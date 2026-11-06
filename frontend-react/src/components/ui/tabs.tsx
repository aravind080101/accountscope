import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsContent = T.Content;
export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn("flex h-10 items-end gap-1 border-b border-line", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return <T.Trigger className={cn("relative -mb-px inline-flex h-9 items-center gap-1.5 border-b-2 border-transparent px-2.5 text-[13px] font-medium text-muted hover:text-fg data-[state=active]:border-ink data-[state=active]:text-fg [&_svg]:size-3.5", className)} {...props} />;
}
export function Segmented({ value, onChange, items }: { value: string; onChange: (v: string) => void; items: [string, React.ReactNode][] }) {
  return (
    <div className="inline-flex rounded-lg bg-line-2 p-0.5">
      {items.map(([k, label]) => (
        <button key={k} onClick={() => onChange(k)} className={cn("h-7 rounded-md px-3 text-[13px] font-medium text-muted", value === k && "bg-white text-fg shadow-sm")}>{label}</button>
      ))}
    </div>
  );
}
