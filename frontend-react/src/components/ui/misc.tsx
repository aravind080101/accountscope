import * as React from "react";
import * as Tip from "@radix-ui/react-tooltip";
import * as DM from "@radix-ui/react-dropdown-menu";
import * as CB from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { cn, initials, tint } from "@/lib/utils";

export function Tooltip({ content, children }: { content: React.ReactNode; children: React.ReactNode }) {
  return (
    <Tip.Root delayDuration={250}>
      <Tip.Trigger asChild>{children}</Tip.Trigger>
      <Tip.Portal><Tip.Content sideOffset={6} className="z-50 max-w-xs rounded-md bg-ink px-2 py-1 text-xs text-white shadow-lg">{content}</Tip.Content></Tip.Portal>
    </Tip.Root>
  );
}
export const TooltipProvider = Tip.Provider;

export const Menu = DM.Root;
export const MenuTrigger = DM.Trigger;
export function MenuContent({ className, ...props }: React.ComponentProps<typeof DM.Content>) {
  return <DM.Portal><DM.Content sideOffset={4} align="end" className={cn("z-50 min-w-44 rounded-lg border border-line bg-white p-1 shadow-xl", className)} {...props} /></DM.Portal>;
}
export function MenuItem({ className, ...props }: React.ComponentProps<typeof DM.Item>) {
  return <DM.Item className={cn("flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] outline-none data-[highlighted]:bg-line-2 [&_svg]:size-3.5 [&_svg]:text-muted", className)} {...props} />;
}

export function Checkbox(props: React.ComponentProps<typeof CB.Root>) {
  return (
    <CB.Root {...props} className={cn("grid size-4 place-items-center rounded border border-[#cfcfd6] bg-white data-[state=checked]:border-ink data-[state=checked]:bg-ink disabled:opacity-40", props.className)}>
      <CB.Indicator><Check className="size-3 text-white" strokeWidth={3} /></CB.Indicator>
    </CB.Root>
  );
}

export function Avatar({ name, size = 28, square = false, className }: { name: string; size?: number; square?: boolean; className?: string }) {
  const c = tint(name);
  return (
    <span className={cn("inline-grid shrink-0 place-items-center font-semibold", square ? "rounded-md" : "rounded-full", className)}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.38), background: c + "1a", color: c }}>{initials(name)}</span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-line-2", className)} />;
}

export function FitPill({ value }: { value: number }) {
  const v = Math.round((value || 0) * 100);
  const tone = v >= 75 ? "bg-owner-soft text-owner" : v >= 50 ? "bg-saffron-soft text-saffron-ink" : "bg-line-2 text-muted";
  return <span className={cn("inline-flex h-5 min-w-9 items-center justify-center rounded-md px-1.5 text-[12px] font-semibold tabular-nums", tone)}>{v}</span>;
}

export function Meter({ value, className }: { value: number; className?: string }) {
  return <span className={cn("inline-block h-1.5 w-14 overflow-hidden rounded-full bg-line-2 align-middle", className)}><i className="block h-full rounded-full bg-ink" style={{ width: `${Math.round((value || 0) * 100)}%` }} /></span>;
}

export function Empty({ icon, title, children, action }: { icon?: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-14 text-center">
      {icon && <div className="mb-3 grid size-10 place-items-center rounded-lg bg-line-2 text-muted [&_svg]:size-5">{icon}</div>}
      <div className="text-[14px] font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-md text-[13px] text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
