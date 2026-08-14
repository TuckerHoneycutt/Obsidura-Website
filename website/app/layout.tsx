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
  "Pantheon is a workflow automation platform for defining, running, and managing reliable processes - ordinary scripted tasks and AI agents in the same job. It connects the systems your information is scattered across and runs work across them on a schedule or on demand, scoped to whoever asked and recorded end to end.";

export const metadata: Metadata = {
  metadataBase: new URL("https://obsidura.com"),
  title: "Obsidura Pantheon | All-Purpose Workflow Automation Platform",
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
        "Pantheon is Obsidura's all-purpose workflow automation platform: processes declared as YAML and compiled into a typed graph, scripted tasks and AI agents executed the same way, contracts validated at every seam, a run-scoped resource proxy that holds all credentials, and an append-only run log. Processes run on a schedule or are called on demand by anyone permitted.",
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
