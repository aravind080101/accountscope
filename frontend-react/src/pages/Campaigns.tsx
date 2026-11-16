import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Building2, ExternalLink, FileText, Globe, Loader2, Megaphone, Plus, Radar, Sparkles, Trash2, Upload, Wand2 } from "lucide-react";
import { api, post } from "@/lib/api";
import { go, useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select } from "@/components/ui/input";
import { Avatar, Checkbox, Empty, Tooltip } from "@/components/ui/misc";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { LocationPicker } from "@/components/LocationPicker";
import { confirmCost } from "@/components/CostConfirm";
import { PitchSheet, ScorePill } from "@/components/PitchSheet";

export default function CampaignsPage({ id, refresh }: { id?: number; refresh: () => void }) {
  return id ? <CampaignDetail id={id} refresh={refresh} /> : <CampaignList />;
}

/* ------------------------------------------------------------------ list */

function CampaignList() {
  const { data, reload } = useApi<any[]>("/api/campaigns");
  const [name, setName] = useState(""); const [desc, setDesc] = useState(""); const [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true);
    try { const c = await post<any>("/api/campaigns", { name, description: desc }); setName(""); setDesc(""); reload(); go(`/campaigns/${c.id}`); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-6"><Megaphone className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Campaigns</h1></header>
      <div className="flex-1 overflow-auto bg-canvas p-6">
        <p className="mb-4 max-w-[760px] text-[13px] text-muted">A campaign is a set of decks and documents for one push (a vertical, an offering, an event). Its profile, its company search and its outreach use only its own documents, separate from your general library.</p>
        <div className="mb-6 grid max-w-[760px] gap-3 rounded-lg border border-line bg-white p-4 md:grid-cols-[1fr_1.4fr_auto] md:items-end">
          <div><Label>New campaign</Label><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Banking migrations Q1" /></div>
          <div><Label>What it's about (optional)</Label><Input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="e.g. Indian banks moving core or net banking platforms" /></div>
          <Button onClick={create} disabled={busy || !name.trim()}>{busy ? <Loader2 className="animate-spin" /> : <Plus />}Create</Button>
        </div>
        {!data ? <Loader2 className="size-5 animate-spin text-muted" /> : !data.length ? (
          <Empty icon={<Megaphone />} title="No campaigns yet">Create one, add its decks, then find companies that need it.</Empty>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.map((c) => (
            <a key={c.id} href={`#/campaigns/${c.id}`} className="rounded-lg border border-line bg-white p-4 hover:border-ink/30">
              <div className="flex items-center gap-2"><b className="text-[14px] font-semibold">{c.name}</b>{!c.has_profile && <Badge tone="saffron">Needs profile</Badge>}</div>
              {c.description && <p className="mt-1 line-clamp-2 text-[12.5px] text-muted">{c.description}</p>}
              <div className="mt-3 flex gap-4 text-[12px] text-muted"><span>{c.docs} doc{c.docs === 1 ? "" : "s"}</span><span>{c.accounts} compan{c.accounts === 1 ? "y" : "ies"}</span><span>{c.pitches} pitch{c.pitches === 1 ? "" : "es"}</span></div>
            </a>))}</div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ one campaign */

function CampaignDetail({ id, refresh }: { id: number; refresh: () => void }) {
  const { data: c, reload } = useApi<any>(`/api/campaigns/${id}`, [], (d) => d?.accounts?.some((a: any) => a.status === "queued" || a.status === "running"), 5000);
  const [busy, setBusy] = useState("");
  const [url, setUrl] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [opts, setOpts] = useState<any>(null);
  const [region, setRegion] = useState<string[]>(["India"]); const [days, setDays] = useState(30);
  const [signals, setSignals] = useState<string[]>([]); const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [hits, setHits] = useState<any[] | null>(null); const [picked, setPicked] = useState<Record<string, any>>({});
  const [pitchOpen, setPitchOpen] = useState<any>(null);
  const { data: pitches, reload: reloadPitches } = useApi<any[]>(`/api/pitches?campaign_id=${id}`, [], (d) => d?.some((p) => p.status === "queued" || p.status === "running"), 4000);

  useEffect(() => { api("/api/discover/options").then(setOpts); }, []);
  useEffect(() => {
    const s: string[] = c?.profile?.search_signals || [];
    setSignals(s); setChosen(Object.fromEntries(s.slice(0, 3).map((x) => [x, true])));
    if (c?.profile?.target_regions?.length) setRegion(c.profile.target_regions);
  }, [c?.profile]); // eslint-disable-line

  if (!c) return <div className="p-6"><Loader2 className="size-5 animate-spin text-muted" /></div>;
  const p = c.profile;

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy("upload");
    const fd = new FormData(); Array.from(files).forEach((f) => fd.append("files", f));
    try { const r = await api<any>(`/api/campaigns/${id}/sources`, { method: "POST", body: fd }); r.errors?.forEach((e: string) => toast.error(e)); if (r.added?.length) toast.success(`Added ${r.added.length} file${r.added.length === 1 ? "" : "s"}`); reload(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };
  const addUrl = async () => {
    setBusy("url");
    try { await post(`/api/campaigns/${id}/sources/url`, { url: url.trim() }); setUrl(""); reload(); toast.success("Page added"); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };
  const removeSource = async (sid: number) => { try { await api(`/api/campaigns/${id}/sources/${sid}`, { method: "DELETE" }); reload(); } catch (e: any) { toast.error(e.message); } };
  const build = async () => {
    setBusy("build");
    try { await post(`/api/campaigns/${id}/profile`); toast.success("Campaign profile built from its documents"); reload(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };
  const find = async () => {
    const qs = signals.filter((s) => chosen[s]);
    if (!qs.length) return toast.error("Pick at least one search");
    setBusy("find"); setPicked({});
    try { const r = await post<any>(`/api/campaigns/${id}/find`, { region, days, signals: qs }); setHits(r.companies); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };
  const addPicked = async () => {
    const companies = Object.values(picked).map((h: any) => ({ name: h.name, domain: h.domain || null, signal: h.signal, source_url: h.source_url }));
    setBusy("add");
    try { const r = await post<any>(`/api/campaigns/${id}/accounts`, { companies }); toast.success(`Added ${r.linked} to the campaign${r.researching ? `; researching ${r.researching}` : ""}`); setPicked({}); setHits(null); reload(); refresh(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };
  const writePitches = async (a: any) => {
    if (!(await confirmCost(`/api/accounts/${a.company_id}/pitches/cost`, `Write "${c.name}" outreach for the best contacts at ${a.name}?`, "Write pitches"))) return;
    try { const r = await post<any>(`/api/campaigns/${id}/accounts/${a.company_id}/pitches`, { limit: 5, min_fit: 0.5 }); toast.success(`Writing ${r.queued} campaign pitch${r.queued === 1 ? "" : "es"}`); reload(); reloadPitches(); }
    catch (e: any) { toast.error(e.message); }
  };
  const unlink = async (a: any) => { try { await api(`/api/campaigns/${id}/accounts/${a.company_id}`, { method: "DELETE" }); reload(); } catch (e: any) { toast.error(e.message); } };
  const del = async () => {
    if (!confirm(`Delete the "${c.name}" campaign and its documents? Researched companies stay; its pitches move to general outreach.`)) return;
    try { await api(`/api/campaigns/${id}`, { method: "DELETE" }); go("/campaigns"); } catch (e: any) { toast.error(e.message); }
  };
  const n = Object.keys(picked).length;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-6">
        <Button variant="ghost" size="icon-sm" onClick={() => go("/campaigns")} aria-label="All campaigns"><ArrowLeft /></Button>
        <Megaphone className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">{c.name}</h1>
        {c.description && <span className="truncate text-[13px] text-muted">{c.description}</span>}
        <Button variant="ghost" size="sm" className="ml-auto text-muted" onClick={del}><Trash2 />Delete</Button>
      </header>
      <div className="flex-1 space-y-5 overflow-auto bg-canvas p-6 pb-24">

        {/* 1. documents + profile */}
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-line bg-white p-4">
            <div className="mb-2 flex items-center justify-between"><h2 className="text-[12px] font-semibold uppercase tracking-wide text-muted">1 · Campaign decks & documents</h2>
              <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={!!busy}>{busy === "upload" ? <Loader2 className="animate-spin" /> : <Upload />}Upload</Button>
              <input ref={fileRef} type="file" multiple accept=".pdf,.pptx,.docx,.txt,.md" className="hidden" onChange={(e) => upload(e.target.files)} /></div>
            <div className="flex gap-1.5"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Or paste a page link (case study, landing page)" className="text-[12px]" />
              <Button size="sm" variant="outline" onClick={addUrl} disabled={!!busy || !url.trim()}>{busy === "url" ? <Loader2 className="animate-spin" /> : <Globe />}Add</Button></div>
            <ul className="mt-3 space-y-1">{c.sources.map((s: any) => (
              <li key={s.id} className="flex items-center gap-2 rounded-md border border-line-2 px-2.5 py-1.5 text-[13px]">
                {s.url ? <Globe className="size-3.5 shrink-0 text-muted" /> : <FileText className="size-3.5 shrink-0 text-muted" />}
                <span className="flex-1 truncate">{s.name}</span><span className="text-[11.5px] text-faint">{Math.round(s.chars / 1000)}k chars</span>
                <Button variant="ghost" size="icon-sm" aria-label={`Remove ${s.name}`} onClick={() => removeSource(s.id)}><Trash2 /></Button></li>))}
              {!c.sources.length && <li className="text-[12.5px] text-faint">No documents yet. These stay in this campaign only.</li>}</ul>
            <Button size="sm" className="mt-3 w-full" onClick={build} disabled={!!busy || !c.sources.length}>{busy === "build" ? <Loader2 className="animate-spin" /> : <Sparkles />}{p ? "Rebuild" : "Build"} campaign profile from {c.sources.length} document{c.sources.length === 1 ? "" : "s"}</Button>
          </div>
          <div className="rounded-lg border border-line bg-white p-4 text-[13px]">
            <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">Campaign profile</h2>
            {!p ? <p className="text-muted">Build it from the documents. Pitches in this campaign use only these offerings, proof and offers; your company name, voice and leadership views still come from your main profile.</p> : (<>
              <p>{p.description}</p>
              <div className="mt-2 space-y-1.5">{(p.offerings || []).map((o: any) => <div key={o.name}><b className="font-medium">{o.name}</b> <span className="text-muted">· {o.what}</span></div>)}</div>
              {p.target_industries?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{p.target_industries.map((x: string) => <Badge key={x} tone="outline">{x}</Badge>)}</div>}
              {p.proof?.length > 0 && <p className="mt-2 text-[12px] text-muted">Proof: {p.proof.slice(0, 3).join(" · ")}</p>}
            </>)}
          </div>
        </section>

        {/* 2. find companies */}
        <section className="rounded-lg border border-line bg-white p-4">
          <h2 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted">2 · Find companies that need this</h2>
          {!p ? <p className="text-[13px] text-muted">Build the campaign profile first. The searches come from what these documents sell.</p> : (<>
            <p className="mb-2 text-[12.5px] text-muted">Searches planned from the documents. Each runs through the signal radar (recent news and job posts); pick up to 3.</p>
            <div className="mb-3 flex flex-wrap gap-1.5">{signals.map((s) => (
              <button key={s} onClick={() => setChosen((x) => ({ ...x, [s]: !x[s] }))} className={cn("h-7 rounded-full border px-3 text-[12.5px] font-medium", chosen[s] ? "border-ink bg-ink text-white" : "border-line bg-white text-muted hover:text-fg")}>{s}</button>))}</div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-[1.4fr_140px_auto] md:items-end">
              <div><Label>Regions</Label><LocationPicker value={region} onChange={setRegion} groups={opts?.locations} /></div>
              <div><Label>News from the last</Label><Select value={days} onChange={(e) => setDays(+e.target.value)} className="w-full">{[7, 30, 90, 180].map((d) => <option key={d} value={d}>{d} days</option>)}</Select></div>
              <Button onClick={find} disabled={!!busy}>{busy === "find" ? <Loader2 className="animate-spin" /> : <Radar />}Find companies</Button>
            </div>
            <p className="mt-1.5 text-[11.5px] text-faint">Each search uses about 2-4 Tavily searches and 1 AI call.</p>
            {busy === "find" && <div className="flex items-center gap-2 py-8 text-muted"><Loader2 className="size-4 animate-spin text-saffron" />Reading recent news and job posts…</div>}
            {hits && busy !== "find" && (hits.length ? (
              <div className="mt-4 overflow-hidden rounded-lg border border-line">
                <div className="flex items-center justify-between border-b border-line px-4 py-2 text-[13px]"><b>{hits.length} companies</b>
                  <Button variant="ghost" size="xs" onClick={() => setPicked(Object.fromEntries(hits.filter((h) => !h.in_campaign).map((h) => [h.name, h])))}>Select all new</Button></div>
                <Table><thead><tr><Th className="w-10 pl-4"></Th><Th>Company</Th><Th>Why it fits now</Th><Th>Source</Th></tr></thead>
                  <tbody>{hits.map((h) => (
                    <Tr key={h.name}>
                      <Td className="pl-4"><Checkbox checked={!!picked[h.name]} disabled={h.in_campaign} onCheckedChange={() => setPicked((s) => { const x = { ...s }; if (x[h.name]) delete x[h.name]; else x[h.name] = h; return x; })} /></Td>
                      <Td><div className="flex items-center gap-2.5"><Avatar name={h.name} size={26} square /><div><div className="font-medium">{h.name}{h.in_campaign && <Badge tone="green" className="ml-1.5">In campaign</Badge>}{h.account_id && !h.in_campaign && <Badge tone="outline" className="ml-1.5">Researched</Badge>}</div>
                        <div className="text-[12px] text-faint">{[h.location || h.country, h.domain].filter(Boolean).join(" · ")}</div></div></div></Td>
                      <Td className="max-w-[460px]">{h.signal}{h.matched?.length > 1 && <div className="mt-0.5 text-[11.5px] text-faint">Matched {h.matched.length} searches</div>}</Td>
                      <Td className="max-w-[220px] text-[12px]">{h.source_url && <a className="inline-flex items-center gap-1 text-muted hover:text-fg" href={h.source_url} target="_blank" rel="noreferrer"><span className="line-clamp-1">{h.source_title || "Source"}</span><ExternalLink className="size-3 shrink-0" /></a>}<div className="text-faint">{h.published_at}</div></Td>
                    </Tr>))}</tbody></Table>
              </div>) : <Empty title="No companies found">Try other searches, a wider region or a longer window.</Empty>)}
          </>)}
        </section>

        {/* 3. companies in the campaign */}
        <section className="rounded-lg border border-line bg-white">
          <h2 className="border-b border-line px-4 py-3 text-[12px] font-semibold uppercase tracking-wide text-muted">3 · Companies in this campaign ({c.accounts.length})</h2>
          {!c.accounts.length ? <p className="px-4 py-4 text-[13px] text-muted">Add companies from the search above. New ones are researched automatically.</p> : (
            <Table><thead><tr><Th className="pl-4">Company</Th><Th>Why it's in the campaign</Th><Th>Research</Th><Th className="text-right">Pitches</Th><Th className="pr-4" /></tr></thead>
              <tbody>{c.accounts.map((a: any) => (
                <Tr key={a.company_id}>
                  <Td className="pl-4"><a href={`#/a/${a.company_id}`} className="flex items-center gap-2.5 hover:underline"><Avatar name={a.name} size={24} square /><span className="font-medium">{a.name}</span></a></Td>
                  <Td className="max-w-[420px] text-[12.5px] text-muted">{a.signal}</Td>
                  <Td>{a.status === "done" ? <Badge tone="green">Ready</Badge> : a.status === "failed" ? <Badge tone="red">Failed</Badge> : a.status ? <Badge tone="saffron"><Loader2 className="size-3 animate-spin" />{a.status}</Badge> : <Badge tone="outline">Not researched</Badge>}</Td>
                  <Td className="text-right tabular-nums">{a.pitches}</Td>
                  <Td className="pr-4"><div className="flex items-center justify-end gap-1">
                    <Tooltip content="Write this campaign's outreach to the best contacts here"><span><Button size="xs" variant="outline" disabled={a.status !== "done" || !p} onClick={() => writePitches(a)}><Wand2 />Write pitches</Button></span></Tooltip>
                    <Tooltip content="Remove from this campaign (the account stays)"><Button variant="ghost" size="icon-sm" aria-label={`Remove ${a.name}`} onClick={() => unlink(a)}><Trash2 /></Button></Tooltip></div></Td>
                </Tr>))}</tbody></Table>
          )}
        </section>

        {/* 4. campaign outreach */}
        <section className="rounded-lg border border-line bg-white">
          <h2 className="border-b border-line px-4 py-3 text-[12px] font-semibold uppercase tracking-wide text-muted">4 · Campaign outreach ({pitches?.length || 0})</h2>
          {!pitches?.length ? <p className="px-4 py-4 text-[13px] text-muted">Pitches written here use only this campaign's documents. They also appear on the Outreach page under this campaign, separate from your general pitches.</p> : (
            <Table><thead><tr><Th className="pl-4">Person</Th><Th>Company</Th><Th>Connection note</Th><Th>Score</Th><Th className="pr-4">Status</Th></tr></thead>
              <tbody>{pitches.map((x: any) => (
                <Tr key={x.id} className="cursor-pointer" onClick={() => setPitchOpen({ ...x, pitch_id: x.id, campaign_id: id, campaign: c.name })}>
                  <Td className="pl-4"><div className="font-medium">{x.full_name}</div><div className="text-[12px] text-faint">{x.title}</div></Td>
                  <Td className="text-muted"><span className="inline-flex items-center gap-1.5"><Building2 className="size-3.5" />{x.company}</span></Td>
                  <Td className="max-w-[420px] text-[12.5px] text-muted"><span className="line-clamp-2">{x.connection_note}</span></Td>
                  <Td><ScorePill v={x.score} /></Td>
                  <Td className="pr-4">{x.status === "queued" || x.status === "running" ? <Badge tone="saffron"><Loader2 className="size-3 animate-spin" />{x.status}</Badge> : <Badge tone={x.status === "approved" ? "green" : x.status === "failed" ? "red" : "outline"}>{x.status}</Badge>}</Td>
                </Tr>))}</tbody></Table>
          )}
        </section>
      </div>

      {n > 0 && (
        <div className="fixed bottom-5 left-[calc(50%+124px)] z-40 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-ink py-2 pl-4 pr-2 text-[13px] text-white shadow-2xl">
          <Badge tone="saffron">{n}</Badge>selected
          <Button variant="accent" size="sm" onClick={addPicked} disabled={busy === "add"}>{busy === "add" ? <Loader2 className="animate-spin" /> : <Plus />}Add to campaign & research</Button>
          <Button variant="ghost" size="sm" className="text-rail hover:bg-ink-3 hover:text-white" onClick={() => setPicked({})}>Clear</Button>
        </div>
      )}
      <PitchSheet person={pitchOpen} onClose={() => setPitchOpen(null)} onChanged={reloadPitches} />
    </div>
  );
}
