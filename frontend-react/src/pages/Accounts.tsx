import { useMemo, useState } from "react";
import { Building2, Eye, ListPlus, Loader2, Plus, Radar, Search } from "lucide-react";
import { cn, day, STAGE_LABEL } from "@/lib/utils";
import { go } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Badge, ROLE_TONE } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Avatar, Empty, FitPill } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";

type SortKey = "name" | "fit" | "projects" | "clientprojects" | "researched";
const FILTERS: [string, string][] = [["all", "All"], ["watched", "Watched"], ["changes", "With changes"], ["fit", "Strong fit"], ["running", "Researching"]];

export default function AccountsPage({ accounts, openAdd }: any) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<{ k: SortKey; dir: "asc" | "desc" }>({ k: "fit", dir: "desc" });

  const rows = useMemo(() => {
    let r = accounts.filter((a: any) => `${a.name} ${a.domain || ""} ${a.industry || ""} ${a.best?.name || ""}`.toLowerCase().includes(q.toLowerCase()));
    if (filter === "watched") r = r.filter((a: any) => a.watch);
    if (filter === "changes") r = r.filter((a: any) => a.unread);
    if (filter === "fit") r = r.filter((a: any) => (a.best?.fit_score || 0) >= 0.75);
    if (filter === "running") r = r.filter((a: any) => a.status === "queued" || a.status === "running");
    const val = (a: any) => sort.k === "name" ? a.name.toLowerCase() : sort.k === "fit" ? a.best?.fit_score ?? -1 : sort.k === "projects" ? a.initiatives : sort.k === "clientprojects" ? a.projects || 0 : a.last_researched_at || "";
    return [...r].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * (sort.dir === "asc" ? 1 : -1));
  }, [accounts, q, filter, sort]);

  const th = (k: SortKey) => ({ sort: true, dir: sort.k === k ? sort.dir : null, onSort: () => setSort((s) => ({ k, dir: s.k === k && s.dir === "desc" ? "asc" : "desc" })) });
  const totals = {
    projects: accounts.reduce((n: number, a: any) => n + (a.initiatives || 0), 0),
    watched: accounts.filter((a: any) => a.watch).length,
    changes: accounts.reduce((n: number, a: any) => n + (a.unread || 0), 0),
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-6">
        <Building2 className="size-4 text-muted" />
        <h1 className="text-[15px] font-semibold">Accounts</h1>
        <span className="text-[13px] text-faint">{accounts.length}</span>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => go("/discover")}><Radar />Find companies</Button>
          <Button variant="outline" size="sm" onClick={() => openAdd("list")}><ListPlus />Paste a list</Button>
          <Button size="sm" onClick={() => openAdd("one")}><Plus />Research a company</Button>
        </div>
      </header>

      {accounts.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-6 py-2.5">
          <div className="relative w-64"><Search className="absolute left-2.5 top-2 size-4 text-faint" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search accounts or initiatives" className="h-8 pl-8" /></div>
          <div className="flex items-center gap-1">
            {FILTERS.map(([k, label]) => (
              <button key={k} onClick={() => setFilter(k)} className={cn("h-7 rounded-full border px-2.5 text-[12.5px] font-medium", filter === k ? "border-ink bg-ink text-white" : "border-line text-muted hover:text-fg")}>{label}</button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-4 text-[12.5px] text-muted">
            <span><b className="font-semibold text-fg">{totals.projects}</b> live initiatives</span>
            <span><b className="font-semibold text-fg">{totals.watched}</b> watched</span>
            <span className={cn(totals.changes && "text-saffron-ink")}><b className="font-semibold">{totals.changes}</b> new changes</span>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {!accounts.length ? (
          <div className="mx-auto max-w-2xl px-6 py-16">
            <Empty icon={<Building2 />} title="No accounts yet"
              action={<div className="flex gap-2"><Button onClick={() => openAdd("one")}><Plus />Research a company</Button><Button variant="outline" onClick={() => go("/discover")}><Radar />Scan for signals</Button></div>}>
              Research a company you have in mind, or scan for companies that are hiring testers, launching apps or migrating platforms right now.
            </Empty>
          </div>
        ) : (
          <Table>
            <thead><tr>
              <Th {...th("name")} className="pl-6">Company</Th>
              <Th {...th("fit")}>Fit</Th>
              <Th>Top initiative</Th>
              <Th>Stage</Th>
              <Th>Likely owner</Th>
              <Th {...th("projects")} className="text-right">Initiatives</Th>
              <Th {...th("clientprojects")} className="text-right">Projects</Th>
              <Th {...th("researched")} className="pr-6">Researched</Th>
            </tr></thead>
            <tbody>
              {rows.map((a: any) => {
                const busy = a.status === "queued" || a.status === "running";
                return (
                  <Tr key={a.id} className="cursor-pointer" onClick={() => go(`/a/${a.id}`)}>
                    <Td className="pl-6">
                      <div className="flex items-center gap-2.5">
                        <Avatar name={a.name} size={26} square />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 font-medium">{a.name}
                            {a.watch ? <Eye className="size-3.5 text-faint" aria-label="Watched" /> : null}
                            {a.unread ? <Badge tone="saffron">{a.unread} new</Badge> : null}
                          </div>
                          <div className="truncate text-[12px] text-faint">{[a.industry, a.hq_country].filter(Boolean).join(" · ") || a.domain}</div>
                        </div>
                      </div>
                    </Td>
                    <Td>{a.best ? <FitPill value={a.best.fit_score} /> : <span className="text-faint">–</span>}</Td>
                    <Td className="max-w-[320px]">
                      {busy ? <span className="inline-flex items-center gap-1.5 text-muted"><Loader2 className="size-3.5 animate-spin text-saffron" />Researching…</span>
                        : a.status === "failed" ? <span className="text-danger">Research failed</span>
                        : a.best ? <div className="flex items-center gap-1.5"><span className="truncate">{a.best.name}</span>{a.best.basis === "hiring" && <Badge tone="saffron">Hiring only</Badge>}</div>
                        : <span className="text-faint">No initiatives found</span>}
                    </Td>
                    <Td>{a.best ? <Badge tone="outline">{STAGE_LABEL[a.best.stage] || a.best.stage}</Badge> : null}</Td>
                    <Td>{a.owner ? <div className="flex items-center gap-2"><Avatar name={a.owner.full_name} size={22} />
                      <div className="min-w-0"><div className="truncate">{a.owner.full_name}</div><div className="truncate text-[12px] text-faint">{a.owner.title}</div></div>
                      <Badge tone={ROLE_TONE[a.owner.role]} className="ml-1">{a.owner.role}</Badge></div> : null}</Td>
                    <Td className="text-right tabular-nums">{a.initiatives || 0}</Td>
                    <Td className="text-right tabular-nums">{a.projects ? <button className="hover:underline" onClick={(e) => { e.stopPropagation(); go(`/a/${a.id}/projects`); }}>{a.projects}</button> : <span className="text-faint">0</span>}</Td>
                    <Td className="pr-6 text-muted tabular-nums">{day(a.last_researched_at)}</Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
        {accounts.length > 0 && !rows.length && <p className="px-6 py-10 text-center text-muted">No accounts match this filter.</p>}
      </div>
    </div>
  );
}
