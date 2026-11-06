import { useMemo, useState } from "react";
import { Download, Loader2, Send, Wand2 } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { cn, day } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, Checkbox, Empty, Tooltip } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { PitchSheet, ScorePill } from "@/components/PitchSheet";

const FILTERS = [["all", "All"], ["ready", "Ready"], ["approved", "Approved"], ["exported", "Exported"], ["weak", "Below 7.5"]] as const;

export default function OutreachPage() {
  const { data, reload } = useApi<any[]>("/api/pitches", [], (d) => d.some((p) => p.status === "queued" || p.status === "running"), 2500);
  const [f, setF] = useState<string>("all");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<any>(null);
  const rows = useMemo(() => (data || []).filter((p) => f === "all" || (f === "weak" ? (p.score ?? 0) < 7.5 && p.status !== "failed" : p.status === f)), [data, f]);
  const exportable = (data || []).filter((p) => sel.has(p.id) && ["ready", "approved", "exported"].includes(p.status));
  const missingUrl = exportable.filter((p) => !p.linkedin_url).length;
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const download = () => { location.href = `/api/pitches.csv?ids=${exportable.map((p) => p.id).join(",")}`; setTimeout(reload, 1200); };

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-14 items-center gap-3 border-b border-line px-6">
        <Send className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Outreach</h1>
        <span className="text-[13px] text-faint">{data?.length ?? 0} pitches</span>
        <div className="ml-auto flex items-center gap-2">
          {exportable.length > 0 && missingUrl > 0 && <span className="text-[12px] text-saffron-ink">{missingUrl} without a LinkedIn URL</span>}
          <Button size="sm" onClick={download} disabled={!exportable.length}><Download />Export {exportable.length || ""} as CSV</Button>
        </div>
      </header>
      <div className="flex items-center gap-1.5 border-b border-line px-6 py-2.5">
        {FILTERS.map(([k, l]) => <button key={k} onClick={() => setF(k)} className={cn("h-7 rounded-full border px-3 text-[12.5px]", f === k ? "border-ink bg-ink text-white" : "border-line bg-white text-muted hover:text-fg")}>{l}</button>)}
        <p className="ml-auto max-w-[520px] text-right text-[12px] text-faint">The CSV has a Connection note and a Message 1 column per lead. In Dripify, map them to Custom Lead Fields and use them as variables.</p>
      </div>
      <div className="flex-1">
        {!data ? <div className="p-10 text-center"><Loader2 className="mx-auto size-5 animate-spin text-muted" /></div>
          : !data.length ? <div className="p-6"><Empty icon={<Wand2 />} title="No pitches yet">Open an account and click <b>Write pitches</b>, or use the wand on any contact.</Empty></div>
          : (
            <Table>
              <thead><tr>
                <Th className="w-10 pl-6"><Checkbox checked={rows.length > 0 && rows.every((r) => sel.has(r.id))} onCheckedChange={(v) => setSel(v ? new Set(rows.map((r) => r.id)) : new Set())} /></Th>
                <Th>Person</Th><Th>Hook</Th><Th>Offer</Th><Th>Score</Th><Th>Status</Th><Th className="pr-6">Updated</Th>
              </tr></thead>
              <tbody>{rows.map((p) => {
                const busy = p.status === "queued" || p.status === "running";
                return (
                  <Tr key={p.id} className="cursor-pointer" onClick={() => setOpen({ person_id: p.person_id, pitch_id: p.id, full_name: p.full_name, title: p.title, company: p.company })}>
                    <Td className="pl-6" onClick={(e) => e.stopPropagation()}><Checkbox checked={sel.has(p.id)} onCheckedChange={() => toggle(p.id)} /></Td>
                    <Td><div className="flex items-center gap-2.5"><Avatar name={p.full_name} size={26} /><div className="min-w-0"><div className="font-medium">{p.full_name}</div>
                      <div className="truncate text-[12px] text-faint">{p.title} · {p.company}</div></div></div></Td>
                    <Td className="max-w-[380px]">{busy ? <span className="inline-flex items-center gap-1.5 text-muted"><Loader2 className="size-3.5 animate-spin text-saffron" />Agent writing…</span>
                      : <div><div className="truncate">{p.hook || "–"}</div><div className="truncate text-[12px] text-faint">{p.connection_note}</div></div>}</Td>
                    <Td className="max-w-[180px] truncate text-[12.5px] text-muted">{p.offer}</Td>
                    <Td><Tooltip content={`${p.rounds} round(s) with the simulated buyer`}><span><ScorePill v={p.score} /></span></Tooltip></Td>
                    <Td><div className="flex items-center gap-1.5"><Badge tone={p.status === "approved" ? "green" : p.status === "exported" ? "violet" : p.status === "failed" ? "red" : "gray"}>{p.status}</Badge>
                      {!p.linkedin_url && !busy && <Tooltip content="No LinkedIn URL: Dripify needs it. Use Get email on the contact."><span><Badge tone="saffron">no URL</Badge></span></Tooltip>}</div></Td>
                    <Td className="pr-6 text-muted tabular-nums">{day(p.updated_at)}</Td>
                  </Tr>
                );
              })}</tbody>
            </Table>
          )}
      </div>
      <PitchSheet person={open} onClose={() => setOpen(null)} onChanged={reload} />
    </div>
  );
}
