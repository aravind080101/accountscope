import { useState } from "react";
import { toast } from "sonner";
import { ArrowRight, Building, Loader2, Plus } from "lucide-react";
import { post } from "@/lib/api";
import { useApi, go } from "@/lib/hooks";
import { day } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Avatar, Empty } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { TempPasswordDialog } from "@/pages/Auth";

export default function WorkspacesPage({ me, onSwitched }: { me: any; onSwitched: () => void }) {
  const { data, reload, error } = useApi<any[]>("/api/workspaces");
  const [creating, setCreating] = useState(false);
  const [temp, setTemp] = useState<{ email: string; password: string } | null>(null);
  const open = async (w: any) => {
    try { await post("/api/auth/switch", { workspace_id: w.id }); toast.success(`Now in ${w.name}`); go("/"); onSwitched(); } catch (e: any) { toast.error(e.message); }
  };
  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-14 items-center gap-3 border-b border-line px-6">
        <Building className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Workspaces</h1>
        <span className="text-[13px] text-faint">One per client company. Each sees only its own accounts, research, profile and team.</span>
        <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}><Plus />New workspace</Button>
      </header>
      {error ? <div className="p-6"><Empty title="Only the platform owner can manage workspaces">{error}</Empty></div>
        : !data ? <div className="p-10 text-center"><Loader2 className="mx-auto size-5 animate-spin text-muted" /></div>
        : (
          <Table>
            <thead><tr><Th className="pl-6">Workspace</Th><Th className="text-right">Users</Th><Th className="text-right">Accounts</Th><Th>Created</Th><Th className="pr-6 text-right" /></tr></thead>
            <tbody>{data.map((w) => (
              <Tr key={w.id}>
                <Td className="pl-6"><div className="flex items-center gap-2.5"><Avatar name={w.name} size={26} square /><span className="font-medium">{w.name}</span>
                  {w.id === me?.workspace?.id && <Badge tone="green">You're here</Badge>}</div></Td>
                <Td className="text-right tabular-nums">{w.users}</Td>
                <Td className="text-right tabular-nums">{w.accounts}</Td>
                <Td className="text-muted tabular-nums">{day(w.created_at)}</Td>
                <Td className="pr-6 text-right">{w.id !== me?.workspace?.id && <Button size="xs" variant="outline" onClick={() => open(w)}>Open<ArrowRight /></Button>}</Td>
              </Tr>))}</tbody>
          </Table>
        )}
      <NewWorkspaceDialog open={creating} onOpenChange={setCreating} onCreated={(email, pw) => { setTemp({ email, password: pw }); reload(); }} />
      <TempPasswordDialog info={temp} onClose={() => setTemp(null)} />
    </div>
  );
}

function NewWorkspaceDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: (email: string, pw: string) => void }) {
  const [f, setF] = useState({ name: "", admin_email: "", admin_name: "" }); const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await post("/api/workspaces", f); onOpenChange(false); onCreated(r.admin.email, r.temp_password); setF({ name: "", admin_email: "", admin_name: "" }); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New workspace" description="For a client company. Its admin signs in with a temporary password and can then add their own team.">
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1"><Label>Company name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Acme Testing" autoFocus /></div>
          <div className="space-y-1"><Label>Admin email</Label><Input type="email" value={f.admin_email} onChange={(e) => setF({ ...f, admin_email: e.target.value })} /></div>
          <div className="space-y-1"><Label>Admin name</Label><Input value={f.admin_name} onChange={(e) => setF({ ...f, admin_name: e.target.value })} /></div>
          {err && <p className="text-[12.5px] text-danger">{err}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={busy || !f.name || !f.admin_email}>{busy && <Loader2 className="animate-spin" />}Create workspace</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
