import * as D from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Search } from "lucide-react";

export function CommandPalette({ open, onOpenChange, children, placeholder = "Search accounts or jump to…" }: { open: boolean; onOpenChange: (v: boolean) => void; children: React.ReactNode; placeholder?: string }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-ink/30" />
        <D.Content className="fixed left-1/2 top-[14vh] z-50 w-[min(600px,92vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-white shadow-2xl">
          <D.Title className="sr-only">Command menu</D.Title>
          <Command loop className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11.5px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-faint">
            <div className="flex items-center gap-2 border-b border-line px-3"><Search className="size-4 text-faint" />
              <Command.Input autoFocus placeholder={placeholder} className="h-11 w-full bg-transparent text-[14px] outline-none placeholder:text-faint" /></div>
            <Command.List className="max-h-[360px] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-6 text-center text-[13px] text-muted">No matches.</Command.Empty>
              {children}
            </Command.List>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
export function CommandItem({ onSelect, children, value }: { onSelect: () => void; children: React.ReactNode; value?: string }) {
  return <Command.Item value={value} onSelect={onSelect} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] data-[selected=true]:bg-line-2 [&_svg]:size-4 [&_svg]:text-muted">{children}</Command.Item>;
}
export const CommandGroup = Command.Group;
