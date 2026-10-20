import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const dynamic = "force-static";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Obsidura | A Cloud for Small Software";

export default async function OpenGraphImage() {
  const logo = await readFile(join(process.cwd(), "public/obsidura-mark-white.png"));
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
        { }
        <img src={logoSrc} alt="" width={262} height={270} />
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
              fontSize: 22,
              color: "#bfbfbf",
              letterSpacing: 5,
              marginTop: 20,
              display: "flex",
            }}
          >
            A CLOUD FOR SMALL SOFTWARE
          </div>
        </div>
      </div>
    ),
    size
  );
}
