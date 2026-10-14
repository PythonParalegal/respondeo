import React from "react";
import { toPixel } from "../hooks/useCoordinates";
import type { RedactionMark } from "../types";

const HANDLE_SIZE = 8;
const HALF = HANDLE_SIZE / 2;

type HandleDir = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const CURSORS: Record<HandleDir, string> = {
  nw: "nwse-resize",
  n: "ns-resize",
  ne: "nesw-resize",
  e: "ew-resize",
  se: "nwse-resize",
  s: "ns-resize",
  sw: "nesw-resize",
  w: "ew-resize",
};

interface ResizeHandlesProps {
  mark: RedactionMark;
  scale: number;
  onHandleMouseDown: (e: React.MouseEvent, dir: HandleDir) => void;
}

export const ResizeHandles: React.FC<ResizeHandlesProps> = ({
  mark,
  scale,
  onHandleMouseDown,
}) => {
  const x0 = toPixel(mark.pdf_x0, scale);
  const y0 = toPixel(mark.pdf_y0, scale);
  const x1 = toPixel(mark.pdf_x1, scale);
  const y1 = toPixel(mark.pdf_y1, scale);
  const mx = (x0 + x1) / 2;
  const my = (y0 + y1) / 2;

  const handles: { dir: HandleDir; cx: number; cy: number }[] = [
    { dir: "nw", cx: x0, cy: y0 },
    { dir: "n", cx: mx, cy: y0 },
    { dir: "ne", cx: x1, cy: y0 },
    { dir: "e", cx: x1, cy: my },
    { dir: "se", cx: x1, cy: y1 },
    { dir: "s", cx: mx, cy: y1 },
    { dir: "sw", cx: x0, cy: y1 },
    { dir: "w", cx: x0, cy: my },
  ];

  return (
    <>
      {handles.map(({ dir, cx, cy }) => (
        <rect
          key={dir}
          x={cx - HALF}
          y={cy - HALF}
          width={HANDLE_SIZE}
          height={HANDLE_SIZE}
          className="resize-handle"
          style={{ cursor: CURSORS[dir] }}
          onMouseDown={(e) => onHandleMouseDown(e, dir)}
        />
      ))}
    </>
  );
};
