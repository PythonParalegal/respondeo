import React from "react";
import type { RedactionMark } from "../types";

interface TooltipProps {
  mark: RedactionMark;
  index: number;
  totalMarks: number;
  position: { x: number; y: number };
  privilegeColors: Record<string, string>;
}

export const Tooltip: React.FC<TooltipProps> = ({
  mark,
  index,
  totalMarks,
  position,
  privilegeColors,
}) => {
  const color = privilegeColors[mark.reason] || "#cc0000";

  return (
    <div
      className="tooltip"
      style={{
        left: position.x,
        top: position.y,
      }}
    >
      <div className="reason" style={{ color }}>
        {mark.reason}
      </div>
      <div className="divider" />
      <div className="meta">
        {mark.author && <div>Applied by: {mark.author}</div>}
        {mark.created_at && <div>{mark.created_at.replace("T", " ").slice(0, 16)}</div>}
        <div>
          Box {index + 1} of {totalMarks}
        </div>
        <div>
          ({mark.pdf_x0.toFixed(0)}, {mark.pdf_y0.toFixed(0)}) → (
          {mark.pdf_x1.toFixed(0)}, {mark.pdf_y1.toFixed(0)}) pt
        </div>
      </div>
    </div>
  );
};
