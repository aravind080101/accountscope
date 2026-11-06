import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/60 [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-ink text-white hover:bg-ink-3 shadow-sm",
        accent: "bg-saffron text-ink hover:bg-[#f6bb60]",
        outline: "border border-line bg-white hover:bg-line-2 text-fg shadow-[0_1px_0_rgba(0,0,0,0.02)]",
        ghost: "hover:bg-line-2 text-muted hover:text-fg",
        subtle: "bg-line-2 hover:bg-line text-fg",
        danger: "text-danger hover:bg-danger-soft",
      },
      size: { default: "h-8 px-3", sm: "h-7 px-2.5 text-[12.5px]", xs: "h-6 px-2 text-xs", icon: "h-8 w-8", "icon-sm": "h-7 w-7" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});
Button.displayName = "Button";
