"use client"

import * as React from "react"
import { Drawer as DrawerPrimitive } from "@base-ui/react/drawer"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { XIcon } from "@phosphor-icons/react"

function Drawer({ ...props }: DrawerPrimitive.Root.Props) {
  return <DrawerPrimitive.Root data-slot="drawer" {...props} />
}

const FIELD = "input, textarea, select, [contenteditable]"

/**
 * Bottom drawer. Touch swipes start from the grip, or from the content once it is scrolled to the top
 * (Base UI hands mid-scroll drags to the scroller); mouse drags start from the grip only. Swiping is off
 * while a field has focus so it never fights the keyboard.
 */
function DrawerContent({
  className,
  children,
  ...props
}: DrawerPrimitive.Popup.Props) {
  const [typing, setTyping] = React.useState(false)
  return (
    <DrawerPrimitive.Portal>
      <DrawerPrimitive.Backdrop
        data-slot="drawer-overlay"
        className="fixed inset-0 z-50 bg-black/80 opacity-[calc(1-var(--drawer-swipe-progress,0))] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 data-swiping:duration-0 supports-backdrop-filter:backdrop-blur-xs"
      />
      <DrawerPrimitive.Viewport className="fixed inset-0 z-50 flex items-end">
        <DrawerPrimitive.Popup
          data-slot="drawer-content"
          data-base-ui-swipe-ignore={typing ? "" : undefined}
          onFocus={(event) => setTyping(event.target.matches(FIELD))}
          onBlur={() => setTyping(false)}
          className={cn(
            "relative flex max-h-[92svh] w-full flex-col rounded-t-4xl border-t bg-popover bg-clip-padding pb-[env(safe-area-inset-bottom)] text-sm text-popover-foreground shadow-lg outline-none",
            "[transform:translateY(var(--drawer-swipe-movement-y,0px))] transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] data-swiping:duration-0 data-swiping:select-none data-ending-style:[transform:translateY(100%)] data-starting-style:[transform:translateY(100%)] data-ending-style:duration-[calc(var(--drawer-swipe-strength,1)*300ms)]",
            className
          )}
          {...props}
        >
          <div aria-hidden data-testid="sheet-handle" className="flex h-7 w-full shrink-0 cursor-grab items-center justify-center">
            <div className="h-1 w-10 rounded-full bg-muted-foreground/30" />
          </div>
          <DrawerPrimitive.Content className="flex min-h-0 flex-col overflow-y-auto overscroll-contain">
            {children}
          </DrawerPrimitive.Content>
          <DrawerPrimitive.Close
            data-slot="drawer-close"
            render={<Button variant="ghost" className="absolute top-4 right-4" size="icon-sm" />}
          >
            <XIcon />
            <span className="sr-only">Close</span>
          </DrawerPrimitive.Close>
        </DrawerPrimitive.Popup>
      </DrawerPrimitive.Viewport>
    </DrawerPrimitive.Portal>
  )
}

export { Drawer, DrawerContent }
