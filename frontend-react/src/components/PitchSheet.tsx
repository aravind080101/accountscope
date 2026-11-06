import { useEffect, useRef, useState } from "react";
import * as D from "@radix-ui/react-dialog";
import { toast } from "sonner";
import { Check, ChevronDown, Copy, Crosshair, Flame, Lightbulb, Loader2, MessageSquareQuote, RefreshCw, ShieldAlert, Swords, Target, Wand2 } from "lucide-react";
import { api, post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { SheetContent } from "@/components/ui/dialog";
import { Avatar } from "@/components/ui/misc";
import { Samples } from "@/components/BriefSheet";

const MSGS: { k: string; label: string; limit?: number; hint: string }[] = [
  { k: "connection_note", label: "Connection note", limit: 280, hint: "Sent with the invite. The hook, nothing to sell." },
  { k: "message_1", label: "Message 1", limit: 500, hint: "After they accept: one sharp insight and a question they'd want to answer. No meeting ask." },
];

export function PitchSheet({ person, onClose, onChanged }: { person: any; onClose: () => void; onChanged?: () => void }) {
  const pid = person?.person_id;
  const [p, setP] = useState<any>(null);
  const [none, setNone] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const timer = useRef<number>();

  const load = async (id?: number) => {
    try {
      const x = id ? await api(`/api/pitches/${id}`) : await api(`/api/people/${pid}/pitch`);
      setP(x); setNone(false); setDraft(x.data?.messages || {});
      clearTimeout(timer.current);
      if (x.status === "queued" || x.status === "running") timer.current = window.setTimeout(() => load(x.id), 1800);
      else onChanged?.();
    } catch { setNone(true); setP(null); }
  };
  useEffect(() => { if (pid) { setP(null); setNone(false); load(person.pitch_id); } return () => clearTimeout(timer.current); }, [pid]); // eslint-disable-line

  const start = async () => {
    try { const x = await post(`/api/people/${pid}/pitch`, { kind: person.context_kind, context_id: person.context_id }); setNone(false); load(x.id); }
    catch (e: any) { toast.error(e.message); }
  };
  const save = async (status?: string) => {
    try { const x = await api(`/api/pitches/${p.id}`, { method: "PUT", body: JSON.stringify({ messages: draft, status }) }); setP(x); toast.success(status === "approved" ? "Approved for Dripify" : "Saved"); onChanged?.(); }
    catch (e: any) { toast.error(e.message); }
  };
  const copy = (t: string) => { navigator.clipboard?.writeText(t); toast.success("Copied"); };
  const busy = p && (p.status === "queued" || p.status === "running");
  const d = p?.data || {};
  const sim = d.simulation || {};
  const dirty = p && JSON.stringify(draft) !== JSON.stringify(d.messages || {});

  return (
    <D.Root open={!!person} onOpenChange={(v) => !v && onClose()}>
      {person && (
        <SheetContent className="w-[min(760px,97vw)]"
          title={<span className="flex items-center gap-2.5"><Avatar name={person.full_name} size={28} />Pitch for {person.full_name}</span>}
          description={[person.title, person.company].filter(Boolean).join(" · ")}>
          {none && (
            <div className="flex flex-col items-center gap-3 py-14 text-center">
              <Wand2 className="size-6 text-saffron" />
              <p className="max-w-md text-[13px] text-muted">The agent reads what this person has said, finds where it meets what you sell, writes a Dripify sequence,
                then a simulated version of them pushes back until the messages would get a reply. Takes about a minute.</p>
              <Button onClick={start}><Wand2 />Write pitch</Button>
            </div>
          )}
          {!p && !none && <div className="flex justify-center py-16"><Loader2 className="size-5 animate-spin text-muted" /></div>}
          {busy && <AgentLog log={p.log} />}
          {p?.status === "failed" && <div className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger">{p.error}<Button size="xs" variant="outline" className="ml-3" onClick={start}>Try again</Button></div>}

          {p && !busy && p.status !== "failed" && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <ScorePill v={p.score} />
                <Badge tone={p.status === "approved" ? "green" : p.status === "exported" ? "violet" : "gray"}>{p.status}</Badge>
                <span className="text-[12px] text-muted">{d.rounds?.length} round{d.rounds?.length === 1 ? "" : "s"} with the simulated buyer · {d.research?.first_hand || 0} first-hand source{d.research?.first_hand === 1 ? "" : "s"}</span>
                {d.research?.voice?.samples > 0 ? <Badge tone="green">Written in their voice</Badge> : <Badge tone="saffron">Neutral tone (voice unknown)</Badge>}
                <Button size="xs" variant="ghost" className="ml-auto" onClick={start}><RefreshCw />Regenerate</Button>
              </div>
              {d.warnings?.length > 0 && <ul className="space-y-1 rounded-md bg-saffron-soft px-3 py-2 text-[12.5px] text-saffron-ink">{d.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
              {!d.research?.first_hand && (String(p.full_name || person.full_name).includes("*")
                ? <p className="rounded-md border border-dashed border-line px-3 py-2 text-[12.5px] text-muted">Their surname is hidden, so their posts can't be matched to them yet. Click <b>Get email</b> on their contact first, then paste their posts here and regenerate.</p>
                : <Samples pid={pid} onChange={start} busy={!!busy} actionLabel="Regenerate pitch with these" startOpen />)}

              {/* the hook */}
              <section className="rounded-lg border border-line p-4">
                <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><Target className="size-3.5" />The hook</div>
                <div className="text-[14.5px] font-semibold leading-snug">{d.angle?.hook}</div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <Badge tone={d.angle?.basis === "their_words" ? "green" : "gray"}>{d.angle?.basis === "their_words" ? "From their own words" : "From their company's work"}</Badge>
                  {d.angle?.offering && <Badge tone="outline">{d.angle.offering}</Badge>}
                  {d.angle?.offer && <Badge tone="saffron">Offer once they reply: {d.angle.offer}</Badge>}
                </div>
                {d.angle?.evidence && <q className="mt-2 block border-l-2 border-saffron pl-3 text-[12.5px] text-muted">{d.angle.evidence}</q>}
                {d.research?.voice?.samples > 0 && <p className="mt-2 text-[12.5px] text-muted"><b className="font-medium text-fg">Their voice:</b> {d.research.voice.summary} {(d.research.voice.mirror || []).join(" · ")}</p>}
                <dl className="mt-3 grid gap-2 text-[13px] sm:grid-cols-2">
                  <div><dt className="text-[11.5px] font-semibold text-muted">Technical insight</dt><dd>{d.angle?.technical_insight}</dd></div>
                  <div><dt className="text-[11.5px] font-semibold text-muted">Why they'd care</dt><dd>{d.angle?.why_they_care}</dd></div>
                  {d.angle?.conversation_starter && <div className="sm:col-span-2"><dt className="text-[11.5px] font-semibold text-muted">Conversation starter</dt><dd>{d.angle.conversation_starter}</dd></div>}
                  {d.angle?.proof && <div className="sm:col-span-2"><dt className="text-[11.5px] font-semibold text-muted">Proof used</dt><dd>{d.angle.proof}</dd></div>}
                </dl>
              </section>

              {/* what hits them + hooks tested */}
              {(d.triggers?.length > 0 || d.hooks?.length > 0) && (
                <section className="grid gap-3 lg:grid-cols-2">
                  {d.triggers?.length > 0 && (
                    <div className="rounded-lg border border-line p-4">
                      <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><Flame className="size-3.5" />What hits them</div>
                      <ul className="space-y-2.5">{d.triggers.map((t: any, i: number) => (
                        <li key={i}>
                          <div className="flex items-center gap-1.5"><Badge tone={TRIGGER_TONE[t.type] || "gray"}>{TRIGGER_LABEL[t.type] || t.type}</Badge>
                            {t.fresh && <Badge tone="saffron">fresh</Badge>}{t.basis === "their_words" && <Badge tone="green">their words</Badge>}
                            <span className="ml-auto flex items-center gap-1 text-[11px] text-faint"><span className="h-1.5 w-12 rounded bg-line"><span className="block h-1.5 rounded bg-danger" style={{ width: `${(Number(t.intensity) || 0) * 10}%` }} /></span>{t.intensity}</span></div>
                          <div className="mt-1 text-[13px] font-medium">{t.what}</div>
                          {t.evidence && <div className="text-[12px] text-muted">"{t.evidence}"</div>}
                        </li>))}</ul>
                      {d.dismiss_reasons?.length > 0 && <div className="mt-3 border-t border-line-2 pt-2"><div className="text-[11.5px] font-semibold text-muted">Why they usually ignore vendors (the pitch has to get past these)</div>
                        <ul className="mt-1 list-disc pl-4 text-[12.5px] text-muted">{d.dismiss_reasons.map((r: string) => <li key={r}>{r}</li>)}</ul></div>}
                    </div>
                  )}
                  {d.hooks?.length > 0 && (
                    <div className="rounded-lg border border-line p-4">
                      <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><Crosshair className="size-3.5" />Opening hooks tested</div>
                      <p className="mb-2 text-[12px] text-faint">They saw only the notification preview. The winner opens the connection note.</p>
                      <ul className="space-y-2">{d.hooks.map((h: any, i: number) => (
                        <li key={i} className={cn("rounded-md border p-2.5", i === 0 ? "border-owner/40 bg-owner-soft/40" : "border-line")}>
                          <div className="flex items-center gap-1.5 text-[11.5px]"><Badge tone={i === 0 ? "green" : "outline"}>{i === 0 ? "Winner · " : ""}{(h.style || "").replace(/_/g, " ")}</Badge>
                            {h.generic && <Badge tone="red">too generic</Badge>}
                            <span className="ml-auto font-semibold tabular-nums">{h.stop}/10</span>
                            <button onClick={() => copy(h.line)} className="text-faint hover:text-fg" aria-label="Copy hook"><Copy className="size-3.5" /></button></div>
                          <div className="mt-1 text-[13px]">{h.line}</div>
                          {h.reaction && <div className="mt-0.5 text-[12px] italic text-muted">"{h.reaction}"</div>}
                        </li>))}</ul>
                    </div>
                  )}
                </section>
              )}

              {/* the sequence */}
              <section>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-[12px] font-semibold uppercase tracking-wide text-muted">Messages</span>
                  <div className="ml-auto flex gap-1.5">
                    {dirty && <Button size="xs" variant="outline" onClick={() => save()}>Save edits</Button>}
                    <Button size="xs" onClick={() => save("approved")} disabled={p.status === "approved"}><Check />{p.status === "approved" ? "Approved" : "Approve"}</Button>
                  </div>
                </div>
                <div className="space-y-3">
                  {MSGS.map((m) => {
                    const v = draft[m.k] || ""; const over = m.limit && v.length > m.limit;
                    return (
                      <div key={m.k}>
                        <div className="mb-1 flex items-center gap-2 text-[12px]"><b className="font-semibold">{m.label}</b><span className="text-faint">{m.hint}</span>
                          <span className={cn("ml-auto tabular-nums", over ? "font-semibold text-danger" : "text-faint")}>{v.length}{m.limit ? `/${m.limit}` : ""}</span>
                          <button onClick={() => copy(v)} className="text-faint hover:text-fg" aria-label={`Copy ${m.label}`}><Copy className="size-3.5" /></button></div>
                        <Textarea rows={m.k === "connection_note" ? 3 : 5} value={v}
                          onChange={(e) => setDraft((x) => ({ ...x, [m.k]: e.target.value }))} className="text-[13px] leading-relaxed" />
                      </div>
                    );
                  })}
                </div>
              </section>

              {/* buyer simulator */}
              <section className="rounded-lg border border-line bg-canvas p-4">
                <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><Swords className="size-3.5" />How {person.full_name.split(" ")[0]} would react (simulated)</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Reaction label="Invite" ok={sim.connection?.accept} yes="Accepts" no="Ignores" text={sim.connection?.reaction} />
                  <Reaction label="Message 1" ok={sim.message_1?.reply} yes="Replies" no="No reply" text={sim.message_1?.reaction} />
                </div>
                {sim.scores && <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">{Object.entries(sim.scores).map(([k, v]: any) => (
                  <div key={k}><div className="text-[11px] capitalize text-muted">{k.replace(/_/g, " ")}</div><div className="mt-0.5 h-1.5 rounded bg-line"><div className="h-1.5 rounded bg-ink" style={{ width: `${(Number(v) || 0) * 10}%` }} /></div></div>))}</div>}
                {sim.refutes?.length > 0 && <div className="mt-3"><div className="text-[11.5px] font-semibold text-muted">Would still push back on</div>
                  <ul className="mt-1 space-y-0.5 text-[12.5px]">{sim.refutes.map((r: string) => <li key={r}>"{r}"</li>)}</ul></div>}
                {d.rounds?.length > 1 && (
                  <details className="mt-3 text-[12.5px]"><summary className="cursor-pointer text-muted">How the drafts improved over {d.rounds.length} rounds</summary>
                    <ol className="mt-2 space-y-2">{d.rounds.map((r: any) => (
                      <li key={r.n} className="rounded-md border border-line bg-white p-2.5">
                        <div className="flex items-center gap-2"><b>Round {r.n}</b><ScorePill v={r.simulation?.overall} small />
                          <span className="text-faint">{r.simulation?.connection?.accept ? "accepts" : "ignores"} · {r.simulation?.message_1?.reply ? "replies" : "no reply"}</span></div>
                        <p className="mt-1 text-muted">{r.messages?.connection_note}</p>
                        {[...(r.lint || []), ...(r.simulation?.fixes || [])].length > 0 && <ul className="mt-1 list-disc pl-4 text-[12px] text-faint">{[...(r.lint || []), ...(r.simulation?.fixes || [])].slice(0, 4).map((f: string) => <li key={f}>{f}</li>)}</ul>}
                      </li>))}</ol>
                  </details>
                )}
              </section>

              {/* why this works */}
              {(d.why?.hits?.length || d.why?.beaten?.length || d.why?.still_open?.length) ? (
                <section className="rounded-lg border border-line p-4">
                  <div className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><Lightbulb className="size-3.5" />Why this works</div>
                  <div className="grid gap-4 lg:grid-cols-3">
                    <WhyCol title="Hits" tone="text-owner" items={d.why.hits} render={(x: any) => <><q className="font-medium">{x.line}</q><div className="text-muted">→ {x.trigger}</div>{x.evidence && <div className="text-[11.5px] text-faint">based on: {x.evidence}</div>}</>} />
                    <WhyCol title="Push-back beaten" tone="text-sponsor" items={d.why.beaten} render={(x: any) => <><div className="font-medium">"{x.refute}"</div><div className="text-muted">{x.how}</div>{x.line && <q className="text-[11.5px] text-faint">{x.line}</q>}</>} />
                    <WhyCol title="Could still refute" tone="text-danger" items={d.why.still_open} render={(x: any) => <><div className="font-medium">"{x.refute}"</div><div className="text-muted">{x.suggestion}</div></>} />
                  </div>
                </section>
              ) : null}

              {/* objections */}
              {d.objections?.length > 0 && (
                <section>
                  <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-muted"><ShieldAlert className="size-3.5" />If they push back</div>
                  <div className="space-y-2">{d.objections.map((o: any, i: number) => <Objection key={i} o={o} copy={copy} />)}</div>
                </section>
              )}

              {/* research */}
              {(d.research?.topics?.length > 0 || d.angles?.length > 1) && (
                <section className="grid gap-4 sm:grid-cols-2">
                  {d.research?.topics?.length > 0 && <div><div className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold text-muted"><MessageSquareQuote className="size-3.5" />What they've talked about</div>
                    <ul className="space-y-1.5 text-[12.5px]">{d.research.topics.map((t: any, i: number) => <li key={i}><b className="font-medium">{t.topic}</b>{t.quote && <q className="block text-muted">{t.quote}</q>}</li>)}</ul></div>}
                  {d.angles?.length > 1 && <div><div className="mb-1.5 text-[12px] font-semibold text-muted">Other angles the agent considered</div>
                    <ul className="space-y-1.5 text-[12.5px]">{d.angles.slice(1).map((a: any, i: number) => <li key={i}><b className="font-medium">{a.hook}</b><span className="block text-muted">{a.offer} · strength {a.strength}/10</span></li>)}</ul></div>}
                </section>
              )}
            </div>
          )}
        </SheetContent>
      )}
    </D.Root>
  );
}

const TRIGGER_LABEL: Record<string, string> = { pain: "Pain", commitment: "Commitment", ambition: "Ambition", event: "Fresh event", peer_move: "Peer move", contrarian: "Contrarian", recognition: "Their talk/post" };
const TRIGGER_TONE: Record<string, any> = { pain: "red", commitment: "violet", ambition: "green", event: "saffron", peer_move: "amber", contrarian: "slate", recognition: "green" };

function WhyCol({ title, tone, items, render }: any) {
  return (
    <div><div className={cn("mb-1.5 text-[12px] font-semibold", tone)}>{title}</div>
      {items?.length ? <ul className="space-y-2 text-[12.5px]">{items.map((x: any, i: number) => <li key={i} className="border-l-2 border-line pl-2.5">{render(x)}</li>)}</ul>
        : <p className="text-[12px] text-faint">None</p>}</div>
  );
}

function AgentLog({ log }: { log: string[] }) {
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="mb-3 flex items-center gap-2 text-[13px] font-medium"><Loader2 className="size-4 animate-spin text-saffron" />Agent at work</div>
      <ol className="space-y-1.5 text-[12.5px]">{log.map((l, i) => (
        <li key={i} className={cn("flex gap-2", i === log.length - 1 ? "text-fg" : "text-muted")}><span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", i === log.length - 1 ? "bg-saffron" : "bg-line")} />{l}</li>))}</ol>
    </div>
  );
}

export function ScorePill({ v, small }: { v?: number | null; small?: boolean }) {
  if (v == null) return null;
  const tone = v >= 7.5 ? "bg-owner-soft text-owner" : v >= 5.5 ? "bg-influencer-soft text-influencer" : "bg-danger-soft text-danger";
  return <span className={cn("inline-flex items-center rounded-md font-semibold tabular-nums", tone, small ? "px-1.5 text-[11px]" : "px-2 py-0.5 text-[12.5px]")}>{Number(v).toFixed(1).replace(/\.0$/, "")}/10</span>;
}

function Reaction({ label, ok, yes, no, text }: any) {
  return (
    <div className="rounded-md border border-line bg-white p-2.5">
      <div className="flex items-center gap-2 text-[12px]"><span className="text-muted">{label}</span><Badge tone={ok ? "green" : "red"}>{ok ? yes : no}</Badge></div>
      {text && <p className="mt-1 text-[12.5px] italic text-fg/80">"{text}"</p>}
    </div>
  );
}

function Objection({ o, copy }: any) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-line">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <span className="flex-1 text-[13px]">"{o.objection}"</span>
        <Badge tone={o.likelihood === "high" ? "red" : o.likelihood === "medium" ? "amber" : "gray"}>{o.likelihood}</Badge>
        <ChevronDown className={cn("size-4 text-faint transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="space-y-2 border-t border-line-2 px-3 py-2">{(o.responses || []).map((r: any, i: number) => (
        <div key={i} className="text-[12.5px]"><div className="flex items-center gap-2"><b className="font-medium">{r.label}</b>
          <button onClick={() => copy(r.reply)} className="ml-auto text-faint hover:text-fg" aria-label="Copy reply"><Copy className="size-3.5" /></button></div>
          <p className="text-muted">{r.reply}</p></div>))}</div>}
    </div>
  );
}
