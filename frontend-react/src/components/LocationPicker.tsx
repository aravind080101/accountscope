import { useEffect, useRef, useState } from "react";
import { Command } from "cmdk";
import { Check, ChevronDown, Globe2, Plus, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type LocationGroup = { group: string; items: string[] };

/** Multi-select place picker: worldwide, regions, every country, states, cities, or anything typed. */
export function LocationPicker({ value, onChange, groups, placeholder = "Worldwide" }:
  { value: string[]; onChange: (v: string[]) => void; groups: LocationGroup[] | undefined; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const has = (v: string) => value.some((x) => x.toLowerCase() === v.toLowerCase());
  const toggle = (v: string) => {
    if (v === "Worldwide") { onChange([]); setOpen(false); return; }
    onChange(has(v) ? value.filter((x) => x.toLowerCase() !== v.toLowerCase()) : [...value, v]);
    setQ("");
  };
  const typed = q.trim();
  const known = !!typed && (groups || []).some((g) => g.items.some((i) => i.toLowerCase() === typed.toLowerCase()));

  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="flex min-h-9 w-full items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1 text-left text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ink/20">
        <Globe2 className="size-3.5 shrink-0 text-faint" />
        <div className="flex min-w-0 flex-1 flex-wrap gap-1">
          {value.length === 0 ? <span className="text-muted">{placeholder}</span> : value.map((v) => (
            <span key={v} className="inline-flex items-center gap-1 rounded bg-line-2 px-1.5 py-0.5 text-[12px]">
              {v}
              <span role="button" aria-label={`Remove ${v}`} onMouseDown={(e) => { e.stopPropagation(); e.preventDefault(); onChange(value.filter((x) => x !== v)); }}
                className="text-faint hover:text-fg"><X className="size-3" /></span>
            </span>))}
        </div>
        <ChevronDown className="size-3.5 shrink-0 text-faint" />
      </button>

      {open && (
        <div className="absolute left-0 top-[calc(100%+4px)] z-50 w-[min(340px,90vw)] overflow-hidden rounded-lg border border-line bg-white shadow-xl">
          <Command loop className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-faint">
            <div className="flex items-center gap-2 border-b border-line px-2.5"><Search className="size-3.5 text-faint" />
              <Command.Input autoFocus value={q} onValueChange={setQ} placeholder="Search a region, country, state or city"
                onKeyDown={(e) => { if (e.key === "Enter" && typed && !known) { e.preventDefault(); toggle(typed); } }}
                className="h-10 w-full bg-transparent text-[13px] outline-none placeholder:text-faint" /></div>
            <Command.List className="max-h-[320px] overflow-y-auto p-1">
              {typed && !known && (
                <Command.Item value={`__add ${typed}`} onSelect={() => toggle(typed)} className={itemCls}>
                  <Plus className="size-3.5 text-muted" />Use “{typed}”
                </Command.Item>)}
              {(groups || []).map((g) => (
                <Command.Group key={g.group} heading={g.group}>
                  {g.items.map((it) => {
                    const on = it === "Worldwide" ? value.length === 0 : has(it);
                    return (
                      <Command.Item key={`${g.group}:${it}`} value={`${it} ${g.group}`} onSelect={() => toggle(it)} className={itemCls}>
                        <Check className={cn("size-3.5", on ? "text-fg" : "invisible")} />{it}
                      </Command.Item>);
                  })}
                </Command.Group>))}
            </Command.List>
          </Command>
          {value.length > 0 && (
            <div className="flex items-center justify-between border-t border-line px-3 py-2 text-[12px] text-muted">
              {value.length} selected
              <button type="button" className="hover:text-fg" onClick={() => onChange([])}>Clear</button>
            </div>)}
        </div>)}
    </div>
  );
}

const itemCls = "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] data-[selected=true]:bg-line-2";
