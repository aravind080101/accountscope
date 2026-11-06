import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn("h-8 w-full rounded-md border border-line bg-white px-2.5 text-[13px] placeholder:text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/50 focus-visible:border-saffron", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn("w-full rounded-md border border-line bg-white px-2.5 py-2 text-[13px] placeholder:text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/50 focus-visible:border-saffron", className)} {...props} />
));
Textarea.displayName = "Textarea";

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-8 rounded-md border border-line bg-white px-2 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/50", className)} {...props} />;
}
export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1 block text-xs font-medium text-muted", className)} {...props} />;
}
