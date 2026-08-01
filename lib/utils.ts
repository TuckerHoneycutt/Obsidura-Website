import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const ROMAN_NUMERALS = [
  "i",
  "ii",
  "iii",
  "iv",
  "v",
  "vi",
  "vii",
  "viii",
  "ix",
  "x",
  "xi",
  "xii",
];

/**
 * Lowercase Roman numeral for small ordinals - kickers uppercase it via
 * CSS. Falls back to the plain number beyond xii.
 */
export function romanNumeral(n: number): string {
  return ROMAN_NUMERALS[n - 1] ?? String(n);
}
