"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Background Ripple Effect": a field of square cells; click
 * one and a ripple runs outward through the grid from that cell.
 *
 * Adapted: cell colours come from the site's --rule and --paper-warm tokens
 * (so the grid inverts with the theme instead of keying off a dark: class
 * this site does not use), and the invalid opacity-600 utility is dropped.
 * The grid is decoration - the whole field is aria-hidden.
 */
export function BackgroundRippleEffect({
  rows = 8,
  cols = 27,
  cellSize = 56,
  className,
}: {
  rows?: number;
  cols?: number;
  cellSize?: number;
  className?: string;
}) {
  const [clickedCell, setClickedCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [rippleKey, setRippleKey] = useState(0);

  return (
    <div
      aria-hidden
      className={cn("absolute inset-0 h-full w-full overflow-hidden", className)}
    >
      <DivGrid
        key={`base-${rippleKey}`}
        className="mask-radial-from-20% mask-radial-at-top"
        rows={rows}
        cols={cols}
        cellSize={cellSize}
        clickedCell={clickedCell}
        onCellClick={(row, col) => {
          setClickedCell({ row, col });
          setRippleKey((k) => k + 1);
        }}
      />
    </div>
  );
}

type CellStyle = CSSProperties & {
  ["--delay"]?: string;
  ["--duration"]?: string;
};

function DivGrid({
  className,
  rows,
  cols,
  cellSize,
  clickedCell,
  onCellClick,
}: {
  className?: string;
  rows: number;
  cols: number;
  cellSize: number;
  clickedCell: { row: number; col: number } | null;
  onCellClick: (row: number, col: number) => void;
}) {
  const cells = useMemo(
    () => Array.from({ length: rows * cols }, (_, idx) => idx),
    [rows, cols]
  );

  return (
    <div
      className={cn("relative z-[3]", className)}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`,
        gridTemplateRows: `repeat(${rows}, ${cellSize}px)`,
        width: cols * cellSize,
        height: rows * cellSize,
        // The grid is wider than most screens; centre it on the section so
        // it overflows evenly on both sides rather than off the right.
        left: "50%",
        translate: "-50% 0",
      }}
    >
      {cells.map((idx) => {
        const rowIdx = Math.floor(idx / cols);
        const colIdx = idx % cols;
        const distance = clickedCell
          ? Math.hypot(clickedCell.row - rowIdx, clickedCell.col - colIdx)
          : 0;
        const style: CellStyle = clickedCell
          ? {
              "--delay": `${Math.max(0, distance * 55)}ms`,
              "--duration": `${200 + distance * 80}ms`,
            }
          : {};

        return (
          <div
            key={idx}
            className={cn(
              "cell relative border-[0.5px] border-rule bg-paper-warm opacity-40 shadow-[0px_0px_40px_1px_var(--accent-pale)_inset] transition-opacity duration-150 will-change-transform hover:opacity-80",
              clickedCell && "animate-cell-ripple [animation-fill-mode:none]"
            )}
            style={style}
            onClick={() => onCellClick(rowIdx, colIdx)}
          />
        );
      })}
    </div>
  );
}
