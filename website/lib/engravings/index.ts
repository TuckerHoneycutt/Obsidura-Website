/**
 * The engravings are large - roughly 70KB of ASCII across the six - and they
 * are purely decorative (every plate is aria-hidden). Importing them into the
 * page tree put that text in the prerendered HTML *and* again in the RSC
 * payload for the same bytes twice.
 *
 * Here they are addressed by name instead, so a plate can pull its own art in
 * a separate chunk once it nears the viewport. Nothing but the name and the
 * line count ships up front.
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
  /** Rows in the art - a plate reserves its height from this before loading. */
  lines: number;
};

export const ENGRAVINGS: Record<EngravingName, Engraving> = {
  "athena-owl": {
    load: () => import("./athena-owl").then((m) => m.ATHENA_OWL),
    lines: 45,
  },
  hades: {
    load: () => import("./hades").then((m) => m.HADES),
    lines: 109,
  },
  hephaestus: {
    load: () => import("./hephaestus").then((m) => m.HEPHAESTUS),
    lines: 52,
  },
  herakles: {
    load: () => import("./herakles").then((m) => m.HERAKLES),
    lines: 56,
  },
  olympus: {
    load: () => import("./olympus").then((m) => m.OLYMPUS),
    lines: 83,
  },
  poseidon: {
    load: () => import("./poseidon").then((m) => m.POSEIDON),
    lines: 109,
  },
  zeus: {
    load: () => import("./zeus").then((m) => m.ZEUS),
    lines: 109,
  },
};
