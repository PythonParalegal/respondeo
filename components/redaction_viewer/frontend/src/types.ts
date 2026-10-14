export interface RedactionMark {
  pdf_x0: number;
  pdf_y0: number;
  pdf_x1: number;
  pdf_y1: number;
  reason: string;
  author?: string;
  created_at?: string;
}

export interface RedactionViewerProps {
  imageDataUrl: string;
  marks: RedactionMark[];
  scale: number;
  pageWidthPt: number;
  pageHeightPt: number;
  mode: "draw" | "select";
  caseClosed: boolean;
  privilegeColors: Record<string, string>;
  zoomPct: number;
}

export interface ComponentValue {
  marks: RedactionMark[];
  action: "update" | "delete" | "batch_update" | null;
}
