import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Loader2 } from "lucide-react";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";

function Brand() {
  return (
    <div className="mb-6 flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden><circle cx="16" cy="16" r="14" fill="none" stroke="#1b1f3b" strokeOpacity=".25" strokeWidth="2" /><circle cx="16" cy="16" r="8" fill="none" stroke="#1b1f3b" strokeOpacity=".5" strokeWidth="2" /><circle cx="16" cy="16" r="3" fill="#F2A93B" /></svg>
      <span className="text-[17px] font-semibold tracking-tight">AccountScope</span>
    </div>
  );
}

function Shell({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-full place-items-center bg-canvas px-4 py-10">
      <div className="w-full max-w-[380px] rounded-xl border border-line bg-white p-7 shadow-sm">
        <Brand />
        <h1 className="text-[18px] font-semibold">{title}</h1>
        {sub && <p className="mt-1 text-[13px] text-muted">{sub}</p>}
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, ...p }: any) {
  return <div className="space-y-1"><Label>{label}</Label><Input {...p} /></div>;
}

export function LoginPage({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState(""); const [pw, setPw] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { await post("/api/auth/login", { email, password: pw }); onDone(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <Shell title="Sign in" sub="Use the email and password your admin gave you.">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Email" type="email" autoComplete="username" value={email} onChange={(e: any) => setEmail(e.target.value)} autoFocus />
        <Field label="Password" type="password" autoComplete="current-password" value={pw} onChange={(e: any) => setPw(e.target.value)} />
        {err && <p className="text-[12.5px] text-danger">{err}</p>}
        <Button type="submit" className="w-full" disabled={busy || !email || !pw}>{busy && <Loader2 className="animate-spin" />}Sign in</Button>
      </form>
      <p className="mt-4 text-[12px] text-faint">Forgot your password? Ask your workspace admin to reset it.</p>
    </Shell>
  );
}

export function SetupPage({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ company: "", name: "", email: "", password: "" }); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF((x) => ({ ...x, [k]: e.target.value }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { await post("/api/auth/setup", f); onDone(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <Shell title="Create the owner account" sub="First start: this account owns the platform and creates workspaces for client companies.">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Your company" placeholder="e.g. Moolya" value={f.company} onChange={set("company")} autoFocus />
        <Field label="Your name" value={f.name} onChange={set("name")} />
        <Field label="Email" type="email" autoComplete="username" value={f.email} onChange={set("email")} />
        <Field label="Password" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} />
        <p className="text-[11.5px] text-faint">At least 10 characters, with upper- and lower-case letters and a number.</p>
        {err && <p className="text-[12.5px] text-danger">{err}</p>}
        <Button type="submit" className="w-full" disabled={busy || !f.email || !f.password}>{busy && <Loader2 className="animate-spin" />}Create account</Button>
      </form>
    </Shell>
  );
}

function PasswordForm({ onDone, submitLabel }: { onDone: () => void; submitLabel: string }) {
  const [cur, setCur] = useState(""); const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    if (pw !== pw2) return setErr("The new passwords don't match");
    setBusy(true);
    try { await post("/api/auth/password", { current: cur, new: pw }); toast.success("Password changed"); onDone(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Current password" type="password" autoComplete="current-password" value={cur} onChange={(e: any) => setCur(e.target.value)} autoFocus />
      <Field label="New password" type="password" autoComplete="new-password" value={pw} onChange={(e: any) => setPw(e.target.value)} />
      <Field label="Repeat new password" type="password" autoComplete="new-password" value={pw2} onChange={(e: any) => setPw2(e.target.value)} />
      <p className="text-[11.5px] text-faint">At least 10 characters, with upper- and lower-case letters and a number.</p>
      {err && <p className="text-[12.5px] text-danger">{err}</p>}
      <Button type="submit" className="w-full" disabled={busy || !cur || !pw}>{busy && <Loader2 className="animate-spin" />}{submitLabel}</Button>
    </form>
  );
}

export function ForcePasswordPage({ onDone, onSignOut }: { onDone: () => void; onSignOut: () => void }) {
  return (
    <Shell title="Choose your own password" sub="You signed in with a temporary password. Set a new one to continue.">
      <PasswordForm onDone={onDone} submitLabel="Save and continue" />
      <button onClick={onSignOut} className="mt-3 text-[12px] text-muted hover:text-fg">Sign out</button>
    </Shell>
  );
}

export function PasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Change password" description="Other devices signed in to your account will be signed out.">
        {open && <PasswordForm onDone={() => onOpenChange(false)} submitLabel="Change password" />}
      </DialogContent>
    </Dialog>
  );
}

/** Shown once after creating a user or resetting a password: the temporary password to hand over. */
export function TempPasswordDialog({ info, onClose }: { info: { email: string; password: string } | null; onClose: () => void }) {
  const text = info ? `Sign in at ${location.origin}\nEmail: ${info.email}\nTemporary password: ${info.password}\nYou'll be asked to choose your own password.` : "";
  return (
    <Dialog open={!!info} onOpenChange={(v) => !v && onClose()}>
      <DialogContent title="Share these sign-in details" description="This temporary password is shown only once. Send it privately; they'll set their own password at first sign-in.">
        {info && (
          <div className="space-y-3">
            <pre className="whitespace-pre-wrap rounded-md border border-line bg-canvas p-3 font-mono text-[12.5px]">{text}</pre>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { navigator.clipboard?.writeText(text); toast.success("Copied"); }}><KeyRound />Copy details</Button>
              <Button onClick={onClose}>Done</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export async function signOut() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* ignore */ }
}
