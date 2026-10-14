import { useState, useCallback, useRef } from "react";
import { toPoint, clamp } from "./useCoordinates";
import type { RedactionMark } from "../types";

const MIN_SIZE_PT = 5; // Minimum mark size in PDF points

interface DrawState {
  startX: number; // pixel
  startY: number; // pixel
  currentX: number;
  currentY: number;
}

interface UseDrawingResult {
  drawingRect: { x: number; y: number; width: number; height: number } | null;
  handleMouseDown: (e: React.MouseEvent<SVGSVGElement>) => void;
  handleMouseMove: (e: React.MouseEvent<SVGSVGElement>) => void;
  handleMouseUp: (e: React.MouseEvent<SVGSVGElement>) => void;
}

export function useDrawing(
  scale: number,
  pageWidthPt: number,
  pageHeightPt: number,
  marks: RedactionMark[],
  onDrawComplete: (newMarks: RedactionMark[]) => void,
  disabled: boolean
): UseDrawingResult {
  const [drawState, setDrawState] = useState<DrawState | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const getLocalCoords = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      const svg = e.currentTarget;
      const rect = svg.getBoundingClientRect();
      return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      };
    },
    []
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (disabled) return;
      // Only start drawing on left click on empty area
      if (e.button !== 0) return;
      const target = e.target as Element;
      if (target.classList.contains("redaction-mark")) return;

      const { x, y } = getLocalCoords(e);
      setDrawState({ startX: x, startY: y, currentX: x, currentY: y });
      e.preventDefault();
    },
    [disabled, getLocalCoords]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!drawState) return;
      const { x, y } = getLocalCoords(e);
      setDrawState((prev) =>
        prev ? { ...prev, currentX: x, currentY: y } : null
      );
    },
    [drawState, getLocalCoords]
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!drawState) return;

      const { startX, startY } = drawState;
      const { x: endX, y: endY } = getLocalCoords(e);

      // Convert to PDF points and normalize (ensure x0 < x1, y0 < y1)
      let pdf_x0 = clamp(toPoint(Math.min(startX, endX), scale), 0, pageWidthPt);
      let pdf_y0 = clamp(toPoint(Math.min(startY, endY), scale), 0, pageHeightPt);
      let pdf_x1 = clamp(toPoint(Math.max(startX, endX), scale), 0, pageWidthPt);
      let pdf_y1 = clamp(toPoint(Math.max(startY, endY), scale), 0, pageHeightPt);

      setDrawState(null);

      // Discard micro-clicks (< 5pt in either dimension)
      if (pdf_x1 - pdf_x0 < MIN_SIZE_PT || pdf_y1 - pdf_y0 < MIN_SIZE_PT) {
        return;
      }

      const newMark: RedactionMark = {
        pdf_x0: Math.round(pdf_x0 * 100) / 100,
        pdf_y0: Math.round(pdf_y0 * 100) / 100,
        pdf_x1: Math.round(pdf_x1 * 100) / 100,
        pdf_y1: Math.round(pdf_y1 * 100) / 100,
        reason: "[Redact — No Privilege Reason]",
      };

      onDrawComplete([...marks, newMark]);
    },
    [drawState, getLocalCoords, scale, pageWidthPt, pageHeightPt, marks, onDrawComplete]
  );

  // Compute the visual drawing rectangle in pixels
  let drawingRect: { x: number; y: number; width: number; height: number } | null = null;
  if (drawState) {
    const x = Math.min(drawState.startX, drawState.currentX);
    const y = Math.min(drawState.startY, drawState.currentY);
    const width = Math.abs(drawState.currentX - drawState.startX);
    const height = Math.abs(drawState.currentY - drawState.startY);
    drawingRect = { x, y, width, height };
  }

  return { drawingRect, handleMouseDown, handleMouseMove, handleMouseUp };
}
