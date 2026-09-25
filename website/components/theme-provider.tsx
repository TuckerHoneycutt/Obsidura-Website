"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * next-themes renders an inline script that sets the theme class before first
 * paint. It only needs to run from the server HTML; React 19 warns whenever it
 * renders a script tag on the client. Marking the client copy as text/plain
 * keeps it inert, so React has nothing to warn about, while the server copy
 * still runs as JavaScript.
 */
export function ThemeProvider(
  props: React.ComponentProps<typeof NextThemesProvider>
) {
  return (
    <NextThemesProvider
      {...props}
      scriptProps={{
        type: typeof window === "undefined" ? "text/javascript" : "text/plain",
      }}
    />
  );
}
