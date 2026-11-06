"""Deploy AccountScope for free: Cloudflare (free plan) in front, Render (free) runs the app.

    source .venv/bin/activate
    python scripts/deploy_free.py

What it does:
  1. Deploys the Cloudflare Worker: your address, the D1 database and the 6-hourly scheduler.
  2. Makes the private token the Worker and the app share, and saves it in Cloudflare.
  3. Shows you what to paste into Render, then waits for your Render address.
  4. Connects the two, checks the whole thing works, and offers to copy the accounts on this Mac.

Safe to run again: it reuses the token and Render address saved in .env (CLOUD_INTERNAL_TOKEN, RENDER_URL).
"""
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def say(msg: str) -> None:
    print(f"\n▸ {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n✘ {msg}", file=sys.stderr)
    sys.exit(1)


def read_env() -> dict:
    env = {}
    if not ENV_PATH.exists():
        fail(".env not found in this folder. Add your keys there first.")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return env


def remember(key: str, value: str) -> None:
    """Save a deploy setting in .env (which never leaves this Mac)."""
    lines = ENV_PATH.read_text().splitlines()
    lines = [l for l in lines if not l.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def wrangler(*args: str, input_text: str | None = None) -> str:
    r = subprocess.run(["npx", "--yes", "wrangler", *args], cwd=ROOT, input=input_text, text=True,
                       capture_output=True)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        print(out)
        fail(f"wrangler {' '.join(args[:2])} failed. The message above says why.")
    return out


def check(site: str, minutes: int = 10) -> bool:
    """True once a request through the Worker reaches the app and the app can read the database."""
    deadline, n = time.time() + minutes * 60, 0
    while time.time() < deadline:
        try:
            r = httpx.get(f"{site}/api/auth/status", timeout=90, headers={"X-Requested-With": "accountscope"})
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return True
            if r.status_code == 403 and "workers.dev" in r.text:
                fail("The app refused the Worker's token. In Render → accountscope → Environment, make sure "
                     "INTERNAL_TOKEN is exactly the token shown above, save, and run this again.")
        except Exception:
            pass
        n += 1
        print("." if n % 20 else ".\n", end="", flush=True)
        time.sleep(10)
    return False


def main() -> None:
    os.chdir(ROOT)
    env = read_env()
    print("AccountScope free deploy (Cloudflare + Render)\n" + "─" * 46)

    say("Deploying the Cloudflare Worker…")
    out = wrangler("deploy")
    m = re.search(r"https://[a-z0-9.-]+\.workers\.dev", out)
    if not m:
        print(out)
        fail("Deployed, but couldn't find your workers.dev address in the output above.")
    site = m.group(0)
    print(f"  Your address: {site}")
    blueprint = (ROOT / "render.yaml").read_text()
    if f"{site}/__d1" not in blueprint:
        (ROOT / "render.yaml").write_text(re.sub(r"https://[a-z0-9.-]+\.workers\.dev/__d1", f"{site}/__d1", blueprint))
        print("  Updated render.yaml with this address. Commit and push it before creating the Render service.")

    token = env.get("CLOUD_INTERNAL_TOKEN") or secrets.token_hex(32)
    remember("CLOUD_INTERNAL_TOKEN", token)
    say("Saving the shared token in Cloudflare…")
    wrangler("secret", "put", "INTERNAL_TOKEN", input_text=token + "\n")

    render_url = env.get("RENDER_URL", "")
    if not render_url:
        keys = {k: ("in your .env" if env.get(k) else "MISSING from .env") for k in
                ("OPENAI_API_KEY", "TAVILY_API_KEY", "APOLLO_API_KEY")}
        print(f"""
────────────────────────────────────────────────────────────────────────────
Now in your browser:

 1. dashboard.render.com → sign in with GitHub
 2. New → Blueprint → pick your accountscope repo → it reads render.yaml
 3. Fill in the values it asks for:
      INTERNAL_TOKEN   {token}
      OPENAI_API_KEY   copy from .env ({keys['OPENAI_API_KEY']})
      TAVILY_API_KEY   copy from .env ({keys['TAVILY_API_KEY']})
      APOLLO_API_KEY   copy from .env ({keys['APOLLO_API_KEY']})
      ADMIN_EMAIL      the email you'll sign in with
      ADMIN_PASSWORD   10+ characters, upper and lower case, a number
 4. Click Apply / Deploy Blueprint and wait until the service says "Live" (5–10 minutes)
 5. Copy the address at the top of the service page (https://….onrender.com)
────────────────────────────────────────────────────────────────────────────""")
        render_url = input("\nPaste your Render address here: ").strip().rstrip("/")
        if not re.match(r"^https://[a-z0-9.-]+\.onrender\.com$", render_url):
            fail("That should look like https://accountscope-xxxx.onrender.com")
        remember("RENDER_URL", render_url)

    say("Connecting your address to the Render app…")
    wrangler("secret", "put", "APP_ORIGIN", input_text=render_url + "\n")

    say("Checking it all works (the free server may take a minute to wake)")
    if not check(site):
        fail(f"No answer yet. Open your service on dashboard.render.com and check its Logs, then run this again.")
    print(f"\n  ✔ Running at {site}")

    try:
        out = wrangler("d1", "execute", "accountscope", "--remote", "--json", "--command",
                       "SELECT COUNT(*) AS n FROM company")
        n = json.loads(out[out.index("["):])[0]["results"][0]["n"]
    except Exception:
        n = None
    if n == 0 and (ROOT / "data" / "accountscope.db").exists():
        if input("\nCopy the accounts you researched on this Mac to the cloud? [Y/n] ").strip().lower() in ("", "y", "yes"):
            say("Copying your accounts…")
            subprocess.run([sys.executable, "scripts/export_for_d1.py"], cwd=ROOT, check=True)
            wrangler("d1", "execute", "accountscope", "--remote", "--yes", "--file=d1_import.sql")
            print("  ✔ Copied.")

    print(f"""
Done. Open {site} and sign in with the ADMIN_EMAIL and ADMIN_PASSWORD you gave Render.
Then change your password from the menu at the bottom left.

Updating later: commit and push to GitHub (Render redeploys by itself). If the Worker changed, run
this script again.""")


if __name__ == "__main__":
    main()
