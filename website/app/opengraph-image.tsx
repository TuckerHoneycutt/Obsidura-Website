import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const dynamic = "force-static";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Obsidura | A Cloud for Small Software";

/**
 * The same lockup the footer shows: the brand banner, inverted to white
 * for the black paper, with the tagline set as a kicker in Cutive Mono.
 * Satori cannot read the woff2 files next/font ships, so the face is
 * vendored as a TTF.
 */
export default async function OpenGraphImage() {
  const [banner, cutive] = await Promise.all([
    readFile(join(process.cwd(), "public/obsidura-banner-white.png")),
    readFile(join(process.cwd(), "app/_og/cutive-mono.ttf")),
  ]);
  const bannerSrc = `data:image/png;base64,${banner.toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#000000",
        }}
      >
        { }
        <img src={bannerSrc} alt="" width={900} height={202} />
        <div
          style={{
            fontFamily: "Cutive Mono",
            fontSize: 24,
            color: "#9c9c9c",
            letterSpacing: 5,
            marginTop: 44,
            display: "flex",
          }}
        >
          A CLOUD FOR SMALL SOFTWARE
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [{ name: "Cutive Mono", data: cutive, weight: 400 }],
    }
  );
}
