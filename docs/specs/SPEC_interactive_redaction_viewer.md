# Sprint Spec: Interactive Redaction Viewer — Custom Streamlit Component

**Branch:** `beta-2.9` (feature branch from beta-2.9: `feature/redaction-viewer`)
**Priority:** Core UX upgrade — replaces `streamlit-drawable-canvas` with a purpose-built React component
**Status:** Ready for implementation

---

## 1. Problem Statement

The current redaction panel in `4_Review.py` uses `streamlit-drawable-canvas` (a generic Fabric.js wrapper) to render document pages as static background images with redaction rectangles drawn on top. This works, but produces a flat, non-interactive experience:

- No hover tooltips on redaction marks (reviewer can't see the privilege reason without scrolling to the control panel)
- No visual distinction between different privilege categories
- Zoom requires full page re-render at a different DPI (slow, janky)
- The canvas component is a third-party dependency (`streamlit-drawable-canvas-fix==0.9.8`) that has already broken once due to Streamlit internal API changes and required a community fork
- Drawing and viewing are the same surface, which limits what we can do with either

**Goal:** Replace `st_canvas` with a custom Streamlit bidirectional component (`RedactionViewer`) that provides an interactive, modern document review experience while preserving the existing backend (database schema, coordinate system, imaging pipeline, production burn chain) exactly as-is.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  4_Review.py (Python)                                   │
│                                                         │
│  redaction_viewer(                                      │
│      page_image=<base64 PNG>,                           │
│      marks=[{pdf_x0, pdf_y0, pdf_x1, pdf_y1, reason,   │
│              author, timestamp}, ...],                   │
│      scale=<float>,                                     │
│      page_width_pt=<float>,                             │
│      page_height_pt=<float>,                            │
│      mode="draw" | "select",                            │
│      case_closed=<bool>,                                │
│      privilege_colors={reason: hex_color, ...},         │
│      zoom_pct=<int>,                                    │
│      key=<str>,                                         │
│  )                                                      │
│  → returns: {marks: [...], action: "save"|"delete"|None}│
│                                                         │
└────────────────────┬────────────────────────────────────┘
                     │  base64 image + marks JSON ↓
                     │  updated marks JSON ↑
┌────────────────────▼────────────────────────────────────┐
│  RedactionViewer (React component in iframe)            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  <img> layer — document page (CSS-scaled)       │    │
│  ├─────────────────────────────────────────────────┤    │
│  │  <svg> overlay — interactive redaction rects    │    │
│  │    • hover → tooltip with reason/author/time    │    │
│  │    • click → select (highlight border)          │    │
│  │    • drag → reposition (select mode)            │    │
│  │    • handles → resize (select mode)             │    │
│  │    • mousedown+drag → draw new rect (draw mode) │    │
│  ├─────────────────────────────────────────────────┤    │
│  │  Tooltip popover (positioned near hovered rect) │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Streamlit.setComponentValue({marks, action})           │
└─────────────────────────────────────────────────────────┘
```

### Why SVG overlay instead of canvas?

- SVG elements are DOM nodes — they get native hover events, CSS transitions, accessibility attributes, and can be styled per-element without redrawing the entire surface
- The document image stays as an `<img>` tag — the browser handles scaling, caching, and rendering natively
- Redaction rectangles are `<rect>` elements with event handlers — no hit-testing math needed
- Tooltips are standard HTML positioned relative to the SVG element — no custom popover rendering engine

---

## 3. File Structure

```
ediscovery/
├── components/
│   └── redaction_viewer/
│       ├── __init__.py              # Python wrapper: redaction_viewer() function
│       └── frontend/
│           ├── package.json         # Vite + React dependencies
│           ├── vite.config.ts       # Build config
│           ├── tsconfig.json        # TypeScript config
│           └── src/
│               ├── index.tsx        # Entry point, Streamlit handshake
│               ├── RedactionViewer.tsx       # Main component
│               ├── layers/
│               │   ├── ImageLayer.tsx        # Document page image
│               │   └── SvgOverlay.tsx        # Redaction rectangles + interactions
│               ├── ui/
│               │   ├── Tooltip.tsx           # Hover tooltip popover
│               │   ├── DrawingRect.tsx       # In-progress rectangle while drawing
│               │   └── ResizeHandles.tsx     # Corner/edge handles for selected rect
│               ├── hooks/
│               │   ├── useDrawing.ts         # Draw mode mouse event logic
│               │   ├── useSelection.ts       # Select mode click/drag/resize logic
│               │   └── useCoordinates.ts     # PDF-point ↔ pixel conversion
│               ├── types.ts                  # TypeScript interfaces
│               └── styles.css               # Minimal base styles
```

---

## 4. Python Wrapper (`components/redaction_viewer/__init__.py`)

```python
import os
import json
import base64
import streamlit.components.v1 as components

_RELEASE = True

if _RELEASE:
    _component_func = components.declare_component(
        "redaction_viewer",
        path=os.path.join(os.path.dirname(__file__), "frontend", "build"),
    )
else:
    _component_func = components.declare_component(
        "redaction_viewer",
        url="http://localhost:5173",
    )


def redaction_viewer(
    page_image_bytes: bytes,
    marks: list[dict],
    scale: float,
    page_width_pt: float,
    page_height_pt: float,
    mode: str = "draw",
    case_closed: bool = False,
    privilege_colors: dict | None = None,
    zoom_pct: int = 75,
    key: str | None = None,
) -> dict | None:
    """
    Render an interactive redaction viewer for a single document page.

    Parameters
    ----------
    page_image_bytes : bytes
        PNG image of the rendered page (from fitz pixmap).
    marks : list[dict]
        Current redaction marks for this page. Each dict MUST contain:
            pdf_x0, pdf_y0, pdf_x1, pdf_y1  (float, PDF points)
            reason  (str)
        And MAY contain:
            author  (str, username who created the mark)
            created_at  (str, ISO timestamp)
    scale : float
        Current scale factor (DPI / 72). Used for PDF-point ↔ pixel conversion.
    page_width_pt : float
        Page width in PDF points (for bounds checking).
    page_height_pt : float
        Page height in PDF points (for bounds checking).
    mode : str
        "draw" — click-drag creates new rectangles.
        "select" — click selects, drag moves, handles resize.
    case_closed : bool
        If True, component is view-only (no drawing, no moving, no deleting).
    privilege_colors : dict | None
        Mapping of reason string → hex color for mark borders/fills.
        Marks with reasons not in this dict get the default red.
    zoom_pct : int
        Current zoom percentage (for display in tooltip, not for rendering).
    key : str | None
        Streamlit component key for instance identity.

    Returns
    -------
    dict | None
        When the user modifies marks, returns:
        {
            "marks": [
                {
                    "pdf_x0": float, "pdf_y0": float,
                    "pdf_x1": float, "pdf_y1": float,
                    "reason": str
                }, ...
            ],
            "action": "update" | "delete" | None
        }
        Returns None if no changes since last render.
    """
    # Encode image as base64 data URL for JSON transport
    b64_img = base64.b64encode(page_image_bytes).decode("utf-8")
    image_data_url = f"data:image/png;base64,{b64_img}"

    result = _component_func(
        imageDataUrl=image_data_url,
        marks=marks,
        scale=scale,
        pageWidthPt=page_width_pt,
        pageHeightPt=page_height_pt,
        mode=mode,
        caseClosed=case_closed,
        privilegeColors=privilege_colors or {},
        zoomPct=zoom_pct,
        key=key,
        default=None,
    )
    return result
```

### Integration pattern in 4_Review.py

The swap is surgical. Everywhere the current code calls `st_canvas(...)`, it will instead call `redaction_viewer(...)`. The upstream data flow (rendering the page image, loading marks from DB) and the downstream flow (saving marks to DB, writing PDF annotations, syncing tags) remain **identical**.

```python
# BEFORE (current):
from streamlit_drawable_canvas import st_canvas
# ... render page to PIL image ...
_r_canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0.8)", stroke_width=2, stroke_color="#ff0000",
    background_image=_pil_image, height=_h, width=_w,
    drawing_mode=_mode, initial_drawing=_fabric_json,
    key=_key, update_streamlit=True,
)
_r_canvas_objs = [o for o in _r_canvas_result.json_data["objects"] if o["type"] == "rect"]

# AFTER (new):
from components.redaction_viewer import redaction_viewer
# ... render page to PNG bytes (skip PIL conversion) ...
_viewer_result = redaction_viewer(
    page_image_bytes=_png_bytes,
    marks=_existing_marks,          # Already loaded from DB, already has pdf_x0/y0/x1/y1
    scale=_r_scale,
    page_width_pt=_page_w_pt,
    page_height_pt=_page_h_pt,
    mode="draw" if _draw_mode else "select",
    case_closed=_case_closed,
    privilege_colors=_priv_color_map,
    zoom_pct=_r_zoom_pct,
    key=f"rv_{current_cn}_{_r_page_idx}_{_r_zoom_pct}",
)
```

**Key simplification:** The current code juggles Fabric.js JSON, canvas coordinates, scale conversions, and a deletion counter — all because `st_canvas` speaks Fabric.js. The new component speaks PDF points natively, so the Python side just passes marks in/out as-is. The scale-dependent canvas coordinate fields (`canvas_x`, `canvas_y`, `canvas_w`, `canvas_h`) become internal to the React component and never touch the database.

---

## 5. React Component Specification

### 5.1 Props (received from Python via Streamlit)

```typescript
interface RedactionViewerProps {
  imageDataUrl: string;           // base64 data URL of page image
  marks: RedactionMark[];         // existing marks (PDF-point coords)
  scale: number;                  // DPI / 72 — pixel-to-point conversion
  pageWidthPt: number;            // page width in PDF points
  pageHeightPt: number;           // page height in PDF points
  mode: "draw" | "select";       // interaction mode
  caseClosed: boolean;            // read-only flag
  privilegeColors: Record<string, string>;  // reason → hex color
  zoomPct: number;                // current zoom % (display only)
}

interface RedactionMark {
  pdf_x0: number;
  pdf_y0: number;
  pdf_x1: number;
  pdf_y1: number;
  reason: string;
  author?: string;
  created_at?: string;
}
```

### 5.2 Component Value (sent back to Python)

```typescript
interface ComponentValue {
  marks: RedactionMark[];         // full updated marks array
  action: "update" | "delete" | null;
}
```

**When to send:** Call `Streamlit.setComponentValue()` when:
- A new rectangle is drawn (mouseup after draw)
- A rectangle is moved or resized (mouseup after transform)
- A rectangle is deleted (via keyboard Delete or a delete interaction)

**When NOT to send:** Do not send on hover, on select (without move), or on tooltip display. These are view-only interactions that should not trigger a Streamlit rerun.

### 5.3 Coordinate System

All coordinates in `marks` are in **PDF points** (72 DPI). The component converts to pixels for rendering:

```typescript
// PDF points → screen pixels
const toPixel = (pt: number) => pt * scale;

// Screen pixels → PDF points (for new drawings)
const toPoint = (px: number) => px / scale;
```

The component NEVER stores or sends canvas pixel coordinates. The `scale` prop is the single source of truth for conversion. This means zoom changes (which change `scale`) automatically reposition all marks correctly without any coordinate migration.

### 5.4 Rendering Layers

**Layer 1: Document Image**
```tsx
<img
  ref={imgRef}
  src={imageDataUrl}
  onLoad={() => {
    // Set iframe height after image loads so Streamlit doesn't clip
    Streamlit.setFrameHeight(imgRef.current.naturalHeight + TOOLTIP_MARGIN);
  }}
  style={{
    display: "block",
    width: pageWidthPt * scale,    // explicit pixel width from rendered image
    height: pageHeightPt * scale,  // explicit pixel height — no stretching
    userSelect: "none",
    pointerEvents: "none",
  }}
  draggable={false}
/>
```
- The image is sized to match the rendered pixmap dimensions exactly — no CSS stretching, no "width: 100%"
- This means the image is the same size regardless of the Streamlit column width or monitor size
- The Streamlit column provides a scrollable container if the image is wider than the viewport (at high zoom)
- `Streamlit.setFrameHeight()` is called on image load to tell Streamlit how tall the iframe should be — without this, the iframe may clip the bottom of the page or leave dead space (this is a known custom component gotcha)
- `pointerEvents: none` ensures all mouse events fall through to the SVG overlay
- `userSelect: none` prevents accidental text/image selection

**Layer 2: SVG Overlay**
```tsx
<svg
  style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }}
  viewBox={`0 0 ${pageWidthPt * scale} ${pageHeightPt * scale}`}
>
  {marks.map((mark, i) => (
    <rect
      key={i}
      x={toPixel(mark.pdf_x0)}
      y={toPixel(mark.pdf_y0)}
      width={toPixel(mark.pdf_x1 - mark.pdf_x0)}
      height={toPixel(mark.pdf_y1 - mark.pdf_y0)}
      fill={getMarkFill(mark, i)}
      stroke={getMarkStroke(mark, i)}
      strokeWidth={2}
      className="redaction-mark"
      onMouseEnter={() => handleHover(i)}
      onMouseLeave={() => handleHoverEnd()}
      onMouseDown={(e) => handleMarkMouseDown(e, i)}
    />
  ))}
  {drawingRect && <DrawingRect rect={drawingRect} />}
  {selectedIndex !== null && <ResizeHandles mark={marks[selectedIndex]} scale={scale} />}
</svg>
```

**Layer 3: Tooltip (HTML, positioned absolutely)**
```tsx
{hoveredIndex !== null && (
  <Tooltip
    mark={marks[hoveredIndex]}
    position={tooltipPosition}
    privilegeColors={privilegeColors}
  />
)}
```

### 5.5 Interaction Behaviors

#### Draw Mode (`mode === "draw"`)

| Action | Behavior |
|--------|----------|
| Click + drag on empty area | Draw new rectangle (red dashed outline while drawing, snaps to solid on mouseup) |
| Mouseup after draw | New mark added to marks array with `reason: "[Redact — No Privilege Reason]"`. Send updated marks to Python. |
| Hover over existing mark | Show tooltip with reason, author, timestamp |
| Click existing mark | No selection (draw mode doesn't select) |
| Minimum size enforcement | Rectangles smaller than 5×5 PDF points are discarded (prevents accidental micro-clicks) |

#### Select Mode (`mode === "select"`)

| Action | Behavior |
|--------|----------|
| Click on mark | Select it (blue highlight border, show resize handles) |
| Click on empty area | Deselect current selection |
| Drag selected mark | Reposition (constrained to page bounds). On mouseup, send updated marks. |
| Drag resize handle | Resize mark (minimum 5×5 pt, constrained to page bounds). On mouseup, send updated marks. |
| `Delete` key with selection | Remove selected mark from array. Send updated marks with `action: "delete"`. |
| Hover over any mark | Show tooltip (even unselected marks) |
| Double-click mark | No special behavior (reserved for future: inline reason editing) |

#### Case Closed (`caseClosed === true`)

| Action | Behavior |
|--------|----------|
| Hover | Tooltip still shows (read access preserved) |
| Click, drag, draw, delete | All disabled. Cursor shows `not-allowed`. |

### 5.6 Visual Design

#### Mark Appearance

```css
/* Default mark (no privilege color mapping) */
.redaction-mark {
  fill: rgba(0, 0, 0, 0.65);
  stroke: #cc0000;
  stroke-width: 2px;
  cursor: pointer;
  transition: fill 0.15s ease, stroke 0.15s ease;
}

/* Hovered */
.redaction-mark:hover {
  fill: rgba(0, 0, 0, 0.45);
  stroke: #ff3333;
  stroke-width: 2.5px;
}

/* Selected (select mode only) */
.redaction-mark.selected {
  stroke: #3399ff;
  stroke-width: 3px;
  stroke-dasharray: 6 3;
}
```

#### Privilege Color Mapping

When `privilegeColors` is provided, mark borders use the mapped color:
```typescript
function getMarkStroke(mark: RedactionMark, index: number): string {
  if (index === selectedIndex) return "#3399ff";  // selected always blue
  const color = privilegeColors[mark.reason];
  return color || "#cc0000";  // fall back to red
}
```

The fill stays dark (black with opacity) regardless of privilege color — the color coding is on the border only. This preserves the visual intent of a redaction (blacking out content) while giving reviewers a way to quickly scan what privilege category each mark belongs to.

#### Tooltip Design

```
┌──────────────────────────────────┐
│  Attorney-Client Privilege       │  ← reason (bold)
│  ────────────────────────────    │
│  Applied by: jsmith              │  ← author (if available)
│  2026-03-28 14:32                │  ← timestamp (if available)
│  Box 3 of 7                      │  ← position context
│  (142, 305) → (518, 340) pt     │  ← PDF coordinates (for QC)
└──────────────────────────────────┘
```

- Appears on hover after 200ms delay (prevents flicker on mouse traversal)
- Positioned above the mark if space allows, below if near page top
- White background, subtle shadow, 13px font
- Dismisses immediately on mouse leave (no exit delay)
- Max width: 300px, text wraps if reason is long

#### Drawing Feedback

While drawing a new rectangle (mousedown + drag in draw mode):
```css
.drawing-rect {
  fill: rgba(255, 0, 0, 0.15);
  stroke: #cc0000;
  stroke-width: 2px;
  stroke-dasharray: 8 4;
  pointer-events: none;
}
```

Dashed red outline with light red fill — clearly different from saved marks.

#### Resize Handles

Eight handles (four corners + four edge midpoints) shown when a mark is selected:
```css
.resize-handle {
  fill: white;
  stroke: #3399ff;
  stroke-width: 1.5px;
  width: 8px;
  height: 8px;
  cursor: <appropriate resize cursor>;
}
```

---

## 6. Zoom Behavior Change

**Current approach:** Each zoom level re-renders the PDF page at a different DPI, producing a new PNG at a different pixel resolution. The canvas is destroyed and recreated at the new size. Marks are converted from PDF points to new canvas coordinates.

**New approach:** The Python side still renders at the requested DPI (this controls image quality/sharpness). But the React component handles zoom display via CSS — the container scales, all SVG coordinates adjust automatically because they're relative to the viewBox. This means:

- Zoom changes update the image source (for quality) but don't destroy/recreate the component
- Mark positions stay stable because they're always in PDF points
- The transition between zoom levels feels smooth rather than jarky

The Python side continues to pass the pre-rendered image at the appropriate DPI. The React component does NOT do its own zoom math — it just renders what it receives. This keeps the quality control on the Python/PyMuPDF side where it belongs.

### Screen Size & Monitor Differences

The component does NOT adapt to screen size. The rendered image has fixed pixel dimensions determined by the zoom level and DPI calculation on the Python side. If the image is wider than the Streamlit column, the column scrolls horizontally. This is the same behavior as the current `st_canvas` implementation and is intentional — in document review, you want pixel-accurate rendering, not responsive reflow that could shift content relative to redaction marks.

Different monitor sizes effectively change how much of the document is visible at once (a larger monitor shows more of the page without scrolling), but the coordinates and mark alignment are identical everywhere.

### High-DPI / Retina Displays

On Retina displays (devicePixelRatio > 1), the browser renders both the image and the SVG at higher physical resolution. Since the SVG overlay uses the same coordinate space as the image, marks align correctly on all displays. The image may appear slightly soft at low zoom on Retina screens (a 96 DPI render displayed at 192 physical DPI) — this matches current behavior. Users can bump zoom to 125-150% for sharper rendering, or the Python side could optionally detect high-DPI in a future enhancement and render at 2x.

### Streamlit.setFrameHeight() — Critical

The React component MUST call `Streamlit.setFrameHeight()` after the image loads (in the `<img onLoad>` handler). Without this, Streamlit defaults the iframe to a small height and clips the document. This is the #1 gotcha with custom Streamlit components. The height should be set to the rendered image height plus a small margin for tooltips that might extend below the last mark.

---

## 7. Integration with Existing Save/Load Flow

### Loading marks (no change needed):

```python
# Existing code — works as-is
_marks_json = db_manager.get_redaction_marks(case_folder, cn, page_idx)
_marks = json.loads(_marks_json) if _marks_json else []
# Pass _marks directly to redaction_viewer() — it already has pdf_x0/y0/x1/y1
```

### Saving marks (simplified):

```python
# Current save code converts FROM canvas coords TO PDF coords.
# New code receives PDF coords directly from the component.

_viewer_result = redaction_viewer(...)
if _viewer_result and _viewer_result.get("action"):
    _updated_marks = _viewer_result["marks"]
    # marks already have pdf_x0/y0/x1/y1 in PDF points — no conversion needed
    # Add canvas_x/y/w/h fields for backward compatibility with any code that reads them:
    for _m in _updated_marks:
        _m["canvas_x"] = _m["pdf_x0"] * _r_scale
        _m["canvas_y"] = _m["pdf_y0"] * _r_scale
        _m["canvas_w"] = (_m["pdf_x1"] - _m["pdf_x0"]) * _r_scale
        _m["canvas_h"] = (_m["pdf_y1"] - _m["pdf_y0"]) * _r_scale
    _marks_json = json.dumps(_updated_marks)
    db_manager.save_redaction_marks(case_folder, cn, page_idx, _marks_json, username)
    _r_write_page_annotations(_pdf_path, page_idx, _updated_marks, _REDACT_NO_REASON)
    _r_sync_tags(case_folder, cn, _priv_reasons, _REDACT_NO_REASON)
```

### Reason assignment (moved to Python side):

The current system assigns reasons via Streamlit `st.selectbox` widgets in the control panel. This stays in Python — the React component does NOT handle reason assignment. The flow is:

1. User draws a mark → component sends it back with `reason: "[Redact — No Privilege Reason]"`
2. Python receives the updated marks and re-renders the control panel with reason dropdowns
3. User selects a reason → Python updates the mark's reason field
4. On save, all marks (with reasons) are persisted

This keeps reason selection in native Streamlit widgets where it's already working well, and avoids building a dropdown UI inside the React component.

---

## 8. Eliminating `streamlit-drawable-canvas` Dependency

Once the new component is validated:

1. Remove `streamlit-drawable-canvas-fix==0.9.8` from `requirements.txt`
2. Remove the try/except import block in `4_Review.py` (lines 39-43)
3. Remove `CANVAS_AVAILABLE` checks
4. Remove `_r_marks_to_drawing()` function (Fabric.js conversion no longer needed)
5. Remove deletion counter logic (`_r_del_counter_key`) — the component handles selection/deletion natively
6. Remove the Fabric.js JSON extraction code (`_r_canvas_objs` filtering for `type == "rect"`)

This eliminates a fragile third-party dependency that has already required a forked fix.

---

## 9. Build & Deployment

### Development workflow:

```bash
cd components/redaction_viewer/frontend
npm install
npm run dev          # starts Vite dev server on localhost:5173
```

In `__init__.py`, set `_RELEASE = False` during development.

### Production build:

```bash
cd components/redaction_viewer/frontend
npm run build        # outputs to frontend/build/
```

Set `_RELEASE = True`. The built static files are served directly by Streamlit — no separate server needed.

### Requirements:

- Node.js (for building the frontend only — not needed at runtime)
- No new Python dependencies (uses `streamlit.components.v1` which is built into Streamlit)
- The `frontend/build/` directory MUST be committed to git so the component works without Node.js on the deployment machine

---

## 10. Security & Defensibility Considerations

### Coordinate Integrity

The component operates in an iframe sandbox. All mark coordinates are validated on the Python side before persistence:

```python
def _validate_marks(marks, page_width_pt, page_height_pt):
    """Ensure all marks are within page bounds and have valid geometry."""
    validated = []
    for m in marks:
        x0 = max(0, min(m["pdf_x0"], page_width_pt))
        y0 = max(0, min(m["pdf_y0"], page_height_pt))
        x1 = max(0, min(m["pdf_x1"], page_width_pt))
        y1 = max(0, min(m["pdf_y1"], page_height_pt))
        if x1 > x0 and y1 > y0:  # valid geometry
            validated.append({
                "pdf_x0": round(x0, 2),
                "pdf_y0": round(y0, 2),
                "pdf_x1": round(x1, 2),
                "pdf_y1": round(y1, 2),
                "reason": m.get("reason", "[Redact — No Privilege Reason]"),
            })
    return validated
```

This prevents:
- Marks with coordinates outside the page bounds (could indicate tampering)
- Zero-area or negative-area marks
- Floating point precision drift

### Audit Trail

All mark modifications continue to flow through `db_manager.save_redaction_marks()` and `log_audit()` — the component change is purely a rendering concern. The audit contract is preserved.

### Production Burn Integrity

The production burn pipeline in `5_Production.py` reads `marks_json` from the database and applies redactions using `pdf_x0/y0/x1/y1` coordinates via PyMuPDF. This pipeline is completely unaffected by the viewer change — it never touches the viewer component.

### No External Network Calls

The React component loads no external resources. All assets (image data, mark data) are passed as props from the Python backend. The component runs entirely within the Streamlit iframe with no outbound requests.

---

## 11. Implementation Order

### Phase 1: Scaffold & basic rendering (get something on screen)
1. Create `components/redaction_viewer/` directory structure
2. Set up `frontend/package.json` with Vite, React, TypeScript
3. Implement `index.tsx` with Streamlit handshake
4. Implement basic `RedactionViewer.tsx`: render image + static SVG rects from marks
5. Implement `__init__.py` Python wrapper
6. Test: can we render a document page with existing marks visible?

### Phase 2: Draw mode
1. Implement `useDrawing` hook (mousedown → mousemove → mouseup on SVG)
2. Implement `DrawingRect.tsx` (dashed preview while drawing)
3. Wire up `Streamlit.setComponentValue()` on draw completion
4. Integrate in `4_Review.py`: replace `st_canvas` call, verify marks save to DB correctly
5. Test: draw a mark, save, reload page — does the mark persist?

### Phase 3: Select mode
1. Implement `useSelection` hook (click to select, drag to move)
2. Implement `ResizeHandles.tsx` (8-handle resize on selected mark)
3. Implement Delete key handling
4. Wire up `setComponentValue()` on move/resize/delete completion
5. Test: select, move, resize, delete — do all operations round-trip correctly?

### Phase 4: Interactivity polish
1. Implement `Tooltip.tsx` with hover delay
2. Implement privilege color mapping on mark borders
3. Add CSS transitions for hover/select states
4. Add `caseClosed` read-only enforcement
5. Implement minimum-size enforcement (5×5 pt)
6. Implement page-bounds clamping on draw/move/resize

### Phase 5: Integration & cleanup
1. Remove `streamlit-drawable-canvas` import and all Fabric.js conversion code
2. Remove `_r_marks_to_drawing()`, deletion counter logic, canvas object extraction
3. Add `_validate_marks()` on the Python save path
4. Update `requirements.txt` (remove canvas dependency)
5. Run through full workflow: draw marks → assign reasons → save → navigate away → return → verify marks → clear → verify clear → production burn → verify burn output
6. Build frontend for production (`npm run build`), commit `build/` directory

### Phase 6: Verification
1. Create a test document with known redaction marks, verify coordinates match between old and new viewer
2. Test all zoom levels — marks should stay correctly positioned
3. Test with case_closed=True — all edits should be blocked
4. Test with long documents (50+ pages) — navigation should remain snappy
5. Test mark reasons: no-reason, privilege categories, custom text — all should display in tooltips
6. Verify audit log entries are created for all mark modifications
7. Run production burn on a document with marks created in the new viewer — verify output PDF

---

## 12. Rollback Plan

The old `st_canvas` code is preserved on `beta-2.8` (and in git history on `beta-2.9` before this feature branch merges). If the new component has issues:

1. The database schema and `marks_json` format are **identical** — marks created with the new viewer work with the old viewer and vice versa
2. Revert the `4_Review.py` changes to restore `st_canvas` usage
3. Re-add `streamlit-drawable-canvas-fix` to `requirements.txt`
4. The `components/redaction_viewer/` directory can be left in place or removed — it has no effect unless imported

This is a zero-risk swap at the data layer. The only risk is UI functionality during the transition, which is why we're doing it on a feature branch.

---

## 13. Future Enhancements (NOT in this sprint)

These are explicitly out of scope but the architecture supports them:

- **Keyboard shortcuts**: Arrow keys for page nav, Ctrl+Z for undo, number keys for quick reason assignment
- **Minimap**: Thumbnail strip showing all pages with indicators for which pages have marks
- **Side-by-side view**: Original vs. redacted preview toggle
- **Text-level redaction**: Would require PDF.js integration (Tier 3) — a separate future project
- **Batch redaction**: Select multiple marks, assign same reason to all
- **Redaction templates**: Save a set of coordinates as a template, apply to similar documents
- **Mark numbering overlay**: Show mark index numbers on the SVG overlay for reference during QC

---

## 14. Acceptance Criteria

The feature is complete when:

- [ ] A reviewer can open a document in the Redact tab and see all existing marks rendered interactively
- [ ] Hovering over any mark shows a tooltip with reason, author, and timestamp
- [ ] Drawing a new rectangle in draw mode creates a mark with correct PDF-point coordinates
- [ ] Selecting, moving, and resizing marks in select mode updates coordinates correctly
- [ ] Deleting a mark via keyboard removes it and persists the change
- [ ] All zoom levels render marks at correct positions
- [ ] Case-closed documents show marks with tooltips but block all modifications
- [ ] Privilege color coding is visible on mark borders when colors are configured
- [ ] Production burn output is identical whether marks were created with old or new viewer
- [ ] `streamlit-drawable-canvas` dependency is removed
- [ ] No external network requests from the component
- [ ] All mark modifications create audit log entries
- [ ] `frontend/build/` is committed so deployment doesn't require Node.js
