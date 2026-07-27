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

export const metadata: Metadata = {
  metadataBase: new URL("https://obsidura.com"),
  title: "Obsidura - Agentic Backend as a Service",
  description:
    "Obsidura orchestrates agents that connect to your company backend and run your operations - durable, audited, and escalation-aware.",
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
