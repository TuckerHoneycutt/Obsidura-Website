"use client";

import { useEffect, useRef } from "react";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";

/**
 * The team film, mounted as a printed plate under the hero's account.
 *
 * It plays once at least half of it is on screen and pauses when it scrolls
 * away, picking up where it left off on the way back. The film has no audio
 * track, but it is muted anyway so browsers allow the autoplay. If the
 * reader pauses it themselves, scrolling won't start it again; pressing
 * play hands it back to the scroll. Readers who ask for reduced motion get
 * the poster and the controls, and nothing starts on its own.
 */
export function Film() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let heldByReader = false;
    let pausingForScroll = false;

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
        if (entry.isIntersecting) {
          if (!heldByReader && video.paused) video.play().catch(() => {});
        } else if (!video.paused) {
          pausingForScroll = true;
          video.pause();
        }
      },
      { threshold: 0.5 }
    );
    observer.observe(video);

    return () => {
      observer.disconnect();
      video.removeEventListener("pause", onPause);
      video.removeEventListener("play", onPlay);
    };
  }, []);

  return (
    <section className="px-5 pb-20 md:pb-28">
      <Reveal className="mx-auto max-w-5xl">
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
      </Reveal>
    </section>
  );
}
