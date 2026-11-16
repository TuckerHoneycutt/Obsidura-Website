"use client";

import { useEffect, useRef, type Ref } from "react";
import { type MotionValue } from "motion/react";
import { FramePanel } from "@/components/ui/frame-panel";

/**
 * The team film, mounted as a printed plate - the hero's third scene.
 *
 * It sits on the hero's pinned stage the whole time, so being on screen
 * isn't enough to mean being seen: it plays only while its scene is shown
 * (`shown` past half) and at least half of it is in the viewport, and
 * pauses otherwise, picking up where it left off on the way back. The film
 * has no audio track, but it is muted anyway so browsers allow the
 * autoplay. If the reader pauses it themselves, scrolling won't start it
 * again; pressing play hands it back to the scroll. Readers who ask for
 * reduced motion get the poster and the controls, and nothing starts on
 * its own.
 *
 * The plate is as wide as the stage allows: never wider than 64rem, and
 * never so wide that its 16:9 height overflows the screen under the nav.
 */
export function Film({
  shown,
  ref,
}: {
  shown: MotionValue<number>;
  ref?: Ref<HTMLDivElement>;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let onScreen = false;
    let heldByReader = false;
    let pausingForScroll = false;

    const sync = () => {
      const wanted = onScreen && shown.get() > 0.5;
      if (wanted) {
        if (!heldByReader && video.paused) video.play().catch(() => {});
      } else if (!video.paused) {
        pausingForScroll = true;
        video.pause();
      }
    };

    const onPause = () => {
      if (pausingForScroll) pausingForScroll = false;
      else heldByReader = true;
    };
    const onPlay = () => {
      heldByReader = false;
    };
    video.addEventListener("pause", onPause);
    video.addEventListener("play", onPlay);

    const observer = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        sync();
      },
      { threshold: 0.5 }
    );
    observer.observe(video);
    const unsubscribe = shown.on("change", sync);

    return () => {
      observer.disconnect();
      unsubscribe();
      video.removeEventListener("pause", onPause);
      video.removeEventListener("play", onPlay);
    };
  }, [shown]);

  return (
    <div
      ref={ref}
      className="w-full max-w-5xl"
      style={{
        maxWidth:
          "min(64rem, calc((100svh - var(--nav-h, 4rem) - 4rem) * 16 / 9))",
      }}
    >
      <FramePanel interactive={false} className="bg-paper-warm/40 p-2 sm:p-3">
        <video
          ref={videoRef}
          className="block aspect-video w-full bg-paper"
          controls
          muted
          playsInline
          preload="metadata"
          poster="/pantheon-team-film-poster.jpg"
          aria-label="Obsidura team film"
        >
          <source src="/pantheon-team-film.mp4" type="video/mp4" />
          Your browser does not support embedded video.{" "}
          <a href="/pantheon-team-film.mp4">Download the film</a>.
        </video>
      </FramePanel>
    </div>
  );
}
