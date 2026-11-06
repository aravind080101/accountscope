"""Sign-in, sessions, roles, and team / workspace administration.

Roles
- Platform owner (is_superadmin): creates client workspaces and their first admin; can switch into any workspace.
- Workspace admin: adds and removes teammates in their workspace, resets their passwords.
- Member: uses the app inside their workspace.

Passwords are hashed with scrypt (salted). Sessions are random tokens in an HttpOnly cookie; only a
SHA-256 of the token is stored. New users and resets get a one-time temporary password that must be
changed at first sign-in.
"""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import config, db, tenancy

COOKIE = "as_session"
CSRF_HEADER = "x-requested-with"          # the app sends this on every change; other sites' forms can't
PUBLIC = {"/api/auth/login", "/api/auth/status", "/api/auth/setup", "/api/auth/logout"}
router = APIRouter()


# ------------------------------------------------------------------ passwords


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


def check_strength(pw: str) -> None:
    if len(pw or "") < 10:
        raise HTTPException(400, "Use at least 10 characters")
    if pw.lower() == pw or pw.upper() == pw or not any(c.isdigit() for c in pw):
        raise HTTPException(400, "Mix upper- and lower-case letters and at least one number")


def temp_password() -> str:
    # readable, strong enough for one use, always passes check_strength
    return f"{secrets.token_urlsafe(6)}-{secrets.randbelow(90) + 10}Aa"


# ------------------------------------------------------------------ sessions


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_cache: dict[str, tuple[float, dict | None]] = {}


def _forget(token_hash: str | None = None, user_id: int | None = None) -> None:
    for k in list(_cache):
        if k == token_hash or (user_id and (_cache[k][1] or {}).get("id") == user_id):
            _cache.pop(k, None)


def start_session(resp: Response, user: dict) -> None:
    token = secrets.token_urlsafe(32)
    with db.session() as s:
        s.execute("INSERT INTO auth_session(token_hash, user_id, workspace_id, expires_at) VALUES (?,?,?,?)",
                  (_hash_token(token), user["id"], user["workspace_id"],
                   (_now() + timedelta(days=config.SESSION_DAYS)).isoformat()))
        s.execute("UPDATE app_user SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
        s.execute("DELETE FROM auth_session WHERE expires_at < ?", (_now().isoformat(),))
    resp.set_cookie(COOKIE, token, max_age=int(config.SESSION_DAYS * 86400), httponly=True,
                    secure=config.RUNNING_IN_CLOUD, samesite="lax", path="/")


def session_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    th = _hash_token(token)
    hit = _cache.get(th)
    if hit and hit[0] > time.time():
        return hit[1]
    with db.session() as s:
        r = s.execute(
            """SELECT u.id, u.email, u.name, u.role, u.is_superadmin, u.must_change_password, u.workspace_id home_workspace,
               a.workspace_id, a.expires_at FROM auth_session a JOIN app_user u ON u.id=a.user_id
               WHERE a.token_hash=? AND u.active=1""", (th,)).fetchone()
    user = dict(r) if r and r["expires_at"] > _now().isoformat() else None
    if user:
        user["workspace_id"] = user["workspace_id"] or user["home_workspace"]
    _cache[th] = (time.time() + 30, user)
    return user


def end_session(request: Request, resp: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with db.session() as s:
            s.execute("DELETE FROM auth_session WHERE token_hash=?", (_hash_token(token),))
        _forget(_hash_token(token))
    resp.delete_cookie(COOKIE, path="/")


# ------------------------------------------------------------------ middleware


async def middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if path.startswith("/api/internal/"):
        if not config.INTERNAL_TOKEN or not hmac.compare_digest(request.headers.get("x-internal-token", ""), config.INTERNAL_TOKEN):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return await call_next(request)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "accountscope":
        return JSONResponse({"detail": "Missing request header"}, status_code=403)
    if not config.REQUIRE_LOGIN:
        request.state.user = None
        token = tenancy.set_current(1)
        try:
            return await call_next(request)
        finally:
            tenancy._current.reset(token)
    if path in PUBLIC:
        return await call_next(request)
    user = session_user(request)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    if user["must_change_password"] and path not in ("/api/auth/me", "/api/auth/password"):
        return JSONResponse({"detail": "Change your temporary password first"}, status_code=403)
    request.state.user = user
    token = tenancy.set_current(user["workspace_id"])
    try:
        return await call_next(request)
    finally:
        tenancy._current.reset(token)


def bootstrap() -> None:
    """Create the platform owner from ADMIN_EMAIL / ADMIN_PASSWORD when no owner exists (first start, or after
    the owner row was deleted to recover a lost password)."""
    if not (config.ADMIN_EMAIL and config.ADMIN_PASSWORD):
        return
    with db.session() as s:
        if s.execute("SELECT 1 FROM app_user WHERE is_superadmin=1 AND active=1 LIMIT 1").fetchone():
            return
        if s.execute("SELECT 1 FROM app_user WHERE email=?", (config.ADMIN_EMAIL,)).fetchone():
            s.execute("UPDATE app_user SET is_superadmin=1, role='admin', active=1, password_hash=?, workspace_id=1 WHERE email=?",
                      (hash_password(config.ADMIN_PASSWORD), config.ADMIN_EMAIL))
            return
        s.execute("""INSERT INTO app_user(workspace_id, email, name, password_hash, role, is_superadmin)
                     VALUES (1, ?, 'Owner', ?, 'admin', 1)""", (config.ADMIN_EMAIL, hash_password(config.ADMIN_PASSWORD)))


# ------------------------------------------------------------------ helpers


def me(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Not signed in")
    return u


def require_admin(request: Request) -> dict:
    u = me(request)
    if not (u["is_superadmin"] or u["role"] == "admin"):
        raise HTTPException(403, "Only workspace admins can do this")
    return u


def require_owner(request: Request) -> dict:
    u = me(request)
    if not u["is_superadmin"]:
        raise HTTPException(403, "Only the platform owner can do this")
    return u


def _user_row(uid: int) -> dict | None:
    with db.session() as s:
        r = s.execute("SELECT id, workspace_id, email, name, role, is_superadmin, active FROM app_user WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


_attempts: dict[str, list[float]] = {}


def _rate_limit(key: str) -> None:
    now = time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < 900]
    _attempts[key] = recent
    if len(recent) >= 8:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    recent.append(now)


# ------------------------------------------------------------------ endpoints


class LoginIn(BaseModel):
    email: str
    password: str


class SetupIn(BaseModel):
    email: str
    name: str = ""
    password: str
    company: str = ""


class PasswordIn(BaseModel):
    current: str
    new: str


class UserIn(BaseModel):
    email: str
    name: str = ""
    role: str = "member"


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None


class WorkspaceIn(BaseModel):
    name: str
    admin_email: str
    admin_name: str = ""


class SwitchIn(BaseModel):
    workspace_id: int


def _has_users() -> bool:
    with db.session() as s:
        return bool(s.execute("SELECT 1 FROM app_user LIMIT 1").fetchone())


@router.get("/api/auth/status")
def status():
    return {"login_required": config.REQUIRE_LOGIN, "needs_setup": config.REQUIRE_LOGIN and config.ALLOW_SETUP and not _has_users()}


@router.post("/api/auth/setup")
def setup(body: SetupIn, response: Response):
    if not (config.REQUIRE_LOGIN and config.ALLOW_SETUP) or _has_users():
        raise HTTPException(404, "Not found")
    check_strength(body.password)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email")
    with db.session() as s:
        if body.company.strip():
            s.execute("UPDATE workspace SET name=? WHERE id=1", (body.company.strip(),))
        uid = s.execute("""INSERT INTO app_user(workspace_id, email, name, password_hash, role, is_superadmin)
                           VALUES (1, ?, ?, ?, 'admin', 1)""", (email, body.name.strip(), hash_password(body.password))).lastrowid
    start_session(response, {"id": uid, "workspace_id": 1})
    return {"ok": True}


@router.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ip = request.headers.get("x-accountscope-client-ip") or request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "")
    _rate_limit(f"{email}|{ip}")
    with db.session() as s:
        r = s.execute("SELECT * FROM app_user WHERE email=? AND active=1", (email,)).fetchone()
    if not r or not verify_password(body.password, r["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    start_session(response, dict(r))
    _attempts.pop(f"{email}|{ip}", None)
    return {"ok": True, "must_change_password": bool(r["must_change_password"])}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    end_session(request, response)
    return {"ok": True}


@router.get("/api/auth/me")
def whoami(request: Request):
    if not config.REQUIRE_LOGIN:
        return {"user": None, "login_required": False, "workspace": {"id": 1}}
    u = me(request)
    with db.session() as s:
        ws = s.execute("SELECT id, name FROM workspace WHERE id=?", (u["workspace_id"],)).fetchone()
        all_ws = db.rows(s.execute("SELECT id, name FROM workspace ORDER BY name")) if u["is_superadmin"] else []
    return {"user": {k: u[k] for k in ("id", "email", "name", "role", "is_superadmin", "must_change_password")},
            "login_required": True, "workspace": dict(ws) if ws else None, "workspaces": all_ws}


@router.post("/api/auth/password")
def change_password(body: PasswordIn, request: Request):
    u = me(request)
    with db.session() as s:
        r = s.execute("SELECT password_hash FROM app_user WHERE id=?", (u["id"],)).fetchone()
    if not verify_password(body.current, r["password_hash"]):
        raise HTTPException(400, "Current password is wrong")
    if body.new == body.current:
        raise HTTPException(400, "Choose a new password")
    check_strength(body.new)
    token_hash = _hash_token(request.cookies.get(COOKIE, ""))
    with db.session() as s:
        s.execute("UPDATE app_user SET password_hash=?, must_change_password=0 WHERE id=?", (hash_password(body.new), u["id"]))
        s.execute("DELETE FROM auth_session WHERE user_id=? AND token_hash!=?", (u["id"], token_hash))  # sign out elsewhere
    _forget(user_id=u["id"])
    return {"ok": True}


@router.post("/api/auth/switch")
def switch(body: SwitchIn, request: Request):
    u = require_owner(request)
    with db.session() as s:
        if not s.execute("SELECT 1 FROM workspace WHERE id=?", (body.workspace_id,)).fetchone():
            raise HTTPException(404, "Workspace not found")
        s.execute("UPDATE auth_session SET workspace_id=? WHERE token_hash=?",
                  (body.workspace_id, _hash_token(request.cookies.get(COOKIE, ""))))
    _forget(user_id=u["id"])
    return {"ok": True}


# --- team (workspace admins)


@router.get("/api/team")
def team(request: Request):
    require_admin(request)
    with db.session() as s:
        return db.rows(s.execute(
            """SELECT id, email, name, role, is_superadmin, active, must_change_password, created_at, last_login_at
               FROM app_user WHERE workspace_id=? ORDER BY active DESC, name, email""", (tenancy.current(),)))


@router.post("/api/team")
def add_user(body: UserIn, request: Request):
    require_admin(request)
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Enter a valid email")
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "Role must be admin or member")
    pw = temp_password()
    with db.session() as s:
        if s.execute("SELECT 1 FROM app_user WHERE email=?", (email,)).fetchone():
            raise HTTPException(400, "That email already has an account")
        uid = s.execute("""INSERT INTO app_user(workspace_id, email, name, password_hash, role, must_change_password)
                           VALUES (?,?,?,?,?,1)""", (tenancy.current(), email, body.name.strip(), hash_password(pw), body.role)).lastrowid
    return {"user": _user_row(uid), "temp_password": pw}


def _teammate(uid: int, request: Request) -> dict:
    admin = require_admin(request)
    u = _user_row(uid)
    if not u or (u["workspace_id"] != tenancy.current() and not admin["is_superadmin"]):
        raise HTTPException(404, "User not found")
    if u["is_superadmin"] and not admin["is_superadmin"]:
        raise HTTPException(403, "You can't change the platform owner")
    return u


@router.post("/api/team/{uid}/reset")
def reset_password(uid: int, request: Request):
    _teammate(uid, request)
    pw = temp_password()
    with db.session() as s:
        s.execute("UPDATE app_user SET password_hash=?, must_change_password=1 WHERE id=?", (hash_password(pw), uid))
        s.execute("DELETE FROM auth_session WHERE user_id=?", (uid,))
    _forget(user_id=uid)
    return {"temp_password": pw}


@router.patch("/api/team/{uid}")
def update_user(uid: int, body: UserPatch, request: Request):
    me_ = me(request)
    _teammate(uid, request)
    if uid == me_["id"] and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "You can't remove your own admin access")
    with db.session() as s:
        if body.role:
            if body.role not in ("admin", "member"):
                raise HTTPException(400, "Role must be admin or member")
            s.execute("UPDATE app_user SET role=? WHERE id=?", (body.role, uid))
        if body.active is not None:
            s.execute("UPDATE app_user SET active=? WHERE id=?", (int(body.active), uid))
            if not body.active:
                s.execute("DELETE FROM auth_session WHERE user_id=?", (uid,))
    _forget(user_id=uid)
    return _user_row(uid)


# --- workspaces (platform owner)


@router.get("/api/workspaces")
def workspaces(request: Request):
    require_owner(request)
    with db.session() as s:
        return db.rows(s.execute(
            """SELECT w.id, w.name, w.created_at,
               (SELECT COUNT(*) FROM app_user u WHERE u.workspace_id=w.id AND u.active=1) users,
               (SELECT COUNT(*) FROM company c WHERE c.workspace_id=w.id) accounts
               FROM workspace w ORDER BY w.name"""))


@router.post("/api/workspaces")
def create_workspace(body: WorkspaceIn, request: Request):
    require_owner(request)
    name, email = body.name.strip(), body.admin_email.strip().lower()
    if not name:
        raise HTTPException(400, "Workspace name is required")
    if "@" not in email:
        raise HTTPException(400, "Enter the admin's email")
    pw = temp_password()
    with db.session() as s:
        if s.execute("SELECT 1 FROM app_user WHERE email=?", (email,)).fetchone():
            raise HTTPException(400, "That email already has an account")
        wid = s.execute("INSERT INTO workspace(name) VALUES (?)", (name,)).lastrowid
        uid = s.execute("""INSERT INTO app_user(workspace_id, email, name, password_hash, role, must_change_password)
                           VALUES (?,?,?,?, 'admin', 1)""", (wid, email, body.admin_name.strip(), hash_password(pw))).lastrowid
    return {"workspace": {"id": wid, "name": name}, "admin": _user_row(uid), "temp_password": pw}


@router.patch("/api/workspaces/{wid}")
def rename_workspace(wid: int, body: dict, request: Request):
    require_owner(request)
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Workspace name is required")
    with db.session() as s:
        s.execute("UPDATE workspace SET name=? WHERE id=?", (name, wid))
    return {"id": wid, "name": name}
