import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const dynamic = "force-static";

const size = { width: 1200, height: 630 };

/**
 * The id is the image's URL (/opengraph-image/<id>). Safari keeps link
 * previews by URL and never refetches one it has seen, so bump the id
 * whenever the artwork changes.
 */
export function generateImageMetadata() {
  return [
    {
      id: "v4",
      size,
      contentType: "image/png",
      alt: "Obsidura | Any Software. Anywhere.",
    },
  ];
}

/**
 * The brand lockup on the black paper, stacked rather than side by side:
 * iOS shows this image both as a wide card and as a centre-cropped square
 * bookmark thumbnail, and a stacked lockup reads whole in either. The mark
 * and wordmark are the footer banner's own artwork, split apart; the
 * tagline is a kicker in Cutive Mono. Satori cannot read the woff2 files
 * next/font ships, so the face is vendored as a TTF.
 */
export default async function OpenGraphImage() {
  const [mark, wordmark, cutive] = await Promise.all([
    readFile(join(process.cwd(), "public/obsidura-mark-white.png")),
    readFile(join(process.cwd(), "public/obsidura-wordmark-white.png")),
    readFile(join(process.cwd(), "app/_og/cutive-mono.ttf")),
  ]);
  const src = (png: Buffer) =>
    `data:image/png;base64,${png.toString("base64")}`;

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
        <img src={src(mark)} alt="" width={272} height={280} />
        { }
        <img
          src={src(wordmark)}
          alt=""
          width={500}
          height={67}
          style={{ marginTop: 40 }}
        />
        <div
          style={{
            fontFamily: "Cutive Mono",
            fontSize: 21,
            color: "#9c9c9c",
            letterSpacing: 4,
            marginTop: 30,
            display: "flex",
          }}
        >
          ANY SOFTWARE. ANYWHERE.
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [{ name: "Cutive Mono", data: cutive, weight: 400 }],
    }
  );
}
