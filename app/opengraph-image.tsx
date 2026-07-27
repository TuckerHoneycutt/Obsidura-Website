import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Obsidura - Agentic Backend as a Service";

export default async function OpenGraphImage() {
  const logo = await readFile(join(process.cwd(), "public/logo-mark.png"));
  const logoSrc = `data:image/png;base64,${logo.toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 72,
          background: "#000000",
        }}
      >
        <div
          style={{
            display: "flex",
            background: "#ffffff",
            borderRadius: 20,
            padding: 28,
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoSrc} alt="" width={220} height={220} />
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              fontSize: 88,
              color: "#ffffff",
              letterSpacing: 20,
              display: "flex",
            }}
          >
            OBSIDURA
          </div>
          <div
            style={{
              fontSize: 26,
              color: "#bfbfbf",
              letterSpacing: 8,
              marginTop: 20,
              display: "flex",
            }}
          >
            AGENTIC BACKEND AS A SERVICE
          </div>
        </div>
      </div>
    ),
    size
  );
}
