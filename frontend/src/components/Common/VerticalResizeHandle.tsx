import React from 'react';

interface VerticalResizeHandleProps {
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
  isDragging?: boolean;
  ariaValueNow?: number;
  ariaValueMin?: number;
  ariaValueMax?: number;
}

export const VerticalResizeHandle: React.FC<VerticalResizeHandleProps> = ({
  onPointerDown,
  onKeyDown,
  isDragging = false,
  ariaValueNow,
  ariaValueMin,
  ariaValueMax,
}) => (
  <div
    role="separator"
    aria-orientation="vertical"
    aria-label="Resize insights panel"
    aria-valuenow={ariaValueNow}
    aria-valuemin={ariaValueMin}
    aria-valuemax={ariaValueMax}
    tabIndex={0}
    onPointerDown={onPointerDown}
    onKeyDown={onKeyDown}
    className={`hidden lg:flex shrink-0 w-2 -mx-0.5 cursor-col-resize touch-none select-none items-stretch justify-center group z-10 ${
      isDragging ? 'bg-deloitte-green/10' : ''
    }`}
  >
    <div
      className={`w-px h-full transition-colors ${
        isDragging
          ? 'bg-deloitte-green'
          : 'bg-brand-border group-hover:bg-deloitte-green/70 group-focus-visible:bg-deloitte-green'
      }`}
    />
  </div>
);
