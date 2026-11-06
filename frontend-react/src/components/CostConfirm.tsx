import { useEffect, useState } from "react";
import { Coins, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";

type Cost = { people: number; lines: { service: string; amount: string; detail: string }[]; notes: string[]; free: boolean };
type Ask = { url: string; title: string; action: string; resolve: (ok: boolean) => void };

let open: ((a: Ask) => void) | null = null;

/** Shows what an action will spend and resolves true only if the user confirms. Free actions go straight through. */
export function confirmCost(url: string, title: string, action: string): Promise<boolean> {
  return new Promise((resolve) => (open ? open({ url, title, action, resolve }) : resolve(true)));
}

export function CostConfirmHost() {
  const [ask, setAsk] = useState<Ask | null>(null);
  const [cost, setCost] = useState<Cost | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    open = (a) => {
      setErr(""); setCost(null); setAsk(a);
      api<Cost>(a.url).then((c) => {
        if (c.free && !c.notes.some((n) => n.includes("hidden"))) { a.resolve(true); setAsk(null); return; }
        setCost(c);
      }).catch((e) => setErr(e.message));
    };
    return () => { open = null; };
  }, []);

  const done = (ok: boolean) => { ask?.resolve(ok); setAsk(null); };

  return (
    <Dialog open={!!ask} onOpenChange={(v) => !v && done(false)}>
      {ask && (
        <DialogContent title={ask.title} description="This uses paid credits. Here's the estimate before anything is spent.">
          {!cost && !err && <div className="flex justify-center py-6"><Loader2 className="size-5 animate-spin text-muted" /></div>}
          {err && <p className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">Couldn't estimate the cost: {err}</p>}
          {cost && (
            <div className="space-y-3">
              {cost.people > 1 && <p className="text-[13px] text-muted">For {cost.people} contacts in total:</p>}
              {cost.lines.length > 0 && (
                <div className="divide-y divide-line rounded-lg border border-line">
                  {cost.lines.map((l) => (
                    <div key={l.service} className="flex items-start gap-3 px-3 py-2.5">
                      <Coins className="mt-0.5 size-4 shrink-0 text-saffron" />
                      <div className="min-w-0 flex-1"><div className="text-[13px] font-medium">{l.service}</div><div className="text-[12px] text-faint">{l.detail}</div></div>
                      <div className="whitespace-nowrap text-[13px] font-semibold tabular-nums">{l.amount}</div>
                    </div>))}
                </div>)}
              {cost.notes.map((n) => <p key={n} className="text-[12.5px] text-muted">{n}</p>)}
            </div>)}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => done(false)}>Cancel</Button>
            <Button size="sm" disabled={!cost && !err} onClick={() => done(true)}>{ask.action}</Button>
          </div>
        </DialogContent>)}
    </Dialog>
  );
}
