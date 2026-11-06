import { useEffect, useState } from "react";
import { Toaster, toast } from "sonner";
import { CostConfirmHost } from "@/components/CostConfirm";
import { Send, Bell, Building, Building2, ChevronsUpDown, Command as CmdIcon, Compass, KeyRound, Loader2, LogOut, Plus, Radar, Search, Settings2, Sparkles, Users } from "lucide-react";
import { api, post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { go, useApi, useRoute } from "@/lib/hooks";
import { TooltipProvider, Avatar, Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Textarea, Label } from "@/components/ui/input";
import { CommandPalette, CommandItem, CommandGroup } from "@/components/ui/command";
import { SellerDialog } from "@/components/SellerDialog";
import AccountsPage from "@/pages/Accounts";
import CompanyPage from "@/pages/Company";
import DiscoverPage from "@/pages/Discover";
import AlertsPage from "@/pages/Alerts";
import OutreachPage from "@/pages/Outreach";
import TeamPage from "@/pages/Team";
import WorkspacesPage from "@/pages/Workspaces";
import { ForcePasswordPage, LoginPage, PasswordDialog, SetupPage, signOut } from "@/pages/Auth";

export type Health = { configured: boolean; missing_keys: string[]; llm_provider: string | null; people_search: boolean; seller: string };

/** Decides between sign-in, first-time setup, forced password change, and the app itself. */
export default function App() {
  const [me, setMe] = useState<any>(null);
  const [state, setState] = useState<"loading" | "login" | "setup" | "ready">("loading");
  const load = async () => {
    try {
      const m = await api<any>("/api/auth/me");
      setMe(m); setState("ready");
    } catch {
      const st = await api<any>("/api/auth/status").catch(() => ({ needs_setup: false }));
      setMe(null); setState(st.needs_setup ? "setup" : "login");
    }
  };
  useEffect(() => { load(); const f = () => load(); addEventListener("as:signedout", f); return () => removeEventListener("as:signedout", f); }, []);
  const out = async () => { await signOut(); location.hash = "/"; load(); };

  if (state === "loading") return <div className="grid h-full place-items-center"><Loader2 className="size-5 animate-spin text-muted" /></div>;
  if (state === "setup") return <><SetupPage onDone={load} /><Toaster position="bottom-right" /></>;
  if (state === "login") return <><LoginPage onDone={load} /><Toaster position="bottom-right" /></>;
  if (me?.user?.must_change_password) return <><ForcePasswordPage onDone={load} onSignOut={out} /><Toaster position="bottom-right" /></>;
  return <Workspace key={me?.workspace?.id || 0} me={me} onAuthChange={load} onSignOut={out} />;
}

function Workspace({ me, onAuthChange, onSignOut }: { me: any; onAuthChange: () => void; onSignOut: () => void }) {
  const route = useRoute();
  const [pwOpen, setPwOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [addOpen, setAddOpen] = useState<null | "one" | "list">(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [rev, setRev] = useState(0); // bump to refresh lists after mutations
  const refresh = () => setRev((r) => r + 1);
  const health = useApi<Health>("/api/health", [rev]).data;
  const accounts = useApi<any[]>("/api/accounts", [rev], (d) => d.some((a) => a.status === "queued" || a.status === "running"), 4000).data || [];
  const unread = useApi<any>("/api/alerts?unread=true", [rev, route.page]).data?.unread || 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setCmdOpen((v) => !v); } };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, []);

  const ctx = { health, refresh, rev, openAdd: (m: "one" | "list") => setAddOpen(m) };

  return (
    <TooltipProvider>
      <div className="flex h-full">
        <Sidebar route={route} accounts={accounts} unread={unread} health={health} me={me} onCmd={() => setCmdOpen(true)} onAdd={() => setAddOpen("one")}
          onSettings={() => setSettingsOpen(true)} onPassword={() => setPwOpen(true)} onSignOut={onSignOut} onSwitched={onAuthChange} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          {health && !health.configured && (
            <div className="border-b border-saffron/40 bg-saffron-soft px-6 py-2 text-[13px] text-saffron-ink">
              {(health as any).cloud
                ? <>Setup needed: the platform owner must add {health.missing_keys.join(" and ")} as Cloudflare secrets (see DEPLOY.md).</>
                : <>Setup needed: add {health.missing_keys.join(" and ")} to the <code className="rounded bg-white/60 px-1">.env</code> file and restart the app.</>}
            </div>
          )}
          {route.page === "accounts" && <AccountsPage accounts={accounts} {...ctx} />}
          {route.page === "company" && route.id && <CompanyPage key={route.id} id={route.id} tab={route.tab || "initiatives"} {...ctx} />}
          {route.page === "discover" && <DiscoverPage {...ctx} />}
          {route.page === "alerts" && <AlertsPage {...ctx} />}
          {route.page === "outreach" && <OutreachPage />}
          {route.page === "team" && <TeamPage me={me} />}
          {route.page === "workspaces" && <WorkspacesPage me={me} onSwitched={onAuthChange} />}
        </main>
      </div>

      <CommandPalette open={cmdOpen} onOpenChange={setCmdOpen}>
        <CommandGroup heading="Actions">
          <CommandItem onSelect={() => { setCmdOpen(false); setAddOpen("one"); }}><Plus />Research a company</CommandItem>
          <CommandItem onSelect={() => { setCmdOpen(false); setAddOpen("list"); }}><Sparkles />Research a list of companies</CommandItem>
          <CommandItem onSelect={() => { setCmdOpen(false); go("/discover"); }}><Radar />Scan for signals</CommandItem>
          <CommandItem onSelect={() => { setCmdOpen(false); go("/alerts"); }}><Bell />Open alerts</CommandItem>
          <CommandItem onSelect={() => { setCmdOpen(false); setSettingsOpen(true); }}><Settings2 />Edit what we sell</CommandItem>
        </CommandGroup>
        {accounts.length > 0 && (
          <CommandGroup heading="Accounts">
            {accounts.map((a) => (
              <CommandItem key={a.id} value={`${a.name} ${a.domain || ""} ${a.industry || ""}`} onSelect={() => { setCmdOpen(false); go(`/a/${a.id}`); }}>
                <Avatar name={a.name} size={20} square /><span className="flex-1">{a.name}</span><span className="text-xs text-faint">{a.industry}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandPalette>

      <AddDialog mode={addOpen} onClose={() => setAddOpen(null)} onDone={(id) => { refresh(); if (id) go(`/a/${id}`); }} />
      <SellerDialog open={settingsOpen} onOpenChange={setSettingsOpen} onSaved={refresh} />
      <PasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
      <Toaster position="bottom-right" toastOptions={{ className: "!text-[13px]" }} />
      <CostConfirmHost />
    </TooltipProvider>
  );
}

function Sidebar({ route, accounts, unread, health, me, onCmd, onAdd, onSettings, onPassword, onSignOut, onSwitched }: any) {
  const nav = [
    { k: "accounts", label: "Accounts", icon: Building2, href: "/", count: accounts.length },
    { k: "discover", label: "Discover", icon: Compass, href: "/discover" },
    { k: "outreach", label: "Outreach", icon: Send, href: "/outreach" },
    { k: "alerts", label: "Alerts", icon: Bell, href: "/alerts", badge: unread },
  ];
  const active = route.page === "company" ? "accounts" : route.page;
  return (
    <aside className="flex w-[248px] shrink-0 flex-col bg-ink text-rail">
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <svg viewBox="0 0 32 32" className="size-6" aria-hidden><circle cx="16" cy="16" r="14" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="2" /><circle cx="16" cy="16" r="8" fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="2" /><circle cx="16" cy="16" r="3" fill="#F2A93B" /></svg>
        <span className="text-[15px] font-semibold tracking-tight text-white">AccountScope</span>
      </div>
      <div className="px-3">
        <button onClick={onCmd} className="flex h-8 w-full items-center gap-2 rounded-md bg-ink-2 px-2.5 text-[13px] text-rail-muted hover:text-white">
          <Search className="size-3.5" /><span className="flex-1 text-left">Search</span><kbd className="flex items-center gap-0.5 text-[11px]"><CmdIcon className="size-3" />K</kbd>
        </button>
      </div>
      <nav className="mt-3 space-y-0.5 px-2">
        {nav.map((n) => (
          <a key={n.k} href={`#${n.href}`} className={cn("flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium hover:bg-ink-2 hover:text-white", active === n.k && "bg-ink-3 text-white")}>
            <n.icon className="size-4 opacity-80" /><span className="flex-1">{n.label}</span>
            {n.badge ? <span className="rounded-full bg-saffron px-1.5 text-[11px] font-semibold leading-[18px] text-ink">{n.badge}</span> : n.count ? <span className="text-[12px] text-rail-muted">{n.count}</span> : null}
          </a>
        ))}
      </nav>
      <div className="px-3 pt-4">
        <Button variant="accent" className="w-full" onClick={onAdd}><Plus />Research a company</Button>
      </div>
      <div className="mt-5 flex items-center justify-between px-4 text-[11.5px] font-medium uppercase tracking-wide text-rail-muted">Recent</div>
      <div className="mt-1 flex-1 overflow-y-auto px-2 pb-2">
        {accounts.slice(0, 30).map((a: any) => {
          const busy = a.status === "queued" || a.status === "running";
          return (
            <a key={a.id} href={`#/a/${a.id}`} className={cn("flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-ink-2", route.id === a.id && route.page === "company" && "bg-ink-3")}>
              <Avatar name={a.name} size={20} square className="!bg-white/10 !text-white" />
              <span className="flex-1 truncate text-white/90">{a.name}</span>
              {busy ? <Loader2 className="size-3.5 animate-spin text-saffron" /> : a.unread ? <span className="size-1.5 rounded-full bg-saffron" /> : a.status === "failed" ? <span className="size-1.5 rounded-full bg-[#e0735f]" /> : null}
            </a>
          );
        })}
        {!accounts.length && <p className="px-2 py-1 text-[12.5px] text-rail-muted">Nothing researched yet.</p>}
      </div>
      <div className="border-t border-ink-3 p-3">
        <div className="mb-2 flex items-center gap-1.5 px-1 text-[11.5px] text-rail-muted">
          <span className={cn("size-1.5 rounded-full", health?.configured ? "bg-[#5fd3a8]" : "bg-[#e0735f]")} />
          {health ? (health.configured ? `${health.llm_provider === "openai" ? "GPT" : "Claude"} · Tavily${health.people_search ? " · Apollo" : ""}` : "Setup needed") : "…"}
        </div>
        <button onClick={onSettings} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-ink-2">
          <Settings2 className="size-3.5 text-rail-muted" /><span className="text-rail-muted">Selling as</span><b className="truncate font-semibold text-white">{health?.seller || "…"}</b>
        </button>
        {me?.user && <AccountMenu me={me} onPassword={onPassword} onSignOut={onSignOut} onSwitched={onSwitched} />}
      </div>
    </aside>
  );
}

function AddDialog({ mode, onClose, onDone }: { mode: null | "one" | "list"; onClose: () => void; onDone: (id?: number) => void }) {
  const [name, setName] = useState(""); const [domain, setDomain] = useState(""); const [list, setList] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (mode) { setName(""); setDomain(""); setList(""); } }, [mode]);
  const submit = async () => {
    setBusy(true);
    try {
      if (mode === "one") {
        if (!name.trim()) return;
        const r = await post<any>("/api/accounts", { name, domain: domain || null });
        toast.success(`Researching ${name}`); onClose(); onDone(r.company_id);
      } else {
        const companies = list.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [n, d] = l.split(",").map((x) => x.trim()); return { name: n, domain: d || null }; });
        if (!companies.length) return;
        const r = await post<any>("/api/accounts/bulk", { companies });
        toast.success(`Researching ${r.queued} companies, one after another`); onClose(); onDone();
      }
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!mode} onOpenChange={(v) => !v && onClose()}>
      <DialogContent title={mode === "list" ? "Research a list of companies" : "Research a company"}
        description={mode === "list" ? "One company per line. Add the website after a comma for better people search." : "Finds its live initiatives, the people behind them, vendors, footprint and a reason to reach out."}>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
          {mode === "one" ? (<>
            <div><Label>Company name</Label><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. HDFC Bank" /></div>
            <div><Label>Website (recommended)</Label><Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="e.g. hdfcbank.com" /></div>
          </>) : (
            <Textarea autoFocus rows={8} value={list} onChange={(e) => setList(e.target.value)} placeholder={"HDFC Bank, hdfcbank.com\nSwiggy, swiggy.com\nLufthansa"} />
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />}{mode === "list" ? "Research all" : "Research"}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}



function AccountMenu({ me, onPassword, onSignOut, onSwitched }: any) {
  const u = me.user; const admin = u.is_superadmin || u.role === "admin";
  const switchTo = async (w: any) => { try { await post("/api/auth/switch", { workspace_id: w.id }); toast.success(`Now in ${w.name}`); go("/"); onSwitched(); } catch (e: any) { toast.error(e.message); } };
  return (
    <Menu>
      <MenuTrigger asChild>
        <button className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-ink-2">
          <Avatar name={u.name || u.email} size={24} className="!bg-white/10 !text-white" />
          <div className="min-w-0 flex-1"><div className="truncate text-[12.5px] font-medium text-white">{u.name || u.email}</div>
            <div className="truncate text-[11px] text-rail-muted">{me.workspace?.name}{u.is_superadmin ? " · owner" : u.role === "admin" ? " · admin" : ""}</div></div>
          <ChevronsUpDown className="size-3.5 text-rail-muted" />
        </button>
      </MenuTrigger>
      <MenuContent side="top" align="start" className="w-60">
        <div className="px-2 pb-1.5 pt-1 text-[11.5px] text-faint">{u.email}</div>
        {admin && <MenuItem onSelect={() => go("/team")}><Users />Team</MenuItem>}
        {u.is_superadmin && <MenuItem onSelect={() => go("/workspaces")}><Building />Workspaces</MenuItem>}
        {u.is_superadmin && me.workspaces?.length > 1 && <>
          <div className="mx-2 my-1 border-t border-line" /><div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-faint">Switch workspace</div>
          {me.workspaces.map((w: any) => <MenuItem key={w.id} onSelect={() => w.id !== me.workspace?.id && switchTo(w)}>
            <Avatar name={w.name} size={16} square /><span className="flex-1 truncate">{w.name}</span>{w.id === me.workspace?.id && <span className="text-[11px] text-owner">current</span>}</MenuItem>)}
        </>}
        <div className="mx-2 my-1 border-t border-line" />
        <MenuItem onSelect={onPassword}><KeyRound />Change password</MenuItem>
        <MenuItem onSelect={onSignOut}><LogOut />Sign out</MenuItem>
      </MenuContent>
    </Menu>
  );
}
