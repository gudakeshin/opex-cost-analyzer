import { useCallback, useEffect, useRef, useState } from 'react';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStoredWidth(storageKey: string, defaultWidth: number, min: number, max: number): number {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return defaultWidth;
    const parsed = Number.parseInt(raw, 10);
    if (Number.isFinite(parsed)) return clamp(parsed, min, max);
  } catch {
    /* ignore */
  }
  return defaultWidth;
}

export interface UseResizableWidthOptions {
  storageKey: string;
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  /** When true, dragging left increases width (right-hand panel). Default true. */
  invertDelta?: boolean;
}

export function useResizableWidth({
  storageKey,
  defaultWidth,
  minWidth,
  maxWidth,
  invertDelta = true,
}: UseResizableWidthOptions) {
  const [width, setWidth] = useState(() =>
    readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth),
  );
  const [isDragging, setIsDragging] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(defaultWidth);

  const beginDrag = useCallback(
    (clientX: number) => {
      startX.current = clientX;
      startWidth.current = width;
      setIsDragging(true);
    },
    [width],
  );

  useEffect(() => {
    if (!isDragging) return;

    const onMove = (e: PointerEvent) => {
      const rawDelta = e.clientX - startX.current;
      const delta = invertDelta ? -rawDelta : rawDelta;
      setWidth(clamp(startWidth.current + delta, minWidth, maxWidth));
    };

    const onEnd = () => {
      setIsDragging(false);
      setWidth((current) => {
        try {
          localStorage.setItem(storageKey, String(current));
        } catch {
          /* ignore */
        }
        return current;
      });
    };

    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onEnd);
    document.addEventListener('pointercancel', onEnd);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onEnd);
      document.removeEventListener('pointercancel', onEnd);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, invertDelta, minWidth, maxWidth, storageKey]);

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      beginDrag(e.clientX);
    },
    [beginDrag],
  );

  const nudgeWidth = useCallback(
    (delta: number) => {
      setWidth((current) => {
        const next = clamp(current + delta, minWidth, maxWidth);
        try {
          localStorage.setItem(storageKey, String(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [minWidth, maxWidth, storageKey],
  );

  const onHandleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const step = e.shiftKey ? 48 : 16;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        nudgeWidth(invertDelta ? step : -step);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        nudgeWidth(invertDelta ? -step : step);
      }
    },
    [invertDelta, nudgeWidth],
  );

  return { width, isDragging, onHandlePointerDown, onHandleKeyDown };
}
