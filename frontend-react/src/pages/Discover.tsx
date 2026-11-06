import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Compass, ExternalLink, Loader2, Radar, Search } from "lucide-react";
import { api, post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { go } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select } from "@/components/ui/input";
import { Avatar, Checkbox, Empty } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/tabs";
import { LocationPicker } from "@/components/LocationPicker";
import { Table, Td, Th, Tr } from "@/components/ui/table";

export default function DiscoverPage({ refresh }: any) {
  const [mode, setMode] = useState("radar");
  const [opts, setOpts] = useState<any>(null);
  const [preset, setPreset] = useState("qa_hiring"); const [query, setQuery] = useState(""); const [region, setRegion] = useState<string[]>(["India"]); const [days, setDays] = useState(30);
  const [hits, setHits] = useState<any[] | null>(null); const [scanning, setScanning] = useState(false);
  const [kw, setKw] = useState(""); const [loc, setLoc] = useState<string[]>([]); const [size, setSize] = useState(""); const [page, setPage] = useState(1);
  const [browse, setBrowse] = useState<any>(null); const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<Record<string, any>>({});
  useEffect(() => { api("/api/discover/options").then(setOpts); }, []);

  const scan = async () => {
    setScanning(true); setPicked({});
    try { setHits((await post<any>("/api/discover/signals", { preset: query ? null : preset, query, region, days })).companies); }
    catch (e: any) { toast.error(e.message); } finally { setScanning(false); }
  };
  const doBrowse = async (p = 1) => {
    setSearching(true); setPage(p); setPicked({});
    try { setBrowse(await post("/api/discover/companies", { keywords: kw, location: loc, size, page: p })); }
    catch (e: any) { toast.error(e.message); } finally { setSearching(false); }
  };
  const toggle = (c: any) => setPicked((s) => { const n = { ...s }; if (n[c.name]) delete n[c.name]; else n[c.name] = c; return n; });
  const research = async () => {
    const companies = Object.values(picked).map((p: any) => ({ name: p.name, domain: p.domain || null }));
    try { const r = await post<any>("/api/accounts/bulk", { companies }); toast.success(`Researching ${r.queued} ${r.queued === 1 ? "company" : "companies"}`); setPicked({}); refresh(); }
    catch (e: any) { toast.error(e.message); }
  };
  const n = Object.keys(picked).length;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-6">
        <Compass className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Discover</h1>
        <div className="ml-4"><Segmented value={mode} onChange={setMode} items={[["radar", "Signal radar"], ["browse", "Browse by filters"]]} /></div>
      </header>
      <div className="flex-1 bg-canvas p-6 pb-24">
        {mode === "radar" ? (<>
          <div className="rounded-lg border border-line bg-white p-4">
            <Label>What should the company be doing?</Label>
            <div className="mb-4 flex flex-wrap gap-1.5">
              {opts?.presets.map((p: any) => (
                <button key={p.id} onClick={() => { setPreset(p.id); setQuery(""); }} className={cn("h-7 rounded-full border px-3 text-[12.5px] font-medium", preset === p.id && !query ? "border-ink bg-ink text-white" : "border-line bg-white text-muted hover:text-fg")}>{p.label}</button>
              ))}
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-[2fr_1fr_140px_auto] md:items-end">
              <div><Label>Or describe your own signal</Label><Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. insurers launching customer portals" /></div>
              <div><Label>Regions</Label><LocationPicker value={region} onChange={setRegion} groups={opts?.locations} /></div>
              <div><Label>News from the last</Label><Select value={days} onChange={(e) => setDays(+e.target.value)} className="w-full">{[7, 30, 90].map((d) => <option key={d} value={d}>{d} days</option>)}</Select></div>
              <Button onClick={scan} disabled={scanning}>{scanning ? <Loader2 className="animate-spin" /> : <Radar />}Scan</Button>
            </div>
          </div>
          <div className="mt-5">
            {scanning ? <div className="flex flex-col items-center gap-2 py-16 text-muted"><Loader2 className="size-5 animate-spin text-saffron" />Reading recent news and job posts…</div>
              : hits === null ? <Empty icon={<Radar />} title="Pick a signal and scan">You'll get real companies showing it right now, each with a one-line reason and its source.</Empty>
              : !hits.length ? <Empty title="No companies found for that signal">{region.length ? "Only companies whose activity is in your chosen regions are shown. " : ""}Try a wider region, a longer window, or describe the signal in your own words.</Empty>
              : (
                <div className="overflow-hidden rounded-lg border border-line bg-white">
                  <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-[13px]"><b>{hits.length} companies showing this signal</b>
                    <Button variant="ghost" size="xs" onClick={() => setPicked(Object.fromEntries(hits.filter((h) => !h.account_id).map((h) => [h.name, h])))}>Select all new</Button></div>
                  <Table><thead><tr><Th className="w-10 pl-4"></Th><Th>Company</Th><Th>Signal</Th><Th>Source</Th><Th className="pr-4"></Th></tr></thead>
                    <tbody>{hits.map((h) => (
                      <Tr key={h.name}>
                        <Td className="pl-4"><Checkbox checked={!!picked[h.name]} disabled={!!h.account_id} onCheckedChange={() => toggle(h)} /></Td>
                        <Td><div className="flex items-center gap-2.5"><Avatar name={h.name} size={26} square /><div><div className="font-medium">{h.name}</div><div className="text-[12px] text-faint">{[h.location || h.country, h.domain].filter(Boolean).join(" · ")}</div></div></div></Td>
                        <Td className="max-w-[460px]">{h.signal}</Td>
                        <Td className="max-w-[220px] text-[12px]">{h.source_url && <a className="inline-flex items-center gap-1 text-muted hover:text-fg" href={h.source_url} target="_blank" rel="noreferrer"><span className="line-clamp-1">{h.source_title || "Source"}</span><ExternalLink className="size-3 shrink-0" /></a>}<div className="text-faint">{h.published_at}</div></Td>
                        <Td className="pr-4">{h.account_id && <Button variant="ghost" size="xs" onClick={() => go(`/a/${h.account_id}`)}>Researched</Button>}</Td>
                      </Tr>))}</tbody></Table>
                </div>
              )}
          </div>
        </>) : (<>
          <div className="rounded-lg border border-line bg-white p-4">
            {opts && !opts.browse && <div className="mb-3 rounded-md bg-saffron-soft px-3 py-2 text-[13px] text-saffron-ink">Browsing needs APOLLO_API_KEY in .env. The signal radar works without it.</div>}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-[2fr_1.2fr_160px_auto] md:items-end">
              <div><Label>Industry or keywords, comma separated</Label><Input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="e.g. banking, fintech" /></div>
              <div><Label>Locations</Label><LocationPicker value={loc} onChange={setLoc} groups={opts?.locations} /></div>
              <div><Label>Employees</Label><Select value={size} onChange={(e) => setSize(e.target.value)} className="w-full"><option value="">Any size</option>{opts?.sizes.map((s: string) => <option key={s}>{s}</option>)}</Select></div>
              <Button onClick={() => doBrowse(1)} disabled={searching || (opts && !opts.browse)}>{searching ? <Loader2 className="animate-spin" /> : <Search />}Search</Button>
            </div>
            <p className="mt-2 text-[12px] text-faint">Company search may use Apollo credits, depending on your plan.</p>
          </div>
          <div className="mt-5">
            {browse && (browse.companies.length ? (
              <div className="overflow-hidden rounded-lg border border-line bg-white">
                <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-[13px]"><b>{browse.total ? `${browse.total.toLocaleString()} companies` : "Companies"}</b>
                  <div className="flex items-center gap-2 text-muted">Page {browse.page}{browse.total_pages ? ` of ${browse.total_pages}` : ""}
                    <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => doBrowse(page - 1)}><ChevronLeft /></Button>
                    <Button variant="outline" size="icon-sm" disabled={browse.total_pages && page >= browse.total_pages} onClick={() => doBrowse(page + 1)}><ChevronRight /></Button></div></div>
                <Table><thead><tr><Th className="w-10 pl-4"></Th><Th>Company</Th><Th>Industry</Th><Th className="text-right">Employees</Th><Th>Location</Th><Th className="pr-4"></Th></tr></thead>
                  <tbody>{browse.companies.map((c: any) => (
                    <Tr key={c.name}><Td className="pl-4"><Checkbox checked={!!picked[c.name]} disabled={!!c.account_id} onCheckedChange={() => toggle(c)} /></Td>
                      <Td><div className="flex items-center gap-2.5"><Avatar name={c.name} size={26} square /><div><div className="font-medium">{c.name}</div><div className="text-[12px] text-faint">{c.domain}</div></div></div></Td>
                      <Td>{c.industry}</Td><Td className="text-right tabular-nums">{c.employees ? Number(c.employees).toLocaleString() : ""}</Td>
                      <Td>{[c.city, c.country].filter(Boolean).join(", ")}</Td>
                      <Td className="pr-4">{c.account_id && <Button variant="ghost" size="xs" onClick={() => go(`/a/${c.account_id}`)}>Researched</Button>}</Td></Tr>))}</tbody></Table>
              </div>) : <Empty title="No companies match those filters">Try fewer keywords or a wider location.</Empty>)}
          </div>
        </>)}
      </div>
      {n > 0 && (
        <div className="fixed bottom-5 left-[calc(50%+124px)] z-40 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-ink py-2 pl-4 pr-2 text-[13px] text-white shadow-2xl">
          <Badge tone="saffron">{n}</Badge>selected
          <Button variant="accent" size="sm" onClick={research}>Research {n === 1 ? "it" : `all ${n}`}</Button>
          <Button variant="ghost" size="sm" className="text-rail hover:bg-ink-3 hover:text-white" onClick={() => setPicked({})}>Clear</Button>
        </div>
      )}
    </div>
  );
}
