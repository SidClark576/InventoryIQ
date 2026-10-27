import { useEffect, useRef, type MouseEvent, type PointerEvent } from "react";

const MOVE_TOLERANCE_PX = 10;

/** Touch/pen long-press (mouse keeps plain clicks). Swallows the click that follows a fired press. */
export function useLongPress(onLongPress: () => void, ms = 500) {
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const origin = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);

  const cancel = () => {
    clearTimeout(timer.current);
    origin.current = null;
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  return {
    onPointerDown: (event: PointerEvent) => {
      if (event.pointerType === "mouse") return;
      fired.current = false;
      origin.current = { x: event.clientX, y: event.clientY };
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        fired.current = true;
        origin.current = null;
        onLongPress();
      }, ms);
    },
    onPointerMove: (event: PointerEvent) => {
      const start = origin.current;
      if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > MOVE_TOLERANCE_PX) cancel();
    },
    onPointerUp: cancel,
    onPointerCancel: cancel,
    // The OS menu for a long-pressed link would cover the selection.
    onContextMenu: (event: MouseEvent) => {
      if (origin.current || fired.current) event.preventDefault();
    },
    onClickCapture: (event: MouseEvent) => {
      if (!fired.current) return;
      fired.current = false;
      event.preventDefault();
      event.stopPropagation();
    },
  };
}
