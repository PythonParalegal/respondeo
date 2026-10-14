import { useState, useCallback, useEffect, useRef } from "react";
import { toPoint, clamp } from "./useCoordinates";
import type { RedactionMark } from "../types";

const MIN_SIZE_PT = 5;

type HandleDir = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

interface DragState {
  type: "move" | "resize";
  startX: number; // pixel
  startY: number; // pixel
  handleDir?: HandleDir;
  originalMark: RedactionMark;
}

interface UseSelectionResult {
  selectedIndex: number | null;
  handleMarkMouseDown: (e: React.MouseEvent, index: number) => void;
  handleSvgMouseDown: (e: React.MouseEvent<SVGSVGElement>) => void;
  handleSvgMouseMove: (e: React.MouseEvent<SVGSVGElement>) => void;
  handleSvgMouseUp: (e: React.MouseEvent<SVGSVGElement>) => void;
  handleHandleMouseDown: (e: React.MouseEvent, dir: HandleDir) => void;
  setSelectedIndex: (index: number | null) => void;
}

export function useSelection(
  scale: number,
  pageWidthPt: number,
  pageHeightPt: number,
  marks: RedactionMark[],
  onMarksChanged: (newMarks: RedactionMark[], action: "update" | "delete") => void,
  onLocalUpdate: (newMarks: RedactionMark[]) => void,
  disabled: boolean
): UseSelectionResult {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const marksRef = useRef(marks);
  marksRef.current = marks;

  const getLocalCoords = useCallback(
    (e: React.MouseEvent) => {
      const svg = e.currentTarget.closest("svg");
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    },
    []
  );

  // Delete key handler
  useEffect(() => {
    if (disabled) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Delete" && selectedIndex !== null) {
        const newMarks = marksRef.current.filter((_, i) => i !== selectedIndex);
        setSelectedIndex(null);
        onMarksChanged(newMarks, "delete");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedIndex, disabled, onMarksChanged]);

  const handleMarkMouseDown = useCallback(
    (e: React.MouseEvent, index: number) => {
      if (disabled) return;
      e.stopPropagation();
      e.preventDefault();
      setSelectedIndex(index);

      const { x, y } = getLocalCoords(e);
      setDragState({
        type: "move",
        startX: x,
        startY: y,
        originalMark: { ...marks[index] },
      });
    },
    [disabled, getLocalCoords, marks]
  );

  const handleHandleMouseDown = useCallback(
    (e: React.MouseEvent, dir: HandleDir) => {
      if (disabled || selectedIndex === null) return;
      e.stopPropagation();
      e.preventDefault();

      const { x, y } = getLocalCoords(e);
      setDragState({
        type: "resize",
        startX: x,
        startY: y,
        handleDir: dir,
        originalMark: { ...marks[selectedIndex] },
      });
    },
    [disabled, selectedIndex, getLocalCoords, marks]
  );

  const handleSvgMouseDown = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      // Click on empty area = deselect
      const target = e.target as Element;
      if (
        !target.classList.contains("redaction-mark") &&
        !target.classList.contains("resize-handle")
      ) {
        setSelectedIndex(null);
      }
    },
    []
  );

  const handleSvgMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!dragState || selectedIndex === null) return;

      const { x, y } = getLocalCoords(e);
      const dx = toPoint(x - dragState.startX, scale);
      const dy = toPoint(y - dragState.startY, scale);
      const orig = dragState.originalMark;

      let newMark: RedactionMark;

      if (dragState.type === "move") {
        const w = orig.pdf_x1 - orig.pdf_x0;
        const h = orig.pdf_y1 - orig.pdf_y0;
        let x0 = clamp(orig.pdf_x0 + dx, 0, pageWidthPt - w);
        let y0 = clamp(orig.pdf_y0 + dy, 0, pageHeightPt - h);
        newMark = { ...orig, pdf_x0: x0, pdf_y0: y0, pdf_x1: x0 + w, pdf_y1: y0 + h };
      } else {
        // Resize
        let { pdf_x0, pdf_y0, pdf_x1, pdf_y1 } = orig;
        const dir = dragState.handleDir!;

        if (dir.includes("w")) pdf_x0 = clamp(orig.pdf_x0 + dx, 0, pdf_x1 - MIN_SIZE_PT);
        if (dir.includes("e")) pdf_x1 = clamp(orig.pdf_x1 + dx, pdf_x0 + MIN_SIZE_PT, pageWidthPt);
        if (dir.includes("n")) pdf_y0 = clamp(orig.pdf_y0 + dy, 0, pdf_y1 - MIN_SIZE_PT);
        if (dir.includes("s")) pdf_y1 = clamp(orig.pdf_y1 + dy, pdf_y0 + MIN_SIZE_PT, pageHeightPt);

        newMark = { ...orig, pdf_x0, pdf_y0, pdf_x1, pdf_y1 };
      }

      // Update local state only for visual feedback — do NOT call onMarksChanged here,
      // that triggers Streamlit.setComponentValue which causes a full Python rerun loop.
      const updated = [...marks];
      updated[selectedIndex] = newMark;
      marksRef.current = updated;
      onLocalUpdate(updated);
    },
    [dragState, selectedIndex, getLocalCoords, scale, pageWidthPt, pageHeightPt, marks, onLocalUpdate]
  );

  const handleSvgMouseUp = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (dragState && selectedIndex !== null) {
        // Send final position to Streamlit now that drag is complete
        onMarksChanged(marksRef.current, "update");
        setDragState(null);
      }
    },
    [dragState, selectedIndex, onMarksChanged]
  );

  return {
    selectedIndex,
    handleMarkMouseDown,
    handleSvgMouseDown,
    handleSvgMouseMove,
    handleSvgMouseUp,
    handleHandleMouseDown,
    setSelectedIndex,
  };
}
