import Image from "next/image";

/**
 * The Obsidura mark, mounted as a static plate. Kept as a named component
 * so the hero mount can swap presentation without touching page layout.
 */
export function TracedMark() {
  return (
    <div className="relative aspect-square w-full">
      <Image
        src="/logo-mark.svg"
        alt=""
        fill
        unoptimized
        priority
        className="logo-invert object-contain select-none"
      />
    </div>
  );
}
