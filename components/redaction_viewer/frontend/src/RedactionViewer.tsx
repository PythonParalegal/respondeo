import React, { useRef, useCallback, useState, useEffect } from "react";
import { Streamlit } from "streamlit-component-lib";
import type { RedactionViewerProps, RedactionMark, ComponentValue } from "./types";
import { toPixel } from "./hooks/useCoordinates";
import { useDrawing } from "./hooks/useDrawing";
import { useSelection } from "./hooks/useSelection";
import { DrawingRect } from "./ui/DrawingRect";
import { ResizeHandles } from "./ui/ResizeHandles";
import { Tooltip } from "./ui/Tooltip";

const DEFAULT_STROKE = "#cc0000";
const SELECTED_STROKE = "#3399ff";

function getMarkStroke(
  mark: RedactionMark,
  index: number,
  selectedIndex: number | null,
  privilegeColors: Record<string, string>
): string {
  if (index === selectedIndex) return SELECTED_STROKE;
  return privilegeColors[mark.reason] || DEFAULT_STROKE;
}

function getMarkFill(index: number, selectedIndex: number | null): string {
  if (index === selectedIndex) return "rgba(0, 0, 0, 0.5)";
  return "rgba(0, 0, 0, 0.65)";
}

export const RedactionViewer: React.FC<RedactionViewerProps> = ({
  imageDataUrl,
  marks: initialMarks,
  scale,
  pageWidthPt,
  pageHeightPt,
  mode,
  caseClosed,
  privilegeColors,
  zoomPct,
}) => {
  const imgRef = useRef<HTMLImageElement>(null);
  const [marks, setMarks] = useState<RedactionMark[]>(initialMarks);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Buffered drawing state ─────────────────────────────────────────
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [unsavedCount, setUnsavedCount] = useState(0);
  const [drawSeq, setDrawSeq] = useState(0);  // bumped on each draw — resets debounce
  const marksForFlushRef = useRef(marks);
  marksForFlushRef.current = marks;
  const hasUnsavedRef = useRef(hasUnsaved);
  hasUnsavedRef.current = hasUnsaved;

  // Sync marks from Python when props change (new page, zoom change, etc.)
  // Use JSON comparison since Streamlit deserializes a new array reference every render
  // Guard: do NOT overwrite locally-buffered marks with stale props
  const prevMarksJsonRef = useRef(JSON.stringify(initialMarks));
  const initialMarksJson = JSON.stringify(initialMarks);
  if (prevMarksJsonRef.current !== initialMarksJson) {
    prevMarksJsonRef.current = initialMarksJson;
    // Only sync from props if we don't have locally-buffered marks
    if (!hasUnsavedRef.current) {
      setMarks(initialMarks);
    }
  }

  const pixelW = pageWidthPt * scale;
  const pixelH = pageHeightPt * scale;

  const handleImageLoad = useCallback(() => {
    if (imgRef.current) {
      Streamlit.setFrameHeight(imgRef.current.naturalHeight + 40);
    }
  }, []);

  // Send updated marks to Python
  const sendValue = useCallback(
    (newMarks: RedactionMark[], action: "update" | "delete" | "batch_update") => {
      const value: ComponentValue = { marks: newMarks, action };
      Streamlit.setComponentValue(value);
    },
    []
  );

  // Draw mode: buffer locally — do NOT call sendValue per box
  const handleDrawComplete = useCallback(
    (newMarks: RedactionMark[]) => {
      setMarks(newMarks);
      setHasUnsaved(true);
      setUnsavedCount((c) => c + 1);
      setDrawSeq((s) => s + 1);  // reset debounce timer
    },
    []
  );

  // Select mode: final change handler (mouseup / delete key only — sends to Streamlit)
  const handleSelectionChange = useCallback(
    (newMarks: RedactionMark[], action: "update" | "delete") => {
      setMarks(newMarks);
      sendValue(newMarks, action);
    },
    [sendValue]
  );

  // Local-only update during drag — visual feedback without Streamlit rerun
  const handleLocalUpdate = useCallback(
    (newMarks: RedactionMark[]) => {
      setMarks(newMarks);
    },
    []
  );

  const drawing = useDrawing(
    scale, pageWidthPt, pageHeightPt, marks,
    handleDrawComplete, caseClosed || mode !== "draw"
  );

  const selection = useSelection(
    scale, pageWidthPt, pageHeightPt, marks,
    handleSelectionChange, handleLocalUpdate, caseClosed || mode !== "select"
  );

  // Deselect when switching to draw mode; flush buffered marks on any mode change
  const prevModeRef = useRef(mode);
  if (prevModeRef.current !== mode) {
    prevModeRef.current = mode;
    if (mode === "draw") {
      selection.setSelectedIndex(null);
    }
    if (hasUnsavedRef.current) {
      sendValue(marksForFlushRef.current, "batch_update");
      setHasUnsaved(false);
      setUnsavedCount(0);
    }
  }

  // ── Debounced auto-flush: send buffered marks after 2s of inactivity ──
  // drawSeq bumps on every new box drawn, resetting the timeout.
  // Flush only fires when the user stops drawing for 2 seconds.
  useEffect(() => {
    if (!hasUnsaved) return;
    const timer = setTimeout(() => {
      if (hasUnsavedRef.current) {
        sendValue(marksForFlushRef.current, "batch_update");
        setHasUnsaved(false);
        setUnsavedCount(0);
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [drawSeq, hasUnsaved, sendValue]);

  // ── Best-effort flush on unmount ───────────────────────────────────
  useEffect(() => {
    return () => {
      if (hasUnsavedRef.current) {
        const value: ComponentValue = { marks: marksForFlushRef.current, action: "batch_update" };
        Streamlit.setComponentValue(value);
      }
    };
  }, []);

  // Hover handlers with 200ms delay
  const handleHoverEnter = useCallback(
    (e: React.MouseEvent, index: number) => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      const rect = (e.target as Element).getBoundingClientRect();
      const container = (e.target as Element).closest(".redaction-viewer");
      const containerRect = container?.getBoundingClientRect() || rect;

      const x = rect.left - containerRect.left + rect.width / 2;
      // Show above mark by default, below if near top
      const markTop = rect.top - containerRect.top;
      const y = markTop > 80 ? markTop - 8 : rect.bottom - containerRect.top + 8;

      hoverTimerRef.current = setTimeout(() => {
        setHoveredIndex(index);
        setTooltipPos({ x, y: markTop > 80 ? y : rect.bottom - containerRect.top + 8 });
      }, 200);
    },
    []
  );

  const handleHoverLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setHoveredIndex(null);
  }, []);

  // SVG event routing based on mode
  const handleSvgMouseDown = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (caseClosed) return;
      if (mode === "draw") {
        drawing.handleMouseDown(e);
      } else {
        selection.handleSvgMouseDown(e);
      }
    },
    [caseClosed, mode, drawing, selection]
  );

  const handleSvgMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (caseClosed) return;
      if (mode === "draw") {
        drawing.handleMouseMove(e);
      } else {
        selection.handleSvgMouseMove(e);
      }
    },
    [caseClosed, mode, drawing, selection]
  );

  const handleSvgMouseUp = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (caseClosed) return;
      if (mode === "draw") {
        drawing.handleMouseUp(e);
      } else {
        selection.handleSvgMouseUp(e);
      }
    },
    [caseClosed, mode, drawing, selection]
  );

  return (
    <div className="redaction-viewer" style={{ width: pixelW, height: pixelH }}>
      {/* Layer 1: Document page image */}
      <img
        ref={imgRef}
        src={imageDataUrl}
        onLoad={handleImageLoad}
        style={{
          display: "block",
          width: pixelW,
          height: pixelH,
          userSelect: "none",
          pointerEvents: "none",
        }}
        draggable={false}
        alt="Document page"
      />

      {/* Layer 2: SVG overlay */}
      <svg
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: pixelW,
          height: pixelH,
          cursor: caseClosed ? "not-allowed" : mode === "draw" ? "crosshair" : "default",
        }}
        viewBox={`0 0 ${pixelW} ${pixelH}`}
        onMouseDown={handleSvgMouseDown}
        onMouseMove={handleSvgMouseMove}
        onMouseUp={handleSvgMouseUp}
      >
        {marks.map((mark, i) => (
          <rect
            key={`mark-${i}`}
            x={toPixel(mark.pdf_x0, scale)}
            y={toPixel(mark.pdf_y0, scale)}
            width={toPixel(mark.pdf_x1 - mark.pdf_x0, scale)}
            height={toPixel(mark.pdf_y1 - mark.pdf_y0, scale)}
            fill={getMarkFill(i, selection.selectedIndex)}
            stroke={getMarkStroke(mark, i, selection.selectedIndex, privilegeColors)}
            strokeWidth={i === selection.selectedIndex ? 3 : 2}
            strokeDasharray={i === selection.selectedIndex ? "6 3" : "none"}
            className="redaction-mark"
            onMouseEnter={(e) => handleHoverEnter(e, i)}
            onMouseLeave={handleHoverLeave}
            onMouseDown={
              mode === "select" && !caseClosed
                ? (e) => selection.handleMarkMouseDown(e, i)
                : undefined
            }
          />
        ))}

        {/* Unsaved mark count badge */}
        {hasUnsaved && unsavedCount > 0 && (
          <text x={8} y={20} fontSize={13} fill="#ff9900" fontWeight="bold">
            {unsavedCount} unsaved
          </text>
        )}

        {/* Drawing preview rect */}
        {drawing.drawingRect && (
          <DrawingRect
            x={drawing.drawingRect.x}
            y={drawing.drawingRect.y}
            width={drawing.drawingRect.width}
            height={drawing.drawingRect.height}
          />
        )}

        {/* Resize handles for selected mark */}
        {mode === "select" &&
          selection.selectedIndex !== null &&
          marks[selection.selectedIndex] && (
            <ResizeHandles
              mark={marks[selection.selectedIndex]}
              scale={scale}
              onHandleMouseDown={selection.handleHandleMouseDown}
            />
          )}
      </svg>

      {/* Layer 3: Tooltip */}
      {hoveredIndex !== null && marks[hoveredIndex] && (
        <Tooltip
          mark={marks[hoveredIndex]}
          index={hoveredIndex}
          totalMarks={marks.length}
          position={tooltipPos}
          privilegeColors={privilegeColors}
        />
      )}
    </div>
  );
};
