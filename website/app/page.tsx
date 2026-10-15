import { Hero } from "@/components/hero";

/**
 * A door, and only a door: the claim, the paragraph that decodes it, and
 * one way in. Everything else has retired from the public site; anyone
 * who wants the depth asks for it through Contact.
 */
export default function Home() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <Hero />
    </main>
  );
}
