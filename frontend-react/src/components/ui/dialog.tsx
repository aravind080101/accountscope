import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ className, children, title, description, ...props }: React.ComponentProps<typeof D.Content> & { title: string; description?: string }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[1px] data-[state=open]:animate-in" />
      <D.Content className={cn("fixed left-1/2 top-[12vh] z-50 w-[min(560px,92vw)] -translate-x-1/2 rounded-xl border border-line bg-white p-5 shadow-2xl focus:outline-none", className)} {...props}>
        <div className="mb-4 pr-8">
          <D.Title className="text-[15px] font-semibold">{title}</D.Title>
          {description && <D.Description className="mt-1 text-[13px] text-muted">{description}</D.Description>}
        </div>
        {children}
        <D.Close className="absolute right-3 top-3 rounded-md p-1 text-muted hover:bg-line-2" aria-label="Close"><X className="size-4" /></D.Close>
      </D.Content>
    </D.Portal>
  );
}

export function SheetContent({ className, children, title, description, ...props }: React.ComponentProps<typeof D.Content> & { title: React.ReactNode; description?: React.ReactNode }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-ink/20" />
      <D.Content className={cn("fixed inset-y-0 right-0 z-50 flex w-[min(560px,96vw)] flex-col border-l border-line bg-white shadow-2xl focus:outline-none", className)} {...props}>
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div><D.Title className="text-[15px] font-semibold">{title}</D.Title>
            {description && <D.Description className="mt-0.5 text-[12.5px] text-muted">{description}</D.Description>}</div>
          <D.Close className="rounded-md p-1 text-muted hover:bg-line-2" aria-label="Close"><X className="size-4" /></D.Close>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </D.Content>
    </D.Portal>
  );
}
