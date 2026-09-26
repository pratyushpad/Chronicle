"use client"

import * as React from "react"
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { XIcon } from "lucide-react"

/*
 * Sheet — Base UI Dialog as an edge-anchored panel.
 *
 * Written for this project's Tailwind 3.4: Base UI marks the enter/exit frames with the
 * `data-starting-style` / `data-ending-style` attributes, which Tailwind 3 targets with
 * arbitrary data variants (`data-[starting-style]:…`). Base UI waits for the resulting
 * CSS transitions to finish before unmounting, so exits are never cut off.
 *
 * Motion follows lib/motion.ts (ease-house, duration-base in / duration-fast out — exits
 * are quicker than entrances). The panel slides from its edge only for readers who allow
 * motion; with prefers-reduced-motion it fades in place instead of travelling.
 */

function Sheet({ ...props }: SheetPrimitive.Root.Props) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger({ ...props }: SheetPrimitive.Trigger.Props) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose({ ...props }: SheetPrimitive.Close.Props) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetPortal({ ...props }: SheetPrimitive.Portal.Props) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

function SheetOverlay({ className, ...props }: SheetPrimitive.Backdrop.Props) {
  return (
    <SheetPrimitive.Backdrop
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-foreground/20 transition-opacity duration-base ease-house data-[ending-style]:duration-fast data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 supports-[backdrop-filter]:backdrop-blur-sm",
        className
      )}
      {...props}
    />
  )
}

// Position per side, plus the off-screen frame it slides from (motion-safe only).
const SIDE_CLASSES = {
  right:
    "inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm motion-safe:data-[starting-style]:translate-x-full motion-safe:data-[ending-style]:translate-x-full",
  left:
    "inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm motion-safe:data-[starting-style]:-translate-x-full motion-safe:data-[ending-style]:-translate-x-full",
  top: "inset-x-0 top-0 h-auto border-b motion-safe:data-[starting-style]:-translate-y-full motion-safe:data-[ending-style]:-translate-y-full",
  bottom:
    "inset-x-0 bottom-0 h-auto border-t motion-safe:data-[starting-style]:translate-y-full motion-safe:data-[ending-style]:translate-y-full",
} as const

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: SheetPrimitive.Popup.Props & {
  side?: keyof typeof SIDE_CLASSES
  showCloseButton?: boolean
}) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        data-side={side}
        className={cn(
          "fixed z-50 flex flex-col gap-4 bg-popover bg-clip-padding text-sm text-popover-foreground outline-none",
          "transition-[transform,opacity] duration-base ease-house data-[ending-style]:duration-fast",
          "motion-reduce:data-[ending-style]:opacity-0 motion-reduce:data-[starting-style]:opacity-0",
          SIDE_CLASSES[side],
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close
            data-slot="sheet-close"
            render={
              <Button
                variant="ghost"
                size="icon"
                // 44px target; hover fills like the rest of the monochrome chrome.
                className="absolute right-2.5 top-2.5 size-11 hover:bg-muted"
              />
            }
          >
            <XIcon aria-hidden />
            <span className="sr-only">Close</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Popup>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-0.5 p-4", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  )
}

function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn(
        "font-display text-base font-medium text-foreground",
        className
      )}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: SheetPrimitive.Description.Props) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
