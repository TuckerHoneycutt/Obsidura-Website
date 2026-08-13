/**
 * The engravings are large - roughly 80KB of ASCII across the seven - and
 * they are purely decorative (every one is aria-hidden). Importing them into
 * the page tree put that text in the prerendered HTML *and* again in the RSC
 * payload: the same bytes twice.
 *
 * Here they are addressed by name instead, so a page can pull its own art in
 * a separate chunk once it nears the viewport. Nothing but the name and the
 * measured grid ships up front.
 */
export type EngravingName =
  | "athena-owl"
  | "hades"
  | "hephaestus"
  | "herakles"
  | "olympus"
  | "poseidon"
  | "zeus";

type Engraving = {
  load: () => Promise<string>;
  /** Rows in the art. */
  lines: number;
  /** Longest row, in characters. Together with lines this is the art's own
   *  grid, which is what lets a plate size itself to fill a container
   *  exactly rather than being pinned to an arbitrary font size. */
  cols: number;
};

export const ENGRAVINGS: Record<EngravingName, Engraving> = {
  "athena-owl": {
    load: () => import("./athena-owl").then((m) => m.ATHENA_OWL),
    lines: 46,
    cols: 94,
  },
  hades: {
    load: () => import("./hades").then((m) => m.HADES),
    lines: 110,
    cols: 137,
  },
  hephaestus: {
    load: () => import("./hephaestus").then((m) => m.HEPHAESTUS),
    lines: 53,
    cols: 157,
  },
  herakles: {
    load: () => import("./herakles").then((m) => m.HERAKLES),
    lines: 57,
    cols: 157,
  },
  olympus: {
    load: () => import("./olympus").then((m) => m.OLYMPUS),
    lines: 83,
    cols: 170,
  },
  poseidon: {
    load: () => import("./poseidon").then((m) => m.POSEIDON),
    lines: 110,
    cols: 144,
  },
  zeus: {
    load: () => import("./zeus").then((m) => m.ZEUS),
    lines: 110,
    cols: 143,
  },
};

/** Advance width of Cutive Mono as a fraction of the em. */
export const CHAR_RATIO = 0.6;
