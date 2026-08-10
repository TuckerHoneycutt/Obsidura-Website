import Image from "next/image";

/**
 * The Obsidura mark, mounted as a static plate. Uses the PNG asset framed
 * to the same content-to-canvas ratio as logo-mark.svg so it reads at the
 * same size in the hero mount.
 */
export function TracedMark() {
  return (
    <div className="relative aspect-square w-full">
      <Image
        src="/B4DFB728-E5CB-40C2-91A9-E602F3B0FD3F.png?v=svg-match"
        alt=""
        fill
        unoptimized
        priority
        className="logo-invert object-contain select-none"
      />
    </div>
  );
}
