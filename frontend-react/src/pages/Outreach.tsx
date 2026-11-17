import { useMemo, useState } from "react";
import { Download, ExternalLink, Loader2, Mail, RefreshCw, Send, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { confirmCost } from "@/components/CostConfirm";
import { useApi } from "@/lib/hooks";
import { cn, day } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, Checkbox, Empty, Tooltip } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { PitchSheet, ScorePill } from "@/components/PitchSheet";
import { Select } from "@/components/ui/input";
import { BriefSheet } from "@/components/BriefSheet";

const FILTERS = [["all", "All"], ["ready", "Ready"], ["approved", "Approved"], ["exported", "Exported"], ["weak", "Needs work"]] as const;

export default function OutreachPage() {
  const { data, reload } = useApi<any[]>("/api/pitches", [], (d) => d.some((p) => p.status === "queued" || p.status === "running"), 2500);
  const campaignList = useApi<any[]>("/api/campaigns").data || [];
  const [camp, setCamp] = useState<string>("all");   // all | general | <campaign id>
  const [f, setF] = useState<string>("all");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<any>(null);
  const [brief, setBrief] = useState<any>(null);
  const [enriching, setEnriching] = useState<number | null>(null);
  const enrich = async (p: any) => {
    if (!(await confirmCost(`/api/people/${p.person_id}/cost?action=enrich`, `Get ${p.full_name}'s email?`, "Get email"))) return;
    setEnriching(p.person_id);
    try { await post(`/api/people/${p.person_id}/enrich`); toast.success("Contact revealed"); reload(); }
    catch (e: any) { toast.error(e.message); } finally { setEnriching(null); }
  };
  const rows = useMemo(() => (data || [])
    .filter((p) => camp === "all" || (camp === "general" ? !p.campaign_id : String(p.campaign_id) === camp))
    .filter((p) => f === "all" || (f === "weak" ? (p.score ?? 0) < 7.5 && p.status !== "failed" : p.status === f)), [data, f, camp]);
  const exportable = (data || []).filter((p) => sel.has(p.id) && ["ready", "approved", "exported"].includes(p.status));
  const missingUrl = exportable.filter((p) => !p.linkedin_url).length;
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const rerun = async (ids: number[]) => {
    if (!ids.length) return;
    const who = ids.length === 1 ? (data || []).find((p) => p.id === ids[0])?.full_name : `${ids.length} people`;
    if (!(await confirmCost(`/api/pitches/rerun/cost?ids=${ids.join(",")}`, `Re-run the outreach for ${who}?`, "Re-run"))) return;
    try {
      const r = await post("/api/pitches/rerun", { ids });
      toast.success(`Re-writing ${r.queued} pitch${r.queued === 1 ? "" : "es"} with the current rules`);
      setSel(new Set()); reload();
    } catch (e: any) { toast.error(e.message); }
  };
  const rerunnable = (data || []).filter((p) => sel.has(p.id) && p.status !== "queued" && p.status !== "running").map((p) => p.id);
  const download = () => { location.href = `/api/pitches.csv?ids=${exportable.map((p) => p.id).join(",")}`; setTimeout(reload, 1200); };

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-14 items-center gap-3 border-b border-line px-6">
        <Send className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Outreach</h1>
        <span className="text-[13px] text-faint">{data?.length ?? 0} pitches</span>
        <div className="ml-auto flex items-center gap-2">
          {exportable.length > 0 && missingUrl > 0 && <span className="text-[12px] text-saffron-ink">{missingUrl} without a LinkedIn URL</span>}
          <Button size="sm" variant="outline" onClick={() => rerun(rerunnable)} disabled={!rerunnable.length}><RefreshCw />Re-run {rerunnable.length || ""}</Button>
          <Button size="sm" onClick={download} disabled={!exportable.length}><Download />Export {exportable.length || ""} as CSV</Button>
        </div>
      </header>
      <div className="flex items-center gap-1.5 border-b border-line px-6 py-2.5">
        <Select value={camp} onChange={(e) => setCamp(e.target.value)} className="mr-2 h-7 text-[12.5px]" aria-label="Campaign">
          <option value="all">All outreach</option><option value="general">General (no campaign)</option>
          {campaignList.map((c: any) => <option key={c.id} value={String(c.id)}>Campaign: {c.name}</option>)}
        </Select>
        {FILTERS.map(([k, l]) => <button key={k} onClick={() => setF(k)} title={k === "weak" ? "Scored under 7.5/10 against the simulated buyer" : undefined} className={cn("h-7 shrink-0 whitespace-nowrap rounded-full border px-3 text-[12.5px]", f === k ? "border-ink bg-ink text-white" : "border-line bg-white text-muted hover:text-fg")}>{l}</button>)}
        <p className="ml-auto max-w-[520px] text-right text-[12px] text-faint">Select pitches and click Re-run to rewrite them with the latest rules. The CSV has the connection note, Message 1, Message 2 and the full pitch per lead. In Dripify, map them to Custom Lead Fields and use them as variables.</p>
      </div>
      <div className="flex-1">
        {!data ? <div className="p-10 text-center"><Loader2 className="mx-auto size-5 animate-spin text-muted" /></div>
          : !data.length ? <div className="p-6"><Empty icon={<Wand2 />} title="No pitches yet">Open an account and click <b>Write pitches</b>, or use the wand on any contact.</Empty></div>
          : (
            <Table>
              <thead><tr>
                <Th className="w-10 pl-6"><Checkbox checked={rows.length > 0 && rows.every((r) => sel.has(r.id))} onCheckedChange={(v) => setSel(v ? new Set(rows.map((r) => r.id)) : new Set())} /></Th>
                <Th>Person</Th><Th>Hook</Th><Th>Offer</Th><Th>Score</Th><Th>Status</Th><Th>Updated</Th><Th className="w-36 pr-6" />
              </tr></thead>
              <tbody>{rows.map((p) => {
                const busy = p.status === "queued" || p.status === "running";
                return (
                  <Tr key={p.id} className="cursor-pointer" onClick={() => setOpen({ person_id: p.person_id, pitch_id: p.id, full_name: p.full_name, title: p.title, company: p.company, campaign_id: p.campaign_id, campaign: p.campaign })}>
                    <Td className="pl-6" onClick={(e) => e.stopPropagation()}><Checkbox checked={sel.has(p.id)} onCheckedChange={() => toggle(p.id)} /></Td>
                    <Td><div className="flex items-center gap-2.5"><Avatar name={p.full_name} size={26} /><div className="min-w-0"><div className="font-medium">{p.full_name}</div>
                      <div className="truncate text-[12px] text-faint">{p.title} · {p.company}</div>
                      {p.campaign && <Badge tone="violet" className="mt-0.5">Campaign: {p.campaign}</Badge>}
                      {(p.email || p.linkedin_url) && <div className="mt-0.5 flex items-center gap-3 text-[12px]" onClick={(e) => e.stopPropagation()}>
                        {p.email && <a className="inline-flex items-center gap-1 text-sponsor hover:underline" href={`mailto:${p.email}`}><Mail className="size-3" />{p.email}</a>}
                        {p.linkedin_url && <a className="inline-flex items-center gap-1 text-sponsor hover:underline" href={p.linkedin_url} target="_blank" rel="noreferrer"><ExternalLink className="size-3" />LinkedIn</a>}
                      </div>}</div></div></Td>
                    <Td className="max-w-[380px]">{busy ? <span className="inline-flex items-center gap-1.5 text-muted"><Loader2 className="size-3.5 animate-spin text-saffron" />Agent writing…</span>
                      : <div><div className="truncate">{p.hook || "–"}</div><div className="truncate text-[12px] text-faint">{p.connection_note}</div></div>}</Td>
                    <Td className="max-w-[180px] truncate text-[12.5px] text-muted">{p.offer}</Td>
                    <Td><Tooltip content={`${p.rounds} round(s) with the simulated buyer`}><span><ScorePill v={p.score} /></span></Tooltip></Td>
                    <Td><div className="flex items-center gap-1.5"><Badge tone={p.status === "approved" ? "green" : p.status === "exported" ? "violet" : p.status === "failed" ? "red" : "gray"}>{p.status}</Badge>
                      {!p.linkedin_url && !busy && <Tooltip content="No LinkedIn URL: Dripify needs it. Use Get email on the contact."><span><Badge tone="saffron">no URL</Badge></span></Tooltip>}</div></Td>
                    <Td className="text-muted tabular-nums">{day(p.updated_at)}</Td>
                    <Td className="pr-6" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-0.5">
                        {!p.email && <Tooltip content="Get email and LinkedIn (1 Apollo credit)"><span>
                          <Button variant="ghost" size="icon-sm" aria-label={`Get email for ${p.full_name}`} disabled={enriching === p.person_id} onClick={() => enrich(p)}>
                            {enriching === p.person_id ? <Loader2 className="animate-spin" /> : <Mail />}</Button></span></Tooltip>}
                        <Tooltip content={p.has_brief ? "View buyer brief" : "Build a buyer brief"}><span>
                          <Button variant="ghost" size={p.has_brief ? "xs" : "icon-sm"} className={cn(p.has_brief && "text-sponsor hover:text-sponsor")} aria-label={`Buyer brief for ${p.full_name}`} onClick={() => setBrief({ person_id: p.person_id, full_name: p.full_name, title: p.title, company: p.company, has_brief: p.has_brief })}>
                            <Sparkles />{p.has_brief && "Brief"}</Button></span></Tooltip>
                        <Tooltip content="Re-run the outreach messages"><span>
                          <Button variant="ghost" size="icon-sm" aria-label={`Re-run outreach for ${p.full_name}`} disabled={busy} onClick={() => rerun([p.id])}><RefreshCw /></Button></span></Tooltip>
                      </div></Td>
                  </Tr>
                );
              })}</tbody>
            </Table>
          )}
      </div>
      <PitchSheet person={open} onClose={() => setOpen(null)} onChanged={reload} />
      <BriefSheet person={brief} onClose={() => setBrief(null)} onBuilt={reload} />
    </div>
  );
}
