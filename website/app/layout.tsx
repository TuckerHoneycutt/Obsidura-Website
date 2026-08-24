import type { Metadata } from "next";
import { ViewTransition } from "react";
import { Cormorant_Garamond, Cutive_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { CommandMenu } from "@/components/command-menu";
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
  "Pantheon is Obsidura's data layer for AI agents. It aggregates the data scattered across your systems into one secure, governed layer and sets agents to work against it - recurring jobs on a schedule, one-off actions, whole workflows, or questions asked in plain English and answered from the context of your data. Access is scoped to each person's role, and every step is recorded end to end.";

export const metadata: Metadata = {
  metadataBase: new URL("https://obsidura.com"),
  title: "Obsidura Pantheon | The Secure Data Layer for AI Agents",
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
        "Pantheon is Obsidura's data layer for AI agents: connectors aggregate the systems your data lives in into one governed layer, scripted tasks and AI agents run against it the same way, every resource call passes through a run-scoped proxy enforcing role-based grants, and an append-only run log records every step. Work runs as recurring scheduled jobs, one-off actions, whole workflows, or plain-English questions answered from your data.",
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
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          <SmoothScroll />
          <ViewportFrame />
          <MotionProvider>
            {/* Nav and Footer live in the layout so they persist across
                client navigations; only the page content transitions. */}
            <Nav />
            <CommandMenu />
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
