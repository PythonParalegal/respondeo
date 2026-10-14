import React from "react";

interface DrawingRectProps {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const DrawingRect: React.FC<DrawingRectProps> = ({ x, y, width, height }) => (
  <rect
    x={x}
    y={y}
    width={width}
    height={height}
    className="drawing-rect"
  />
);
