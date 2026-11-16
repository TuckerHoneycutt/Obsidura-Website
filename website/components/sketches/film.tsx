"use client";

import {
  createContext,
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { FramePanel } from "@/components/ui/frame-panel";
import { CHAPTERS } from "@/lib/home-content";
import { cn } from "@/lib/utils";

type FilmState = {
  videoRef: RefObject<HTMLVideoElement | null>;
  time: number;
  chapter: number;
  seek: (at: number) => void;
};

const FilmContext = createContext<FilmState | null>(null);

export function useFilm() {
  const film = use(FilmContext);
  if (!film) throw new Error("useFilm needs a <FilmProvider>");
  return film;
}

const chapterAt = (t: number) =>
  CHAPTERS.findLastIndex((c) => c.at <= t + 0.25);

/**
 * Owns the film's playhead for a sketch: which chapter is playing, and a
 * seek that jumps to a chapter and plays from there.
 */
export function FilmProvider({ children }: { children: ReactNode }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTime = () => setTime(video.currentTime);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("seeked", onTime);
    return () => {
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("seeked", onTime);
    };
  }, []);

  const seek = useCallback((at: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = at;
    setTime(at);
    video.play().catch(() => {});
  }, []);

  return (
    <FilmContext value={{ videoRef, time, chapter: chapterAt(time), seek }}>
      {children}
    </FilmContext>
  );
}

/**
 * The film on its plate. Plays once half of it is on screen and pauses
 * when it leaves; a reader's own pause holds until they press play.
 * Reduced motion: nothing starts on its own.
 */
export function FilmPlate({ className }: { className?: string }) {
  const { videoRef } = useFilm();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let held = false;
    let pausingForScroll = false;
    const onPause = () => {
      if (pausingForScroll) pausingForScroll = false;
      else held = true;
    };
    const onPlay = () => {
      held = false;
    };
    video.addEventListener("pause", onPause);
    video.addEventListener("play", onPlay);

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          if (!held && video.paused) video.play().catch(() => {});
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
  }, [videoRef]);

  return (
    <FramePanel
      interactive={false}
      className={cn("bg-paper-warm/40 p-2 sm:p-3", className)}
    >
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
  );
}
