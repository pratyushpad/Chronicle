import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  // Minimalist Monochrome: sharp corners, uppercase mono labels, instant inversion on hover.
  "group/button inline-flex shrink-0 items-center justify-center gap-2 border border-transparent font-mono text-xs font-medium uppercase tracking-[0.15em] whitespace-nowrap transition-colors duration-100 outline-none select-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px] disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // Primary: black fill → inverts to outlined white on hover.
        default:
          "bg-foreground text-background border-foreground hover:bg-background hover:text-foreground",
        // Outline: black hairline → fills black on hover.
        outline:
          "border-foreground bg-background text-foreground hover:bg-foreground hover:text-background",
        secondary:
          "bg-muted text-foreground border-transparent hover:bg-foreground hover:text-background",
        ghost:
          "text-foreground border-transparent hover:underline underline-offset-4",
        destructive:
          "bg-background text-foreground border-foreground hover:bg-foreground hover:text-background",
        link: "text-foreground border-transparent underline-offset-4 hover:underline normal-case tracking-normal",
      },
      size: {
        default: "h-10 px-5",
        xs: "h-7 px-3 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 px-4 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-12 px-8 text-sm",
        icon: "size-10",
        "icon-xs": "size-7 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
