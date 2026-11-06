import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium leading-4 whitespace-nowrap", {
  variants: {
    tone: {
      gray: "bg-line-2 text-muted",
      outline: "border border-line text-muted bg-white",
      green: "bg-owner-soft text-owner",
      violet: "bg-sponsor-soft text-sponsor",
      amber: "bg-influencer-soft text-influencer",
      saffron: "bg-saffron-soft text-saffron-ink",
      red: "bg-danger-soft text-danger",
      slate: "bg-practitioner-soft text-practitioner",
      ink: "bg-ink text-white",
    },
  },
  defaultVariants: { tone: "gray" },
});
export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
export const ROLE_TONE: Record<string, any> = { Owner: "green", Sponsor: "violet", Influencer: "amber", Practitioner: "slate", "Runs it": "green", Team: "slate" };
