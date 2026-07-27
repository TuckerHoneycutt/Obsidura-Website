"use client";

import { useEffect, useRef } from "react";
import { FramePanel } from "@/components/ui/frame-panel";

const COLS = 58;
const ROWS = 30;
const RAMP = " .:-=+*#%@";
const ARMS = 4;
const SAMPLES = 170;
const SX = 22;
const SY = 12; // chars are ~2x taller than wide, so y is compressed

/**
 * ASCII rendition of the Obsidura pinwheel mark: four wavy tentacle arms
 * radiating from center. The whole mark slowly rotates while a wave travels
 * outward along each arm; a high-frequency shimmer fakes the braid texture.
 * The arms bow away from the cursor while the pointer is over the panel.
 */
export function AsciiMark() {
  const preRef = useRef<HTMLPreElement>(null);
  // Pointer state in logical mark coordinates, smoothed in the frame loop.
  const mouse = useRef({ x: 0, y: 0, strength: 0, active: false });

  useEffect(() => {
    const pre = preRef.current;
    if (!pre) return;

    const stars: [number, number][] = Array.from({ length: 46 }, () => [
      Math.floor(Math.random() * COLS),
      Math.floor(Math.random() * ROWS),
    ]);

    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    let raf = 0;
    const start = performance.now();

    const render = (t: number) => {
      const m = mouse.current;
      m.strength += ((m.active ? 1 : 0) - m.strength) * 0.06;

      const bright: number[][] = Array.from({ length: ROWS }, () =>
        Array(COLS).fill(0)
      );

      const rot = t * 0.35;
      for (let k = 0; k < ARMS; k++) {
        const theta = (k * Math.PI) / 2 + rot;
        const cos = Math.cos(theta);
        const sin = Math.sin(theta);
        for (let i = 0; i <= SAMPLES; i++) {
          const s = i / SAMPLES;
          const r = 0.06 + s;
          // Traveling wave, amplified toward the tip like the logo's S-curve.
          const wig = 0.16 * Math.sin(s * 6.2 - t * 1.6) * (0.3 + 0.7 * s);
          let cx = r * cos - wig * sin;
          let cy = r * sin + wig * cos;

          // Cursor repulsion: arms bow away with a soft gaussian falloff.
          if (m.strength > 0.01) {
            const dx = cx - m.x;
            const dy = cy - m.y;
            const d2 = dx * dx + dy * dy;
            const push =
              (Math.exp(-d2 / 0.12) * 0.22 * m.strength * s) /
              (Math.sqrt(d2) + 0.08);
            cx += dx * push;
            cy += dy * push;
          }

          const w = 0.05 * (1 - s) + 0.006; // half-thickness, tapers to tip
          const braid = 0.75 + 0.25 * Math.sin(s * 48 - t * 2.6);
          for (let o = -2; o <= 2; o++) {
            const off = (o / 2) * w;
            // The y offset is damped so thickness stays visually constant as
            // arms rotate between horizontal and vertical (cells are ~2x
            // taller than wide, and SX/SY don't fully cancel that out).
            const x = cx - off * sin;
            const y = cy + off * cos * 0.85;
            const px = Math.round(COLS / 2 + x * SX);
            const py = Math.round(ROWS / 2 - y * SY);
            if (px < 0 || px >= COLS || py < 0 || py >= ROWS) continue;
            const b =
              (1 - (Math.abs(o) / 2) ** 2 * 0.85) *
              braid *
              (0.45 + 0.55 * (1 - s));
            if (b > bright[py][px]) bright[py][px] = b;
          }
        }
      }

      const rows: string[] = [];
      for (let y = 0; y < ROWS; y++) {
        let row = "";
        for (let x = 0; x < COLS; x++) {
          const b = bright[y][x];
          if (b > 0.02) {
            const idx = Math.min(
              RAMP.length - 1,
              Math.max(1, Math.floor(b * RAMP.length))
            );
            row += RAMP[idx];
          } else {
            row += " ";
          }
        }
        rows.push(row);
      }
      for (const [x, y] of stars) {
        if (rows[y][x] === " ") {
          rows[y] = rows[y].slice(0, x) + "." + rows[y].slice(x + 1);
        }
      }

      pre.textContent = rows.join("\n");
    };

    if (reduced) {
      render(0.4);
      return;
    }

    const frame = (now: number) => {
      render((now - start) / 1000);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  const toLogical = (e: React.PointerEvent<HTMLPreElement>) => {
    const rect = preRef.current?.getBoundingClientRect();
    if (!rect) return;
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    mouse.current.x = ((fx - 0.5) * COLS) / SX;
    mouse.current.y = (-(fy - 0.5) * ROWS) / SY;
  };

  return (
    <FramePanel className="bg-paper-warm/40">
      <div className="flex items-center justify-between border-b border-rule px-4 py-2">
        <span className="kicker">yggdrasil core</span>
        <span className="kicker text-accent">live</span>
      </div>
      <pre
        ref={preRef}
        aria-hidden
        onPointerMove={(e) => {
          mouse.current.active = true;
          toLogical(e);
        }}
        onPointerLeave={() => {
          mouse.current.active = false;
        }}
        className="select-none overflow-hidden px-4 py-3 font-mono text-[9px] leading-[13px] text-ink-soft sm:text-[10px] sm:leading-[14px]"
      />
      <div className="flex items-center justify-between border-t border-rule px-4 py-2">
        <span className="kicker">obsidura://yggdrasil.0</span>
        <span className="kicker">fig. 01</span>
      </div>
    </FramePanel>
  );
}
