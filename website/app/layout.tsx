import type { Metadata } from "next";
import { ViewTransition } from "react";
import { Cormorant_Garamond, Cutive_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { MotionProvider } from "@/components/motion-provider";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { SmoothScroll } from "@/components/smooth-scroll";
import { ViewportFrame } from "@/components/viewport-frame";
import { SOCIALS } from "@/lib/socials";
import "./globals.css";

const cutiveMono = Cutive_Mono({
  variable: "--font-cutive",
  weight: "400",
  subsets: ["latin"],
});

const cormorant = Cormorant_Garamond({
  variable: "--font-display",
  weight: ["300", "400", "500", "600", "700"],
  style: ["normal", "italic"],
  subsets: ["latin"],
});

const DESCRIPTION =
  "Obsidura is a cloud for small software: the purpose-built tools agents make easy to write but the big clouds make hard to deploy and share. Powered by our engine, Pantheon, it runs your tools in a secure, governed environment and makes sharing one with a colleague as easy as sharing a doc.";

export const metadata: Metadata = {
  metadataBase: new URL("https://obsidura.com"),
  title: "Obsidura | A Cloud for Small Software",
  description: DESCRIPTION,
  alternates: {
    canonical: "/",
  },
};

// Organization + WebSite + SoftwareApplication structured data for search
// engines. Only fields we can honestly claim - no invented ratings, prices,
// or certifications.
const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://obsidura.com/#organization",
      name: "Obsidura",
      url: "https://obsidura.com",
      logo: "https://obsidura.com/logo-mark.png",
      email: "contact@obsidura.com",
      description: DESCRIPTION,
      sameAs: SOCIALS.map((s) => s.href),
    },
    {
      "@type": "WebSite",
      "@id": "https://obsidura.com/#website",
      name: "Obsidura",
      url: "https://obsidura.com",
      publisher: { "@id": "https://obsidura.com/#organization" },
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://obsidura.com/#software",
      name: "Pantheon",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web, Linux",
      url: "https://obsidura.com",
      description:
        "Pantheon is the engine behind Obsidura's cloud for small software: it runs purpose-built tools in a secure, governed environment, with access scoped to each person's role and every run recorded.",
      publisher: { "@id": "https://obsidura.com/#organization" },
    },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${cormorant.variable} ${cutiveMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col paper-grain">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        {/* Obsidian is the house palette - black volcanic glass is the
            material the name claims - so dark is the default and light is
            the opt-out, kept one click away on the toggle. */}
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          {/* First focusable on every page. Parked above the viewport and
              slid in on keyboard focus, so mouse users never see it and a
              keyboard user is offered it before the nav's five stops. */}
          <a
            href="#content"
            className="kicker fixed top-4 left-4 z-[200] -translate-y-24 bg-accent px-5 py-3 !text-paper transition-transform focus-visible:translate-y-0"
          >
            Skip to content
          </a>
          <SmoothScroll />
          <ViewportFrame />
          <MotionProvider>
            {/* Nav and Footer live in the layout so they persist across
                client navigations; only the page content transitions. */}
            <Nav />
            {/*
              Links that move between chapters declare their direction with
              transitionTypes, and the page slides to match: forward pushes
              left, back pushes right. Untagged navigations (deep links, the
              browser's own back button) fall through to the plain rise.
            */}
            <ViewTransition
              enter={{
                "nav-forward": "nav-forward",
                "nav-back": "nav-back",
                default: "page-enter",
              }}
              exit={{
                "nav-forward": "nav-forward",
                "nav-back": "nav-back",
                default: "page-exit",
              }}
            >
              {children}
            </ViewTransition>
            <Footer />
          </MotionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
