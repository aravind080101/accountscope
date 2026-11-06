import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { FileText, Globe, Loader2, RefreshCw, Sparkles, Trash2, Upload } from "lucide-react";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";

type Source = { id: number; name: string; kind: "deck" | "web"; url?: string; chars: number };

const DEFAULT_TARGETS = "Moolya, moolya.com\nBugasura, bugasura.io";

export function SellerDialog({ open, onOpenChange, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; onSaved: () => void }) {
  const [profile, setProfile] = useState<any>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [targets, setTargets] = useState(DEFAULT_TARGETS);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<"" | "upload" | "web" | "build" | "rescore">("");
  const [json, setJson] = useState<string | null>(null);
  const [rescore, setRescore] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [p, s] = await Promise.all([api<any>("/api/profile"), api<Source[]>("/api/profile/sources")]);
    setProfile(p.profile); setSources(s);
  };
  useEffect(() => { if (open) { load(); setJson(null); } }, [open]);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy("upload");
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    try {
      const body = await api<any>("/api/profile/sources", { method: "POST", body: fd });
      toast.success(`Added ${body.added.length} file${body.added.length === 1 ? "" : "s"}`);
      body.errors?.forEach((e: string) => toast.error(e));
      await load();
    } catch (e: any) { toast.error(e.message); } finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };

  const research = async () => {
    const list = targets.split("\n").map((l) => l.split(",").map((x) => x.trim())).filter((x) => x[0]).map(([name, domain]) => ({ name, domain: domain || null }));
    setBusy("web");
    try { const r = await post("/api/profile/research", { targets: list }); toast.success(`Read ${r.added} pages`); setSources(r.sources); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };

  const build = async () => {
    setBusy("build");
    try { const p = await post("/api/profile/generate", { company: profile?.company || "", description: notes }); setProfile(p); onSaved(); toast.success("Profile rebuilt from your material. Re-score accounts to apply it."); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };

  const saveJson = async () => {
    try { const p = await api("/api/profile", { method: "PUT", body: JSON.stringify(JSON.parse(json || "")) }); setProfile(p); setJson(null); onSaved(); toast.success("Saved"); }
    catch (e: any) { toast.error("Couldn't save: " + e.message); }
  };

  const startRescore = async () => {
    setBusy("rescore");
    try {
      let st = await post("/api/profile/rescore");
      setRescore(st);
      for (let n = 1; n < 800; n++) {
        await new Promise((r) => setTimeout(r, 1500));
        st = await api("/api/profile/rescore");
        setRescore(st);
        if (!st.running && (st.total ? st.done >= st.total : n > 2)) break;
      }
      toast.success("Fit re-judged on every account"); onSaved();
    } catch (e: any) { toast.error(e.message); } finally { setBusy(""); }
  };

  const remove = async (id: number) => { await api(`/api/profile/sources/${id}`, { method: "DELETE" }); setSources((s) => s.filter((x) => x.id !== id)); };
  const decks = sources.filter((s) => s.kind === "deck"), web = sources.filter((s) => s.kind === "web");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="What you sell" description="Fit is judged by AI against this profile. Build it from your own decks and websites, not a keyword list." className="top-[5vh] max-h-[90vh] w-[min(980px,95vw)] overflow-y-auto">
        <div className="grid gap-5 md:grid-cols-[340px_1fr]">
          {/* left: material */}
          <div className="space-y-4">
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted">Decks & documents</h3>
                <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={!!busy}>
                  {busy === "upload" ? <Loader2 className="animate-spin" /> : <Upload />}Upload
                </Button>
                <input ref={fileRef} type="file" multiple accept=".pdf,.pptx,.docx,.txt,.md" className="hidden" onChange={(e) => upload(e.target.files)} />
              </div>
              <p className="mb-2 text-[12px] text-muted">PDF, PowerPoint (.pptx), Word or text. Sales decks, case studies, capability docs.</p>
              <SourceList items={decks} onRemove={remove} empty="No decks yet" />
            </section>
            <section>
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">Web research</h3>
              <Textarea rows={3} value={targets} onChange={(e) => setTargets(e.target.value)} className="font-mono text-[12px]" placeholder="Company, domain (one per line)" />
              <Button size="sm" variant="outline" className="mt-2" onClick={research} disabled={!!busy}>
                {busy === "web" ? <Loader2 className="animate-spin" /> : <Globe />}{busy === "web" ? "Reading pages… (a minute)" : "Research these on the web"}
              </Button>
              <div className="mt-2"><SourceList items={web} onRemove={remove} empty="No web pages yet" /></div>
            </section>
            <section className="rounded-lg border border-line bg-canvas p-3">
              <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes, e.g. focus on BFSI and OTT" />
              <Button className="mt-2 w-full" onClick={build} disabled={!!busy || !sources.length}>
                {busy === "build" ? <Loader2 className="animate-spin" /> : <Sparkles />}Build profile from {sources.length} source{sources.length === 1 ? "" : "s"}
              </Button>
            </section>
          </div>

          {/* right: the profile */}
          <div className="min-w-0">
            {json !== null ? (
              <div>
                <Textarea rows={24} value={json} onChange={(e) => setJson(e.target.value)} className="font-mono text-[12px]" spellCheck={false} />
                <div className="mt-2 flex justify-end gap-2"><Button variant="outline" onClick={() => setJson(null)}>Cancel</Button><Button onClick={saveJson}>Save</Button></div>
              </div>
            ) : profile ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div><div className="text-[15px] font-semibold">{profile.company}</div><p className="mt-1 text-[13px] leading-relaxed text-muted">{profile.description}</p></div>
                  <Button size="sm" variant="ghost" onClick={() => setJson(JSON.stringify(profile, null, 2))}>Edit</Button>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(profile.offerings || []).map((o: any) => (
                    <div key={o.name} className="rounded-lg border border-line p-3">
                      <div className="flex items-center gap-2"><span className="text-[13px] font-semibold">{o.name}</span>{o.kind && <Badge tone={o.kind === "product" ? "violet" : "slate"}>{o.kind}</Badge>}</div>
                      {o.what && <p className="mt-1 text-[12.5px] leading-snug text-muted">{o.what}</p>}
                      {!!o.problems?.length && <ul className="mt-2 space-y-0.5 text-[12px] text-fg/80">{o.problems.slice(0, 4).map((p: string) => <li key={p}>· {p}</li>)}</ul>}
                    </div>
                  ))}
                </div>
                {!!profile.proof?.length && <Block title="Proof">{profile.proof.map((p: string) => <li key={p}>{p}</li>)}</Block>}
                <div className="flex flex-wrap gap-1.5"><span className="mr-1 text-[12px] text-muted">Buyers</span>{(profile.buyer_titles || []).map((t: string) => <Badge key={t} tone="outline">{t}</Badge>)}</div>
                {!!profile.competitors?.length && <div className="flex flex-wrap gap-1.5"><span className="mr-1 text-[12px] text-muted">Competitors</span>{profile.competitors.map((t: string) => <Badge key={t} tone="red">{t}</Badge>)}</div>}
              </div>
            ) : <Loader2 className="animate-spin text-muted" />}
          </div>
        </div>
        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <p className="text-[12px] text-muted">{rescore?.total ? `Re-scored ${rescore.done} of ${rescore.total} accounts` : "Changed the profile? Re-judge fit on accounts you've already researched (no new web searches)."}</p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={startRescore} disabled={!!busy}>{busy === "rescore" ? <Loader2 className="animate-spin" /> : <RefreshCw />}Re-score all accounts</Button>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SourceList({ items, onRemove, empty }: { items: Source[]; onRemove: (id: number) => void; empty: string }) {
  if (!items.length) return <p className="text-[12px] text-faint">{empty}</p>;
  return (
    <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-lg border border-line">
      {items.map((s) => (
        <li key={s.id} className="group flex items-center gap-2 px-2.5 py-1.5 text-[12.5px]">
          {s.kind === "deck" ? <FileText className="size-3.5 shrink-0 text-muted" /> : <Globe className="size-3.5 shrink-0 text-muted" />}
          {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:underline">{s.name}</a> : <span className="min-w-0 flex-1 truncate">{s.name}</span>}
          <span className="text-[11px] text-faint">{Math.round(s.chars / 1000)}k</span>
          <button aria-label="Remove" onClick={() => onRemove(s.id)} className="text-faint opacity-0 hover:text-danger group-hover:opacity-100"><Trash2 className="size-3.5" /></button>
        </li>
      ))}
    </ul>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><div className="mb-1 text-[12px] text-muted">{title}</div><ul className="list-disc space-y-0.5 pl-4 text-[12.5px]">{children}</ul></div>;
}
