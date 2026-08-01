import type { Metadata } from "next";
import { Cormorant_Garamond, Cutive_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { MotionProvider } from "@/components/motion-provider";
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
  "Deploy auditable AI agents across your databases, APIs, and business systems with durable workflows, human escalation, and cloud, VPC, or on-premises deployment.";

export const metadata: Metadata = {
  metadataBase: new URL("https://obsidura.com"),
  title: "Obsidura | Backend-Native AI Agent Orchestration",
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
        "Pantheon is Obsidura's AI agent orchestration suite: typed connectors into backend systems, a durable workflow runtime, human-in-the-loop escalation, and an append-only audit log.",
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
          <MotionProvider>{children}</MotionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
