/** The homepage's three points. */
export const POINTS = [
  "Obsidura unifies the entire software lifecycle, enabling businesses to create, deploy, customize, secure, and maintain applications across cloud, on-premises, and air-gapped environments.",
  "Our agent-native infrastructure connects applications, data, and AI models through a common backend with enforced permissions, automated maintenance, and comprehensive auditability - sensible defaults for all software.",
  "Built for security, compliance, and cost efficiency, Obsidura makes complex software infrastructure simple, scalable, and accessible.",
];

export const NUMERALS = ["I", "II", "III"];

/**
 * The team film's chapters, read off the film's own section labels. `at`
 * is the second the chapter's first title appears.
 */
export const CHAPTERS = [
  { at: 0, title: "The problem" },
  { at: 22, title: "What we are" },
  { at: 40, title: "How it works" },
  { at: 76, title: "Agents, safely" },
  { at: 94, title: "Reproducible" },
  { at: 121, title: "Inside the data center" },
  { at: 166, title: "What we have built" },
  { at: 211, title: "Where we are" },
] as const;

export const FILM_LENGTH = 237.6;

export const timecode = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
