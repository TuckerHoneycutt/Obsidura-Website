function Seal({ className }: { className: string }) {
  return (
    <span
      aria-hidden
      className={`absolute size-[7px] border border-rule bg-paper ${className}`}
    />
  );
}

/**
 * Persistent hairline frame around the viewport, echoing the frame-panel
 * language. The page scrolls inside it like a mounted plate.
 */
export function ViewportFrame() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-3 z-[80] hidden border border-rule md:block"
    >
      <Seal className="-top-1 -left-1" />
      <Seal className="-top-1 -right-1" />
      <Seal className="-bottom-1 -left-1" />
      <Seal className="-bottom-1 -right-1" />
    </div>
  );
}
