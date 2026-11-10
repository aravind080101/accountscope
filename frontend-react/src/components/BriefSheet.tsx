import { useEffect, useState } from "react";
import { Brain, ClipboardPaste, Loader2, MessageCircle, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import * as D from "@radix-ui/react-dialog";
import { api, post } from "@/lib/api";
import { confirmCost } from "@/components/CostConfirm";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SheetContent } from "@/components/ui/dialog";
import { Avatar, Tooltip } from "@/components/ui/misc";
import { Select, Textarea } from "@/components/ui/input";

const STYLE: Record<string, string> = { "data-driven": "Data-driven", visionary: "Visionary", pragmatic: "Pragmatic", technical: "Technical", "relationship-led": "Relationship-led", unknown: "Not enough to tell" };

export function BriefSheet({ person, onClose, onBuilt }: { person: any; onClose: () => void; onBuilt?: () => void }) {
  const [b, setB] = useState<any>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [none, setNone] = useState(false);
  const pid = person?.person_id;
  const build = async (force = false) => {
    if (!(await confirmCost(`/api/people/${pid}/cost?action=brief${force ? "&force=true" : ""}`, `${b ? "Refresh" : "Build"} ${person.full_name}'s buyer brief?`, b ? "Refresh brief" : "Build brief"))) return;
    setBusy(true); setErr(""); setNone(false);
    try { setB(await post(`/api/people/${pid}/brief${force ? "?force=true" : ""}`)); onBuilt?.(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  useEffect(() => {
    if (!pid) return;
    setB(null); setErr(""); setNone(false);
    api(`/api/people/${pid}/brief`).then(setB).catch(() => setNone(true));
  }, [pid]); // eslint-disable-line

  const src = (n: number) => b?.sources?.find((s: any) => s.n === n);
  const List = ({ title, items }: { title: string; items?: any[] }) => items?.length ? (
    <div><div className="mb-1 text-[12px] font-semibold text-muted">{title}</div>
      <ul className="space-y-1 text-[13px]">{items.map((x, i) => {
        const text = typeof x === "string" ? x : x.text; const sn = typeof x === "string" ? undefined : x.source; const s = sn != null ? src(sn) : null;
        return (<li key={i} className="flex gap-1.5"><span className="text-faint">·</span><span>{text}{" "}
          {typeof x !== "string" && (s ? <a href={s.url} target="_blank" rel="noreferrer" className="whitespace-nowrap text-[11px] font-medium text-owner hover:underline">Their words ↗</a>
            : <span className="whitespace-nowrap text-[11px] text-faint">Role-typical</span>)}</span></li>);
      })}</ul></div>) : null;

  return (
    <D.Root open={!!person} onOpenChange={(v) => !v && onClose()}>
      {person && (
        <SheetContent title={<span className="flex items-center gap-2.5"><Avatar name={person.full_name} size={28} />{person.full_name}</span>} description={person.title}>
          {none && !busy && !b && (
            <div className="flex flex-col items-center gap-3 py-14 text-center">
              <Sparkles className="size-6 text-sponsor" />
              <p className="max-w-sm text-[13px] text-muted">The brief reads what this person has said in talks, podcasts, interviews and posts: what drives them, what worries them and how they talk.</p>
              <Button onClick={() => build()}><Sparkles />Build brief</Button>
            </div>)}
          {busy && !b && <div className="flex flex-col items-center gap-2 py-16 text-muted"><Loader2 className="size-5 animate-spin text-saffron" />Reading what they've said publicly…</div>}
          {err && <div className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</div>}
          {b && (
            <div className="space-y-5">
              <div className="flex items-center gap-2">
                <Badge tone="violet"><Sparkles className="size-3" />{STYLE[b.communication_style] || b.communication_style}</Badge>
                <Badge tone={b.confidence === "high" ? "green" : b.confidence === "low" ? "saffron" : "gray"}>{b.confidence} confidence</Badge>
                <Button variant="ghost" size="xs" className="ml-auto" onClick={() => build(true)} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <RefreshCw />}Refresh</Button>
              </div>
              <div><p className="text-[14px] font-medium leading-relaxed">{b.summary}</p>
                {b.style_note && <p className="mt-1 text-[12.5px] text-muted">{b.style_note}</p>}
                {b.note && <p className="mt-1 text-[12.5px] text-saffron-ink">{b.note}</p>}</div>
              <VoiceCard v={b.voice} />
              <PersonalityCard p={b.personality} src={src} />
              <Samples pid={pid} onChange={() => build(true)} busy={busy} />
              {b.topics?.length > 0 && (
                <div className="rounded-lg border border-line p-3"><div className="mb-2 text-[12px] font-semibold text-muted">What they've talked about</div>
                  <ul className="space-y-2">{b.topics.map((t: any, i: number) => { const s = src(t.source); return (
                    <li key={i}><div className="text-[13px] font-medium">{t.topic}</div>{t.quote && <q className="text-[12.5px] text-muted">{t.quote}</q>}
                      {s && <div className="text-[11.5px] text-faint">{t.date || s.published_at || ""} <a className="hover:text-fg hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></div>}</li>); })}</ul></div>
              )}
              {b.first_hand === 0 && <p className="rounded-md bg-saffron-soft px-3 py-2 text-[12.5px] text-saffron-ink">Nothing first-hand from this person was found, so the points below are typical for the role, not about them.</p>}
              <div className="grid grid-cols-2 gap-4">
                <List title="What they focus on" items={b.priorities} /><List title="What drives them" items={b.motivators} />
                <List title="What worries them" items={b.concerns} /><List title="Avoid" items={b.avoid} />
              </div>
              {b.approach?.length > 0 && <div className="rounded-lg border border-line bg-canvas p-3"><List title="How to open" items={b.approach} /></div>}
              <List title="Link to what you sell" items={b.talking_points} />
              {b.evidence?.length > 0 && (
                <div><div className="mb-1.5 text-[12px] font-semibold text-muted">In their words</div>
                  <ul className="space-y-2">{b.evidence.map((e: any, i: number) => { const s = src(e.source); return (
                    <li key={i} className="border-l-2 border-saffron pl-3"><q className="text-[13px]">{e.quote}</q>
                      {s && <div className="text-[12px] text-faint">{s.published_at || ""} <a className="hover:text-fg hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></div>}</li>); })}</ul></div>
              )}
              <SourceList sources={b.sources || []} />
              <p className="border-t border-line pt-3 text-[12px] text-faint">Built from {b.sources?.length || 0} source{b.sources?.length === 1 ? "" : "s"} on {(b.created_at || "").slice(0, 10)}. Professional statements only.</p>
            </div>
          )}
        </SheetContent>
      )}
    </D.Root>
  );
}


const VOICE_LABEL: Record<string, string> = { register: "Register", length: "Writes", directness: "Directness", evidence: "Makes points with", energy: "Energy", emoji_hashtags: "Emoji / hashtags" };

export function PersonalityCard({ p, src }: { p: any; src: (n: number) => any }) {
  if (!p) return (
    <div className="rounded-lg border border-line p-3 text-[12.5px] text-muted">
      <div className="mb-1 flex items-center gap-2 text-[12px] font-semibold"><Brain className="size-3.5" />Personality</div>
      This brief was built before personality reading existed. Click Refresh to add it.
    </div>);
  const traits = Object.values(p.traits || {}) as any[];
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-muted"><Brain className="size-3.5" />Personality
        <span className="ml-auto font-normal text-faint">{p.known ? `${p.known} of ${traits.length} traits read from their own words` : "nothing first-hand to judge from"}</span></div>
      {p.summary && <p className="mb-2.5 text-[13px] font-medium">{p.summary}</p>}
      <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {traits.map((t) => {
          const known = t.lean !== "unknown";
          const pos = t.lean === "left" ? 50 - (t.strength || 1) * 15 : t.lean === "right" ? 50 + (t.strength || 1) * 15 : 50;
          const s = t.source != null ? src(t.source) : null;
          const row = (
            <div className={known ? "" : "opacity-40"}>
              <div className="flex justify-between text-[11.5px]">
                <span className={t.lean === "left" ? "font-semibold text-fg" : "text-faint"}>{t.left}</span>
                <span className={t.lean === "right" ? "font-semibold text-fg" : "text-faint"}>{t.right}</span>
              </div>
              <div className="relative mt-1 h-1.5 rounded-full bg-line-2">
                {known && <span className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sponsor ring-2 ring-white" style={{ left: `${pos}%` }} />}
              </div>
            </div>);
          return <div key={t.left}>{known ? <Tooltip content={<span>"{t.quote}"{s?.title ? ` (${s.title})` : ""}</span>}>{s?.url ? <a href={s.url} target="_blank" rel="noreferrer" className="block">{row}</a> : row}</Tooltip>
            : <Tooltip content="Not enough of their own words to tell">{row}</Tooltip>}</div>;
        })}
      </div>
      {(p.values?.length > 0 || p.interests?.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {(p.values || []).map((x: any) => <Badge key={"v" + x.text} tone="violet">{x.text}</Badge>)}
          {(p.interests || []).map((x: any) => <Badge key={"i" + x.text} tone="gray">{x.text}</Badge>)}
        </div>)}
      {p.how_to_write?.length > 0 && (
        <div className="mt-3"><div className="mb-1 text-[11.5px] font-semibold text-muted">Write for this personality</div>
          <ul className="space-y-0.5 text-[12.5px]">{p.how_to_write.map((x: string) => <li key={x} className="flex gap-1.5"><span className="text-faint">·</span>{x}</li>)}</ul></div>)}
    </div>
  );
}

function VoiceCard({ v }: { v: any }) {
  if (!v) return null;
  const has = v.samples > 0;
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-muted"><MessageCircle className="size-3.5" />How they communicate
        <span className={has ? "ml-auto font-normal text-owner" : "ml-auto font-normal text-saffron-ink"}>{has ? `from ${v.samples} of their own texts` : "no first-hand writing yet"}</span></div>
      {has ? (<>
        {v.summary && <p className="text-[13px] font-medium">{v.summary}</p>}
        <div className="mt-2 flex flex-wrap gap-1.5">{Object.keys(VOICE_LABEL).filter((k) => v[k]).map((k) => <Badge key={k} tone="outline">{VOICE_LABEL[k]}: {v[k]}</Badge>)}</div>
        {v.vocabulary?.length > 0 && <div className="mt-2 text-[12.5px]"><span className="text-muted">Words they use: </span>{v.vocabulary.map((w: string) => <q key={w} className="mr-2">{w}</q>)}</div>}
        {v.how_they_reply && <div className="mt-1 text-[12.5px]"><span className="text-muted">How they reply: </span>{v.how_they_reply}</div>}
        <div className="mt-2 grid grid-cols-2 gap-3 text-[12.5px]">
          {v.mirror?.length > 0 && <div><div className="text-[11.5px] font-semibold text-owner">Write to them like this</div><ul className="list-disc pl-4">{v.mirror.map((m: string) => <li key={m}>{m}</li>)}</ul></div>}
          {v.avoid?.length > 0 && <div><div className="text-[11.5px] font-semibold text-danger">Tone to avoid</div><ul className="list-disc pl-4">{v.avoid.map((m: string) => <li key={m}>{m}</li>)}</ul></div>}
        </div>
      </>) : <p className="text-[12.5px] text-muted">No talks, interviews or writing of theirs turned up in search. Paste a few things they wrote or said below for a real read on their voice; until then pitches use a plain, neutral tone.</p>}
    </div>
  );
}

export function Samples({ pid, onChange, busy, actionLabel = "Re-read their voice", startOpen = false }: { pid: number; onChange: () => void; busy: boolean; actionLabel?: string; startOpen?: boolean }) {
  const [list, setList] = useState<any[]>([]); const [text, setText] = useState(""); const [kind, setKind] = useState("post"); const [open, setOpen] = useState(startOpen);
  const load = () => api<any[]>(`/api/people/${pid}/samples`).then(setList).catch(() => {});
  useEffect(() => { load(); }, [pid]); // eslint-disable-line
  const add = async () => { try { await post(`/api/people/${pid}/samples`, { text, kind }); setText(""); await load(); } catch (e: any) { alert(e.message); } };
  const del = async (id: number) => { await api(`/api/samples/${id}`, { method: "DELETE" }); load(); };
  return (
    <div className="rounded-lg border border-dashed border-line p-3">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left text-[12.5px] font-medium"><ClipboardPaste className="size-3.5 text-muted" />
        Paste things they wrote or said: posts, comments, replies, talk quotes<span className="ml-auto text-[12px] font-normal text-faint">{list.length} pasted</span></button>
      {open && (
        <div className="mt-2 space-y-2">
          <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="One post, comment, email reply or transcript excerpt from them (LinkedIn, X, a talk, a forum)" className="text-[12.5px]" />
          <div className="flex items-center gap-2">
            <Select value={kind} onChange={(e) => setKind(e.target.value)} className="h-7 w-32 text-[12px]">
              {["post", "comment", "reply", "article", "talk", "other"].map((k) => <option key={k} value={k}>{k}</option>)}
            </Select>
            <Button size="xs" variant="outline" onClick={add} disabled={text.trim().length < 20}>Add</Button>
            {list.length > 0 && <Button size="xs" className="ml-auto" onClick={onChange} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <RefreshCw />}{actionLabel}</Button>}
          </div>
          {list.length > 0 && <ul className="max-h-40 space-y-1 overflow-y-auto">{list.map((x) => (
            <li key={x.id} className="group flex gap-2 rounded bg-canvas px-2 py-1 text-[12px]"><Badge tone="gray">{x.kind}</Badge><span className="line-clamp-2 flex-1 text-muted">{x.text}</span>
              <button onClick={() => del(x.id)} className="text-faint opacity-0 hover:text-danger group-hover:opacity-100" aria-label="Remove"><Trash2 className="size-3.5" /></button></li>))}</ul>}
          <p className="text-[11.5px] text-faint">Two to five recent posts or comments are enough. Only their professional writing; it stays in this app.</p>
        </div>
      )}
    </div>
  );
}


const FAMILY: Record<string, { label: string; tone: any }> = {
  pasted: { label: "Pasted by you", tone: "green" }, talk: { label: "Talk / panel", tone: "green" }, podcast: { label: "Podcast / video", tone: "green" },
  interview: { label: "Interview", tone: "green" }, writing: { label: "Their writing", tone: "violet" }, company_site: { label: "Company site", tone: "violet" },
  profile: { label: "Bio / profile", tone: "gray" }, news: { label: "Quoted in news", tone: "outline" },
};

function SourceList({ sources }: { sources: any[] }) {
  if (!sources.length) return null;
  const counts: Record<string, number> = {};
  sources.forEach((x) => { const f = x.family || "profile"; counts[f] = (counts[f] || 0) + 1; });
  return (
    <details className="text-[12.5px]">
      <summary className="cursor-pointer text-muted">
        <span className="mr-2">Sources</span>
        {Object.entries(counts).map(([f, n]) => <Badge key={f} tone={FAMILY[f]?.tone || "gray"} className="mr-1">{FAMILY[f]?.label || f} {n}</Badge>)}
      </summary>
      <ul className="mt-2 space-y-1">{sources.map((x) => (
        <li key={x.n} className="flex items-center gap-2"><Badge tone={FAMILY[x.family]?.tone || "gray"}>{FAMILY[x.family]?.label || "Source"}</Badge>
          {x.url ? <a href={x.url} target="_blank" rel="noreferrer" className="truncate hover:underline">{x.title || x.url}</a> : <span className="truncate text-muted">{x.title}</span>}</li>))}</ul>
      <p className="mt-1 text-[11.5px] text-faint">Talks, podcasts, interviews and pasted text show how they really speak. Press quotes are usually polished, so they count least for voice.</p>
    </details>
  );
}
