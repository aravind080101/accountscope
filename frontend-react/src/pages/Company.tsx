import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Activity, Briefcase, Check, ChevronDown, ChevronRight, Copy, Download, ExternalLink, Eye, EyeOff, FileText, Globe, Mail,
  MapPin, MoreHorizontal, Network, FolderKanban, ArrowRight, ArrowLeft, Building2, RefreshCw, Sparkles, Wand2, ThumbsDown, ThumbsUp, Trash2, Undo2, Users, Loader2, Handshake,
} from "lucide-react";
import { api, post } from "@/lib/api";
import { cn, day, pct, SOURCE_LABEL, STAGES, STAGE_LABEL, ALERT_LABEL } from "@/lib/utils";
import { go, useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Badge, ROLE_TONE } from "@/components/ui/badge";
import { Avatar, Empty, FitPill, Menu, MenuContent, MenuItem, MenuTrigger, Meter, Skeleton, Tooltip } from "@/components/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { PitchSheet } from "@/components/PitchSheet";
import { BriefSheet } from "@/components/BriefSheet";

const RUN_STEPS = ["Reading sources", "Finding initiatives", "Mapping people", "Done"];
const stepOf = (log: string[]) => { const t = log.join("\n"); return /Done$/m.test(t) ? 3 : /contacts, fit/.test(t) ? 2 : /Extracting/.test(t) ? 1 : 0; };

export default function CompanyPage({ id, tab, refresh, health }: any) {
  const busyFn = (d: any) => d?.run && ["queued", "running"].includes(d.run.status);
  const { data: d, reload, error } = useApi<any>(`/api/accounts/${id}`, [], busyFn, 2000);
  const [brief, setBrief] = useState<any>(null);
  const [pitchFor, setPitchFor] = useState<any>(null);
  useEffect(() => { const f = (e: any) => setPitchFor(e.detail); addEventListener("as:pitch", f); return () => removeEventListener("as:pitch", f); }, []);
  const wasBusy = useMemo(() => busyFn(d), [d]);
  useEffect(() => { if (d && !wasBusy) refresh?.(); /* refresh sidebar when a run finishes */ }, [wasBusy]); // eslint-disable-line

  if (error) return <div className="p-8"><Empty title="Couldn't load this account">{error}</Empty></div>;
  if (!d) return <div className="space-y-3 p-8"><Skeleton className="h-8 w-64" /><Skeleton className="h-4 w-96" /><Skeleton className="mt-6 h-40 w-full" /></div>;

  const c = d.company, run = d.run, busy = busyFn(d);
  const setTab = (t: string) => go(`/a/${id}/${t}`);
  const act = async (fn: () => Promise<any>, ok?: string) => { try { await fn(); ok && toast.success(ok); await reload(); refresh?.(); } catch (e: any) { toast.error(/not found/i.test(e.message) ? "That list was out of date and has been refreshed. Try again." : e.message); await reload(); } };

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <header className="border-b border-line px-6 pt-4">
        <div className="flex items-center gap-1.5 text-[12.5px] text-faint">
          <a href="#/" className="hover:text-fg">Accounts</a><ChevronRight className="size-3" /><span className="text-muted">{c.name}</span>
        </div>
        <div className="mt-3 flex items-start gap-3.5">
          <Avatar name={c.name} size={44} square />
          <div className="min-w-0 flex-1">
            <h1 className="text-[22px] font-semibold leading-tight tracking-tight">{c.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
              {c.industry && <span>{c.industry}</span>}
              {c.hq_country && <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{c.hq_country}</span>}
              {c.domain && <a className="inline-flex items-center gap-1 hover:text-fg" href={`https://${c.domain}`} target="_blank" rel="noreferrer"><Globe className="size-3.5" />{c.domain}</a>}
              {c.last_researched_at && <span className="text-faint">Researched {day(c.last_researched_at)}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Tooltip content={`Re-research every ${d.watch_every_days} days and alert you to changes`}>
              <Button variant={c.watch ? "subtle" : "outline"} size="sm" onClick={() => act(() => post(`/api/accounts/${id}/watch`, { watch: !c.watch }), c.watch ? "Stopped watching" : "Watching weekly")}>
                {c.watch ? <><Eye />Watching</> : <><EyeOff />Watch weekly</>}
              </Button>
            </Tooltip>
            <Tooltip content="The agent writes pitches for the top 5 contacts on strong-fit initiatives and projects">
              <Button variant="outline" size="sm" disabled={busy} onClick={() => act(async () => { const r = await post(`/api/accounts/${id}/pitches`, { limit: 5, min_fit: 0.5 }); toast.success(`Writing ${r.queued} pitches. Follow them in Outreach.`); go("/outreach"); })}><Wand2 />Write pitches</Button>
            </Tooltip>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => act(() => post(`/api/accounts/${id}/refresh?force=true`))}>
              {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />}{busy ? "Researching" : "Research again"}
            </Button>
            <Menu><MenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="More"><MoreHorizontal /></Button></MenuTrigger>
              <MenuContent>
                <MenuItem onSelect={() => { location.href = `/api/accounts/${id}/export.csv`; }}><Download />Export contacts (CSV)</MenuItem>
                <MenuItem className="text-danger" onSelect={async () => { if (confirm(`Delete ${c.name} and all its research?`)) { await api(`/api/accounts/${id}`, { method: "DELETE" }); toast.success(`Deleted ${c.name}`); refresh?.(); go("/"); } }}><Trash2 />Delete account</MenuItem>
              </MenuContent>
            </Menu>
          </div>
        </div>
        <Tabs value={tab} onValueChange={setTab} className="mt-4">
          <TabsList className="border-b-0">
            <TabsTrigger value="initiatives"><Briefcase />Initiatives <span className="text-faint">{d.initiatives.length}</span></TabsTrigger>
            <TabsTrigger value="projects"><FolderKanban />Projects <span className="text-faint">{d.projects?.length || 0}</span></TabsTrigger>
            <TabsTrigger value="people"><Network />People</TabsTrigger>
            <TabsTrigger value="footprint"><MapPin />Footprint</TabsTrigger>
            <TabsTrigger value="deals"><Handshake />Vendors & deals</TabsTrigger>
            <TabsTrigger value="changes"><Activity />Changes {d.unread_alerts ? <Badge tone="saffron">{d.unread_alerts}</Badge> : null}</TabsTrigger>
          </TabsList>
        </Tabs>
      </header>

      <div className="flex-1 bg-canvas">
        {busy && <RunProgress run={run} name={c.name} />}
        {run?.status === "failed" && <div className="mx-6 mt-4 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-[13px] text-danger">{run.error}</div>}
        {tab === "initiatives" && <InitiativesTab d={d} reload={reload} act={act} onBrief={setBrief} seller={health?.seller} />}
        {tab === "projects" && <ClientProjectsTab d={d} act={act} onBrief={setBrief} />}
        {tab === "people" && <PeopleTab id={id} onBrief={setBrief} />}
        {tab === "footprint" && <FootprintTab id={id} />}
        {tab === "deals" && <DealsTab id={id} />}
        {tab === "changes" && <ChangesTab id={id} company={c} every={d.watch_every_days} onRead={() => { reload(); refresh?.(); }} />}
      </div>
      <BriefSheet person={brief} onClose={() => setBrief(null)} onBuilt={reload} />
      <PitchSheet person={pitchFor ? { ...pitchFor, company: c.name } : null} onClose={() => setPitchFor(null)} />
    </div>
  );
}

function RunProgress({ run, name }: any) {
  const step = stepOf(run.log);
  return (
    <div className="mx-6 mt-4 rounded-lg border border-line bg-white p-4">
      <div className="flex items-center gap-2 text-[13px] font-medium"><Loader2 className="size-4 animate-spin text-saffron" />Researching {name}</div>
      <div className="mt-3 grid grid-cols-4 gap-2">
        {RUN_STEPS.map((s, i) => <div key={s} className={cn("border-t-2 pt-1.5 text-[12px]", i < step ? "border-ink text-fg" : i === step ? "border-saffron font-medium text-fg" : "border-line text-faint")}>{s}</div>)}
      </div>
      <div className="mt-2 space-y-0.5 text-[12px] text-muted">{run.log.slice(-3).map((l: string, i: number) => <div key={i} className="truncate">{l.trim()}</div>)}</div>
    </div>
  );
}

/* ------------------------------------------------------------ Initiatives */

function InitiativesTab({ d, reload, act, onBrief, seller }: any) {
  const c = d.company;
  const [open, setOpen] = useState<Record<number, boolean>>(() => (d.initiatives[0] ? { [d.initiatives[0].id]: true } : {}));
  const people = useMemo(() => {
    const m = new Map<string, any>();
    d.initiatives.forEach((i: any) => i.contacts.filter((p: any) => p.feedback !== "rejected" && ["Owner", "Sponsor"].includes(p.role))
      .forEach((p: any) => { if (!m.has(p.full_name)) m.set(p.full_name, { ...p, projects: [i.name] }); else m.get(p.full_name).projects.push(i.name); }));
    return [...m.values()].sort((a, b) => (a.role === "Owner" ? -1 : 1) - (b.role === "Owner" ? -1 : 1) || b.score - a.score).slice(0, 8);
  }, [d]);
  const mix = Object.entries(d.source_mix || {}).sort((a: any, b: any) => b[1] - a[1]) as [string, number][];
  const maxMix = Math.max(1, ...mix.map(([, n]) => n));

  return (
    <div className="grid grid-cols-1 gap-5 p-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <Panel title="Details">
          <Prop k="Industry" v={c.industry} /><Prop k="Headquarters" v={c.hq_country} />
          <Prop k="Website" v={c.domain && <a className="text-sponsor hover:underline" href={`https://${c.domain}`} target="_blank" rel="noreferrer">{c.domain}</a>} />
          <Prop k="Initiatives" v={d.initiatives.length} /><Prop k="Pages read" v={d.documents} />
          <Prop k="Watched" v={c.watch ? "Weekly" : "No"} />
          {c.summary && <p className="border-t border-line-2 px-3 py-2.5 text-[12.5px] leading-relaxed text-muted">{c.summary}</p>}
        </Panel>
        {people.length > 0 && (
          <Panel title="Key people">
            {people.map((p) => (
              <button key={p.full_name} onClick={() => onBrief(p)} className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-canvas">
                <Avatar name={p.full_name} size={28} />
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.full_name}</div><div className="truncate text-[12px] text-faint">{p.title}</div></div>
                <Badge tone={ROLE_TONE[p.role]}>{p.role}</Badge>
              </button>
            ))}
          </Panel>
        )}
        {mix.length > 0 && (
          <Panel title="Sources read">
            <div className="space-y-1.5 px-3 py-2.5">
              {mix.map(([k, n]) => (
                <div key={k} className="grid grid-cols-[96px_1fr_24px] items-center gap-2 text-[12px]">
                  <span className="text-muted">{SOURCE_LABEL[k] || k}</span>
                  <span className="h-1.5 overflow-hidden rounded-full bg-line-2"><i className="block h-full rounded-full bg-ink/70" style={{ width: `${(n / maxMix) * 100}%` }} /></span>
                  <span className="text-right tabular-nums text-muted">{n}</span>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </aside>

      <section className="min-w-0 space-y-2.5">
        <div className="flex items-center justify-between px-0.5 text-[12.5px] text-muted">
          <span>Best fit first, scored against what {seller || "you"} sell{seller ? "s" : ""}.</span>
          {d.dismissed > 0 && <span>{d.dismissed} dismissed hidden</span>}
        </div>
        {d.initiatives.map((i: any) => (
          <InitiativeCard key={i.id} i={i} open={!!open[i.id]} toggle={() => setOpen((o) => ({ ...o, [i.id]: !o[i.id] }))} act={act} onBrief={onBrief} />
        ))}
        {!d.initiatives.length && d.run?.status === "done" && (
          <Empty icon={<Briefcase />} title="No initiatives found in public sources">Add the company's website and research again, or try a more specific company name.</Empty>
        )}
      </section>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="overflow-hidden rounded-lg border border-line bg-white"><div className="border-b border-line-2 px-3 py-2 text-[12px] font-semibold text-muted">{title}</div>{children}</div>;
}
function Prop({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="grid grid-cols-[100px_1fr] gap-2 px-3 py-1.5 text-[13px]"><span className="text-faint">{k}</span><span className="min-w-0 truncate">{v || <span className="text-faint">–</span>}</span></div>;
}

function StageTrack({ stage }: { stage: string }) {
  const idx = Math.max(0, STAGES.findIndex(([k]) => k === stage));
  return (
    <div className="flex items-center gap-1">
      {STAGES.map(([k, label], n) => (
        <div key={k} className="flex flex-1 flex-col gap-1">
          <span className={cn("h-1 rounded-full", n < idx ? "bg-ink" : n === idx ? "bg-saffron" : "bg-line")} />
          <span className={cn("text-[11px]", n === idx ? "font-semibold text-fg" : "text-faint")}>{label}</span>
        </div>
      ))}
    </div>
  );
}

function InitiativeCard({ i, open, toggle, act, onBrief }: any) {
  const live = i.contacts.filter((p: any) => p.feedback !== "rejected");
  const rejected = i.contacts.filter((p: any) => p.feedback === "rejected");
  const confirmed = i.feedback === "confirmed";
  const accent = confirmed ? "bg-sponsor" : i.basis === "announced" ? "bg-owner" : i.basis === "hiring" ? "bg-saffron" : "bg-line";
  return (
    <article className="relative overflow-hidden rounded-lg border border-line bg-white">
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", accent)} />
      <button onClick={toggle} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-canvas/60">
        <FitPill value={i.fit_score} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2"><span className="truncate text-[14px] font-semibold">{i.name}</span>
            {confirmed && <Badge tone="violet">Confirmed</Badge>}
            {i.basis === "hiring" && <Tooltip content="Only job posts point to this initiative so far. Verify before outreach."><span><Badge tone="saffron">Hiring only</Badge></span></Tooltip>}
            {i.basis === "announced" && <Badge tone="green">Publicly described</Badge>}
          </div>
          <div className="mt-0.5 text-[12px] text-faint">{i.category_label} · {STAGE_LABEL[i.stage]} · {pct(i.confidence)}% confidence{i.last_seen ? ` · latest signal ${i.last_seen}` : ""}</div>
        </div>
        <div className="hidden items-center -space-x-1 md:flex">{live.slice(0, 4).map((p: any) => <Avatar key={p.id} name={p.full_name} size={24} className="ring-2 ring-white" />)}</div>
        <ChevronDown className={cn("size-4 text-faint transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="border-t border-line-2 px-4 pb-4 pt-3">
          <StageTrack stage={i.stage} />
          <p className="mt-3 max-w-3xl text-[13.5px] leading-relaxed">{i.summary}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {i.tech.slice(0, 10).map((t: string) => <Badge key={t} tone="outline">{t}</Badge>)}
            <span className="ml-auto text-[12px] text-muted"><b className="font-medium text-fg">Fit:</b> {i.fit_reason}</span>
          </div>

          <div className="mt-4 overflow-hidden rounded-md border border-line">
            <Table>
              <thead><tr><Th className="pl-3">Person</Th><Th>Role</Th><Th>Why this person</Th><Th>Score</Th><Th className="pr-3 text-right">Actions</Th></tr></thead>
              <tbody>
                {live.map((p: any) => <ContactRow key={p.id} p={p} act={act} onBrief={onBrief} />)}
                {!live.length && <tr><Td colSpan={5} className="py-5 text-center text-muted">No people yet. Add the company's website and research again.</Td></tr>}
              </tbody>
            </Table>
          </div>
          {rejected.length > 0 && (
            <details className="mt-2 text-[12.5px] text-muted"><summary className="cursor-pointer">{rejected.length} marked as wrong</summary>
              <div className="mt-1 overflow-hidden rounded-md border border-line opacity-60"><Table><tbody>{rejected.map((p: any) => <ContactRow key={p.id} p={p} act={act} onBrief={onBrief} />)}</tbody></Table></div>
            </details>
          )}

          <div className="mt-3 flex items-start justify-between gap-3">
            <details className="min-w-0 flex-1 text-[12.5px]"><summary className="cursor-pointer text-muted hover:text-fg"><FileText className="mr-1 inline size-3.5" />{i.evidence.length} source{i.evidence.length === 1 ? "" : "s"} behind this</summary>
              <ul className="mt-2 space-y-2">
                {i.evidence.map((e: any, n: number) => (
                  <li key={n} className="border-l-2 border-saffron pl-3">
                    <q className="text-[13px] text-fg">{e.quote}</q>
                    <div className="mt-0.5 text-[12px] text-faint">{e.published_at || "Undated"} · {SOURCE_LABEL[e.source_type] || e.source_type} · <a className="hover:text-fg hover:underline" href={e.url} target="_blank" rel="noreferrer">{e.title || e.url}</a></div>
                  </li>
                ))}
              </ul>
            </details>
            <div className="flex shrink-0 gap-1">
              <Button variant="ghost" size="xs" onClick={() => act(() => post(`/api/initiatives/${i.id}/feedback`, { verdict: confirmed ? "clear" : "confirmed" }))}><Check />{confirmed ? "Undo confirm" : "This is real"}</Button>
              <Button variant="ghost" size="xs" onClick={() => act(() => post(`/api/initiatives/${i.id}/feedback`, { verdict: "dismissed" }), "Dismissed; future research will skip it")}><EyeOff />Not relevant</Button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function ContactRow({ p, act, onBrief, base = "/api/contacts" }: any) {
  const masked = p.full_name.includes("*") && !p.email;
  const [busy, setBusy] = useState(false);
  const enrich = async () => { setBusy(true); await act(() => post(`/api/people/${p.person_id}/enrich`), "Contact revealed"); setBusy(false); };
  return (
    <Tr>
      <Td className="pl-3">
        <div className="flex items-center gap-2.5">
          <Avatar name={p.full_name} size={28} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-medium">{p.full_name}{p.feedback === "confirmed" && <Badge tone="green">Right person</Badge>}</div>
            <div className="truncate text-[12px] text-faint">{p.title}</div>
            {(p.email || p.linkedin_url) && <div className="flex gap-2 text-[12px]">{p.email && <a className="text-sponsor hover:underline" href={`mailto:${p.email}`}>{p.email}</a>}{p.linkedin_url && <a className="text-sponsor hover:underline" href={p.linkedin_url} target="_blank" rel="noreferrer">LinkedIn</a>}</div>}
            {masked && <div className="text-[11.5px] text-faint">Surname hidden until Get email (1 Apollo credit)</div>}
          </div>
        </div>
      </Td>
      <Td><Badge tone={ROLE_TONE[p.role]}>{p.role}</Badge></Td>
      <Td className="max-w-[340px] text-[12.5px] text-muted">
        <div className="line-clamp-2">{p.rationale}</div>
        <div className="mt-0.5 text-[11.5px] text-faint">{p.source === "evidence" ? <span className="font-medium text-owner">Named in sources</span> : "From people database"}</div>
      </Td>
      <Td className="whitespace-nowrap"><Meter value={p.score} /> <span className="ml-1 text-[12px] tabular-nums text-muted">{pct(p.score)}</span></Td>
      <Td className="pr-3">
        <div className="flex items-center justify-end gap-0.5">
          <Tooltip content="Write a pitch: hook, offer, Dripify sequence, tested against a simulated buyer">
            <Button variant="ghost" size="icon-sm" aria-label="Write pitch" onClick={() => window.dispatchEvent(new CustomEvent("as:pitch", { detail: p }))}><Wand2 className="text-saffron" /></Button></Tooltip>
          <Tooltip content={p.has_brief ? "View buyer brief" : "Build a buyer brief from their public statements"}>
            <Button variant="ghost" size="icon-sm" onClick={() => onBrief(p)} aria-label="Buyer brief"><Sparkles className={cn(p.has_brief && "text-sponsor")} /></Button></Tooltip>
          {p.opener && <Tooltip content={p.opener || "Copy opener"}><Button variant="ghost" size="icon-sm" aria-label="Copy opener" onClick={() => { navigator.clipboard?.writeText(p.opener); toast.success("Opener copied"); }}><Copy /></Button></Tooltip>}
          {!p.email && <Tooltip content="Reveal email (1 Apollo credit)"><Button variant="ghost" size="icon-sm" aria-label="Get email" onClick={enrich} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Mail />}</Button></Tooltip>}
          <span className="mx-1 h-4 w-px bg-line" />
          {p.feedback ? (
            <Tooltip content="Undo verdict"><Button variant="ghost" size="icon-sm" aria-label="Undo" onClick={() => act(() => post(`${base}/${p.id}/feedback`, { verdict: "clear" }))}><Undo2 /></Button></Tooltip>
          ) : (<>
            <Tooltip content="Right person"><Button variant="ghost" size="icon-sm" aria-label="Right person" className="hover:text-owner" onClick={() => act(() => post(`${base}/${p.id}/feedback`, { verdict: "confirmed" }), "Marked as the right person")}><ThumbsUp /></Button></Tooltip>
            <Tooltip content="Wrong person: won't be suggested again"><Button variant="ghost" size="icon-sm" aria-label="Wrong person" className="hover:text-danger" onClick={() => act(() => post(`${base}/${p.id}/feedback`, { verdict: "rejected" }), "Won't be suggested again for this kind of initiative")}><ThumbsDown /></Button></Tooltip>
          </>)}
        </div>
      </Td>
    </Tr>
  );
}

/* ------------------------------------------------------------ Client & partner projects */

const PROJECT_STATUS: Record<string, { label: string; tone: any }> = {
  announced: { label: "Announced", tone: "gray" }, won: { label: "Won / signed", tone: "violet" },
  in_progress: { label: "In progress", tone: "amber" }, live: { label: "Live", tone: "green" }, completed: { label: "Completed", tone: "slate" },
};

function ClientProjectsTab({ d, act, onBrief }: any) {
  const [dir, setDir] = useState<"all" | "client" | "partner">("all");
  const [open, setOpen] = useState<Record<number, boolean>>(() => (d.projects?.[0] ? { [d.projects[0].id]: true } : {}));
  const list = (d.projects || []).filter((p: any) => dir === "all" || p.direction === dir);
  const n = (k: string) => (d.projects || []).filter((p: any) => p.direction === k).length;
  if (!d.projects?.length) return (
    <div className="p-6"><Empty icon={<FolderKanban />} title="No client or partner projects found yet">
      Projects are named pieces of work with a specific client or partner: deal wins, case studies, "selected by" announcements.
      Accounts researched before this update need <b>Research again</b> to look for them.</Empty></div>
  );
  return (
    <div className="mx-auto max-w-[1180px] px-6 py-5">
      <div className="mb-3 flex items-center gap-3">
        <div className="flex gap-1">
          {([["all", `All ${d.projects.length}`], ["client", `For clients ${n("client")}`], ["partner", `With partners ${n("partner")}`]] as const).map(([k, l]) => (
            <button key={k} onClick={() => setDir(k as any)} className={cn("h-7 rounded-full border px-3 text-[12.5px]", dir === k ? "border-ink bg-ink text-white" : "border-line bg-white text-muted hover:text-fg")}>{l}</button>
          ))}
        </div>
        <p className="text-[12.5px] text-muted">For clients: {d.company.name} delivers the work. With partners: another company delivers it for {d.company.name}.</p>
      </div>
      <div className="space-y-2">
        {list.map((p: any) => <ClientProjectCard key={p.id} p={p} company={d.company} open={!!open[p.id]} toggle={() => setOpen((o) => ({ ...o, [p.id]: !o[p.id] }))} act={act} onBrief={onBrief} />)}
      </div>
    </div>
  );
}

function ClientProjectCard({ p, company, open, toggle, act, onBrief }: any) {
  const st = PROJECT_STATUS[p.status] || PROJECT_STATUS.announced;
  const confirmed = p.feedback === "confirmed";
  const research = async () => {
    if (p.counterparty_account_id) return go(`/a/${p.counterparty_account_id}`);
    await act(() => post("/api/accounts", { name: p.counterparty }), `Researching ${p.counterparty}`);
  };
  const when = [p.start_date && `from ${p.start_date}`, p.duration, p.last_seen && `latest news ${p.last_seen}`].filter(Boolean).join(" · ");
  return (
    <article className="relative overflow-hidden rounded-lg border border-line bg-white">
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", confirmed ? "bg-sponsor" : p.direction === "client" ? "bg-owner" : "bg-saffron")} />
      <button onClick={toggle} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-canvas/60">
        <FitPill value={p.fit_score} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[14px] font-semibold">{p.name}</span>
            <Badge tone={st.tone}>{st.label}</Badge>
            {p.value && <Badge tone="outline">{p.value}</Badge>}
            {confirmed && <Badge tone="violet">Confirmed</Badge>}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-faint">
            <span className="font-medium text-muted">{company.name}</span>
            {p.direction === "client" ? <ArrowRight className="size-3" /> : <ArrowLeft className="size-3" />}
            <span className="font-medium text-fg">{p.counterparty}</span>
            <span>· {p.direction === "client" ? "client" : "partner delivers"}{when ? ` · ${when}` : ""}</span>
          </div>
        </div>
        <div className="hidden items-center -space-x-1 md:flex">{p.contacts.slice(0, 4).map((c: any) => <Avatar key={c.id} name={c.full_name} size={24} className="ring-2 ring-white" />)}</div>
        <ChevronDown className={cn("size-4 text-faint transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-line-2 px-4 pb-4 pt-3">
          <p className="max-w-3xl text-[13.5px] leading-relaxed">{p.summary}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {p.tech.slice(0, 10).map((t: string) => <Badge key={t} tone="outline">{t}</Badge>)}
            {p.fit_reason && <span className="ml-auto text-[12px] text-muted"><b className="font-medium text-fg">Fit:</b> {p.fit_reason}</span>}
          </div>

          <div className="mt-3 grid gap-3 md:grid-cols-[1fr_260px]">
            <div className="overflow-hidden rounded-md border border-line">
              <div className="border-b border-line-2 bg-canvas px-3 py-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-muted">People at {company.name}</div>
              <Table>
                <tbody>
                  {p.contacts.map((c: any) => <ContactRow key={c.id} p={c} act={act} onBrief={onBrief} base="/api/project-contacts" />)}
                  {!p.contacts.length && <tr><Td className="py-5 text-center text-muted">No one named yet. Add the company's website and research again.</Td></tr>}
                </tbody>
              </Table>
            </div>
            <div className="rounded-md border border-line p-3">
              <div className="flex items-center gap-2"><Building2 className="size-4 text-muted" /><span className="text-[13px] font-semibold">{p.counterparty}</span></div>
              {p.counterparty_people.length > 0 ? (
                <ul className="mt-2 space-y-1.5">{p.counterparty_people.map((x: any) => (
                  <li key={x.name} className="flex items-center gap-2 text-[12.5px]"><Avatar name={x.name} size={22} /><div className="min-w-0"><div className="truncate font-medium">{x.name}</div><div className="truncate text-[11.5px] text-faint">{x.title}</div></div></li>
                ))}</ul>
              ) : <p className="mt-1.5 text-[12px] text-faint">No one on their side named in sources.</p>}
              <Button variant="outline" size="xs" className="mt-3 w-full" onClick={research}>
                {p.counterparty_account_id ? <><ExternalLink />Open {p.counterparty}</> : <><RefreshCw />Research {p.counterparty} too</>}
              </Button>
            </div>
          </div>

          <div className="mt-3 flex items-start justify-between gap-3">
            <details className="min-w-0 flex-1 text-[12.5px]"><summary className="cursor-pointer text-muted hover:text-fg"><FileText className="mr-1 inline size-3.5" />{p.evidence.length} source{p.evidence.length === 1 ? "" : "s"} behind this</summary>
              <ul className="mt-2 space-y-2">
                {p.evidence.map((e: any, n: number) => (
                  <li key={n} className="border-l-2 border-saffron pl-3">
                    {e.quote && <q className="text-[13px] text-fg">{e.quote}</q>}
                    <div className="mt-0.5 text-[12px] text-faint">{e.published_at || "Undated"} · {SOURCE_LABEL[e.source_type] || e.source_type} · <a className="hover:text-fg hover:underline" href={e.url} target="_blank" rel="noreferrer">{e.title || e.url}</a></div>
                  </li>
                ))}
              </ul>
            </details>
            <div className="flex shrink-0 gap-1">
              <Button variant="ghost" size="xs" onClick={() => act(() => post(`/api/projects/${p.id}/feedback`, { verdict: confirmed ? "clear" : "confirmed" }))}><Check />{confirmed ? "Undo confirm" : "This is real"}</Button>
              <Button variant="ghost" size="xs" onClick={() => act(() => post(`/api/projects/${p.id}/feedback`, { verdict: "dismissed" }), "Hidden; future research will skip it")}><EyeOff />Not relevant</Button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

/* ------------------------------------------------------------ People (org chart) */

function PeopleTab({ id, onBrief }: any) {
  const { data: o } = useApi<any>(`/api/accounts/${id}/org`);
  const [hl, setHl] = useState("");
  if (!o) return <div className="p-6"><Skeleton className="h-40 w-full" /></div>;
  if (!o.nodes.length) return <div className="p-6"><Empty icon={<Users />} title="No people found yet">The org chart fills in from people named in sources and, with Apollo and the company's website, from its leadership team.</Empty></div>;
  const byId = Object.fromEntries(o.nodes.map((n: any) => [n.id, n]));
  const kids: Record<number, any[]> = {}; const hasParent = new Set<number>();
  o.edges.forEach((e: any) => { (kids[e.from] ||= []).push(e); hasParent.add(e.to); });
  const roots = o.nodes.filter((n: any) => !hasParent.has(n.id)).sort((a: any, b: any) => a.rank - b.rank);
  const inits = [...new Map(o.nodes.flatMap((n: any) => n.initiatives).map((i: any) => [String(i.id), i])).values()] as any[];

  const Node = ({ n, kind, depth }: any) => {
    const dim = hl && !n.initiatives.some((i: any) => String(i.id) === hl);
    return (
      <div>
        <div className="flex items-stretch" style={{ paddingLeft: depth * 28 }}>
          {depth > 0 && <span className={cn("mr-2 w-4 border-b-2 border-l-2 rounded-bl-md mb-[22px]", kind === "confirmed" ? "border-ink" : "border-dashed border-[#c5c7d6]")} />}
          <button onClick={() => onBrief({ person_id: n.id, full_name: n.name, title: n.title })}
            className={cn("my-1 flex min-w-[300px] items-center gap-2.5 rounded-lg border border-line bg-white px-3 py-2 text-left transition-opacity hover:border-[#d5d5dc]", dim && "opacity-30")}>
            <Avatar name={n.name} size={30} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 font-medium">{n.name}{n.source === "evidence" && <Badge tone="green">In sources</Badge>}</div>
              <div className="truncate text-[12px] text-faint">{n.title} · {n.function}</div>
              {n.initiatives.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{n.initiatives.map((i: any) => <Badge key={i.id} tone={ROLE_TONE[i.role]}>{i.role} · {i.name}</Badge>)}</div>}
            </div>
          </button>
        </div>
        {(kids[n.id] || []).sort((a, b) => byId[a.to].rank - byId[b.to].rank).map((e) => <Node key={e.to} n={byId[e.to]} kind={e.kind} depth={depth + 1} />)}
      </div>
    );
  };
  return (
    <div className="p-6">
      <div className="mb-4 flex flex-wrap items-center gap-4 text-[12.5px] text-muted">
        <span>{o.nodes.length} people · <b className="text-fg">{o.confirmed}</b> reporting lines confirmed by a source · <b className="text-fg">{o.inferred}</b> inferred from titles</span>
        <span className="inline-flex items-center gap-1.5"><i className="w-5 border-t-2 border-ink" />confirmed</span>
        <span className="inline-flex items-center gap-1.5"><i className="w-5 border-t-2 border-dashed border-[#c5c7d6]" />inferred</span>
        {inits.length > 0 && <label className="ml-auto flex items-center gap-2">Highlight
          <select value={hl} onChange={(e) => setHl(e.target.value)} className="h-7 rounded-md border border-line bg-white px-2 text-[12.5px]">
            <option value="">all initiatives</option>{inits.map((i) => <option key={i.id} value={String(i.id)}>{i.name}</option>)}</select></label>}
      </div>
      <div className="rounded-lg border border-line bg-white p-4">{roots.map((r: any) => <Node key={r.id} n={r} depth={0} />)}</div>
    </div>
  );
}

/* ------------------------------------------------------------ Footprint */

const LOC_TYPE: Record<string, string> = { hq: "Headquarters", office: "Office", rd_centre: "R&D centre", engineering_centre: "Engineering centre", gcc: "Global capability centre", delivery_centre: "Delivery centre", plant: "Plant", other: "Site" };

function FootprintTab({ id }: any) {
  const { data: f } = useApi<any>(`/api/accounts/${id}/footprint`);
  if (!f) return <div className="p-6"><Skeleton className="h-40 w-full" /></div>;
  const max = Math.max(1, ...f.hiring.map((h: any) => h.roles));
  return (
    <div className="grid grid-cols-1 gap-5 p-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <Panel title="Sites">
        {f.sites.length ? <Table><thead><tr><Th className="pl-3">Location</Th><Th>Type</Th><Th>What happens there</Th><Th className="text-right">People</Th><Th className="pr-3">Source</Th></tr></thead>
          <tbody>{f.sites.map((s: any, n: number) => (
            <Tr key={n}><Td className="pl-3 font-medium">{[s.city, s.country].filter(Boolean).join(", ")}</Td><Td><Badge tone={s.type === "hq" ? "ink" : s.type === "gcc" || s.type.includes("centre") ? "violet" : "gray"}>{LOC_TYPE[s.type] || s.type}</Badge></Td>
              <Td><div className="flex flex-wrap gap-1">{s.functions.map((x: string) => <Badge key={x} tone="outline">{x}</Badge>)}</div></Td>
              <Td className="text-right tabular-nums">{s.headcount ? s.headcount.toLocaleString() : ""}</Td>
              <Td className="pr-3 text-[12px]">{s.url && <a className="text-sponsor hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.doc_title || "Source"}</a>}{s.quote && <div className="text-faint">“{s.quote}”</div>}</Td></Tr>))}</tbody></Table>
          : <p className="px-3 py-6 text-center text-muted">No sites mentioned in the sources yet.</p>}
      </Panel>
      <Panel title="Where they're hiring">
        {f.hiring.length ? <div className="space-y-2.5 p-3">{f.hiring.map((h: any) => (
          <div key={h.city} className="grid grid-cols-[120px_1fr_28px] items-center gap-3 text-[13px]">
            <span className="truncate">{h.city}{h.country && <span className="text-faint">, {h.country}</span>}</span>
            <div><span className="block h-2 overflow-hidden rounded-full bg-line-2"><i className="block h-full rounded-full bg-ink" style={{ width: `${(h.roles / max) * 100}%` }} /></span>
              <span className="text-[11.5px] text-faint">{h.functions.join(", ")}</span></div>
            <span className="text-right font-semibold tabular-nums">{h.roles}</span>
          </div>))}</div>
          : <p className="px-3 py-6 text-center text-muted">No job posts with locations yet.</p>}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------ Vendors & deals */

function DealsTab({ id }: any) {
  const { data: t } = useApi<any>(`/api/accounts/${id}/tech`);
  if (!t) return <div className="p-6"><Skeleton className="h-40 w-full" /></div>;
  const rel: Record<string, string> = { selected: "Selected", partner: "Partner", incumbent: "Current vendor", replacing: "Being replaced", evaluating: "Evaluating" };
  const dt: Record<string, [string, any]> = { new: ["New deal", "green"], renewal: ["Renewal", "violet"], expansion: ["Expansion", "saffron"], ended: ["Ended", "red"] };
  const onSite = (x: any) => x.source === "website" || x.source === "builtwith";
  const site = t.tech.filter(onSite), mentioned = t.tech.filter((x: any) => !onSite(x));
  const groups: Record<string, string[]> = {};
  site.forEach((x: any) => (groups[(x.category || "Other").split(", ")[0]] ||= []).push(x.name));
  return (
    <div className="space-y-5 p-6">
      <Panel title="Deal history">
        {t.vendors.length ? <Table><thead><tr><Th className="pl-3">When</Th><Th>Vendor</Th><Th>What for</Th><Th>Deal</Th><Th>Value</Th><Th className="pr-3">Source</Th></tr></thead>
          <tbody>{t.vendors.map((v: any, n: number) => (
            <Tr key={n} className={cn(v.is_competitor && "bg-saffron-soft/40")}>
              <Td className="pl-3 whitespace-nowrap tabular-nums text-muted">{v.deal_date || v.published_at || ""}</Td>
              <Td><div className="flex items-center gap-2"><Avatar name={v.name} size={22} square /><div><div className="font-medium">{v.name}{v.is_competitor ? <Badge tone="saffron" className="ml-1.5">Competitor</Badge> : null}</div><div className="text-[12px] text-faint">{rel[v.relationship] || v.relationship}</div></div></div></Td>
              <Td className="max-w-[260px]">{v.area}</Td>
              <Td>{v.deal_type && <Badge tone={dt[v.deal_type]?.[1]}>{dt[v.deal_type]?.[0]}</Badge>}{v.duration && <div className="text-[12px] text-faint">{v.duration}</div>}</Td>
              <Td className="whitespace-nowrap">{v.deal_value}</Td>
              <Td className="pr-3 max-w-[280px] text-[12px]">{v.url && <a className="text-sponsor hover:underline" href={v.url} target="_blank" rel="noreferrer">{v.doc_title || "Source"}</a>}{v.quote && <div className="line-clamp-2 text-faint">“{v.quote}”</div>}</Td>
            </Tr>))}</tbody></Table>
          : <p className="px-3 py-6 text-center text-muted">No vendor deals mentioned in the sources yet.</p>}
      </Panel>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Tech they mention (job posts, blogs, news)">
          <div className="flex flex-wrap gap-1.5 p-3">{mentioned.length ? mentioned.map((x: any) => x.url
            ? <a key={x.name} href={x.url} target="_blank" rel="noreferrer"><Badge tone="outline" className="hover:border-[#cfcfd6]">{x.name}</Badge></a>
            : <Badge key={x.name} tone="outline">{x.name}</Badge>) : <span className="text-muted">Nothing mentioned yet.</span>}</div>
        </Panel>
        <Panel title="On their website (detected from its code)">
          {Object.keys(groups).length ? <div className="divide-y divide-line-2">{Object.entries(groups).sort().map(([cat, names]) => (
            <div key={cat} className="grid grid-cols-[140px_1fr] gap-3 px-3 py-2"><span className="text-[12px] text-faint">{cat}</span><div className="flex flex-wrap gap-1">{names.map((n) => <Badge key={n} tone="gray">{n}</Badge>)}</div></div>))}</div>
            : <p className="px-3 py-6 text-center text-muted">Nothing detected yet. Add the company's website and research again.</p>}
        </Panel>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ Changes */

function ChangesTab({ id, company, every, onRead }: any) {
  const { data } = useApi<any>(`/api/alerts?company_id=${id}`);
  useEffect(() => { if (data?.alerts?.some((a: any) => !a.read)) post("/api/alerts/read", { company_id: id }).then(onRead); }, [data]); // eslint-disable-line
  if (!data) return <div className="p-6"><Skeleton className="h-40 w-full" /></div>;
  return (
    <div className="p-6">
      {data.alerts.length ? <AlertList alerts={data.alerts} /> : (
        <Empty icon={<Activity />} title="No changes yet">
          {company.watch ? `${company.name} is re-checked every ${every} days. New initiatives, stage changes, new leaders, hiring surges and new vendors show up here.`
            : `Turn on Watch weekly and ${company.name} is re-checked every ${every} days. Anything new shows up here.`}
        </Empty>
      )}
    </div>
  );
}

const ALERT_TONE: Record<string, any> = { new_initiative: "green", stage_change: "saffron", new_leader: "violet", hiring_surge: "amber", new_vendor: "gray" };
export function AlertList({ alerts, withCompany = false }: { alerts: any[]; withCompany?: boolean }) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white">
      {alerts.map((a) => (
        <div key={a.id} onClick={() => withCompany && go(`/a/${a.company_id}/changes`)}
          className={cn("grid grid-cols-[120px_1fr_auto] items-start gap-4 border-b border-line-2 px-4 py-3 last:border-0", withCompany && "cursor-pointer hover:bg-canvas", !a.read && "bg-saffron-soft/30")}>
          <Badge tone={ALERT_TONE[a.kind]} className="justify-self-start">{ALERT_LABEL[a.kind] || a.kind}</Badge>
          <div className="min-w-0"><div className="font-medium">{withCompany && <span className="text-muted">{a.company} · </span>}{a.title}</div>{a.detail && <div className="mt-0.5 text-[12.5px] text-muted">{a.detail}</div>}</div>
          <span className="text-[12px] tabular-nums text-faint">{day(a.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

export { ExternalLink };
