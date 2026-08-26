import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

// Next.js emits inline bootstrap scripts and motion sets inline style
// attributes, so both need 'unsafe-inline'. Dev additionally needs
// 'unsafe-eval' for React Refresh; production does not get it.
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "upgrade-insecure-requests",
].join("; ");

const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: contentSecurityPolicy,
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  experimental: {
    viewTransition: true,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  // Old paths keep resolving so anything already linked or indexed lands on
  // the page that replaced it.
  async redirects() {
    return [
      // /platform was split into the chapter pages; workflows is the part
      // that carried most of it.
      {
        source: "/platform",
        destination: "/workflows",
        permanent: true,
      },
      // The reports chapter was rebroadened into the works chapter: reports
      // are one of the jobs Pantheon runs, not the product.
      {
        source: "/reports",
        destination: "/automations",
        permanent: true,
      },
      {
        source: "/solutions/finance-operations",
        destination: "/solutions/financial-audit",
        permanent: true,
      },
      {
        source: "/solutions/customer-support",
        destination: "/solutions/flight-diagnostics",
        permanent: true,
      },
      {
        source: "/solutions/revenue-operations",
        destination: "/solutions/clinical-summary",
        permanent: true,
      },
      // The about page folded into contact. Temporary rather than permanent:
      // a standalone about page may yet come back, and a 308 would be cached
      // past its welcome.
      {
        source: "/about",
        destination: "/contact",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
