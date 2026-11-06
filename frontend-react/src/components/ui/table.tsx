import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

export function Table({ className, ...p }: React.TableHTMLAttributes<HTMLTableElement>) {
  return <div className="overflow-x-auto"><table className={cn("w-full border-collapse text-[13px]", className)} {...p} /></div>;
}
export function Th({ className, sort, dir, onSort, children, ...p }: React.ThHTMLAttributes<HTMLTableCellElement> & { sort?: boolean; dir?: "asc" | "desc" | null; onSort?: () => void }) {
  return (
    <th className={cn("h-8 whitespace-nowrap border-b border-line bg-canvas px-3 text-left text-[12px] font-medium text-muted", sort && "cursor-pointer select-none hover:text-fg", className)} onClick={onSort} {...p}>
      <span className="inline-flex items-center gap-1">{children}{dir === "asc" ? <ArrowUp className="size-3" /> : dir === "desc" ? <ArrowDown className="size-3" /> : null}</span>
    </th>
  );
}
export function Td({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-line-2 px-3 py-2 align-middle", className)} {...p} />;
}
export function Tr({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-canvas", className)} {...p} />;
}
