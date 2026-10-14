/**
 * PDF-point <-> pixel coordinate conversion utilities.
 * Scale = DPI / 72; all mark coordinates are stored in PDF points.
 */
export function toPixel(pt: number, scale: number): number {
  return pt * scale;
}

export function toPoint(px: number, scale: number): number {
  return px / scale;
}

/** Clamp a value to [min, max]. */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
