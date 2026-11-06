import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Loader2, UserPlus, Users } from "lucide-react";
import { api, post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { day } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Avatar, Empty } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { TempPasswordDialog } from "@/pages/Auth";

export default function TeamPage({ me }: { me: any }) {
  const { data, reload, error } = useApi<any[]>("/api/team");
  const [adding, setAdding] = useState(false);
  const [temp, setTemp] = useState<{ email: string; password: string } | null>(null);
  const act = async (fn: () => Promise<any>, ok?: string) => { try { await fn(); ok && toast.success(ok); reload(); } catch (e: any) { toast.error(e.message); } };
  const reset = (u: any) => act(async () => { const r = await post(`/api/team/${u.id}/reset`); setTemp({ email: u.email, password: r.temp_password }); });

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-14 items-center gap-3 border-b border-line px-6">
        <Users className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Team</h1>
        <span className="text-[13px] text-faint">{me?.workspace?.name}</span>
        <Button size="sm" className="ml-auto" onClick={() => setAdding(true)}><UserPlus />Add teammate</Button>
      </header>
      <div className="flex-1">
        {error ? <div className="p-6"><Empty title="Only workspace admins can manage the team">{error}</Empty></div>
          : !data ? <div className="p-10 text-center"><Loader2 className="mx-auto size-5 animate-spin text-muted" /></div>
          : (
            <Table>
              <thead><tr><Th className="pl-6">Person</Th><Th>Role</Th><Th>Status</Th><Th>Last sign-in</Th><Th className="pr-6 text-right">Actions</Th></tr></thead>
              <tbody>{data.map((u) => {
                const self = u.id === me?.user?.id;
                return (
                  <Tr key={u.id}>
                    <Td className="pl-6"><div className="flex items-center gap-2.5"><Avatar name={u.name || u.email} size={26} />
                      <div><div className="font-medium">{u.name || u.email.split("@")[0]}{self && <span className="ml-1.5 text-[12px] text-faint">(you)</span>}</div><div className="text-[12px] text-faint">{u.email}</div></div></div></Td>
                    <Td>{u.is_superadmin ? <Badge tone="violet">Owner</Badge> : (
                      <Select value={u.role} disabled={self} onChange={(e) => act(() => api(`/api/team/${u.id}`, { method: "PATCH", body: JSON.stringify({ role: e.target.value }) }), "Role updated")} className="h-7 w-28 text-[12.5px]">
                        <option value="member">Member</option><option value="admin">Admin</option>
                      </Select>)}</Td>
                    <Td>{!u.active ? <Badge tone="gray">Deactivated</Badge> : u.must_change_password ? <Badge tone="saffron">Invited</Badge> : <Badge tone="green">Active</Badge>}</Td>
                    <Td className="text-muted tabular-nums">{u.last_login_at ? day(u.last_login_at) : "Never"}</Td>
                    <Td className="pr-6"><div className="flex justify-end gap-1">
                      {!self && !u.is_superadmin && <>
                        <Button size="xs" variant="ghost" onClick={() => reset(u)}><KeyRound />Reset password</Button>
                        <Button size="xs" variant="ghost" className={u.active ? "hover:text-danger" : ""}
                          onClick={() => act(() => api(`/api/team/${u.id}`, { method: "PATCH", body: JSON.stringify({ active: !u.active }) }), u.active ? "Deactivated and signed out" : "Reactivated")}>
                          {u.active ? "Deactivate" : "Reactivate"}</Button>
                      </>}
                    </div></Td>
                  </Tr>
                );
              })}</tbody>
            </Table>
          )}
      </div>
      <AddUserDialog open={adding} onOpenChange={setAdding} onCreated={(email, pw) => { setTemp({ email, password: pw }); reload(); }} />
      <TempPasswordDialog info={temp} onClose={() => setTemp(null)} />
    </div>
  );
}

function AddUserDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: (email: string, pw: string) => void }) {
  const [f, setF] = useState({ email: "", name: "", role: "member" }); const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await post("/api/team", f); onOpenChange(false); onCreated(r.user.email, r.temp_password); setF({ email: "", name: "", role: "member" }); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Add a teammate" description="They get a temporary password to share with them; they set their own at first sign-in.">
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1"><Label>Email</Label><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoFocus /></div>
          <div className="space-y-1"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="space-y-1"><Label>Role</Label>
            <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="member">Member: uses the app</option><option value="admin">Admin: also manages the team</option></Select></div>
          {err && <p className="text-[12.5px] text-danger">{err}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={busy || !f.email}>{busy && <Loader2 className="animate-spin" />}Add teammate</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
