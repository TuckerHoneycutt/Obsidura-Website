// Server-side verification of a Cloudflare Turnstile token.
// https://developers.cloudflare.com/turnstile/get-started/server-side-validation/

const SITEVERIFY_URL =
  "https://challenges.cloudflare.com/turnstile/v0/siteverify";

// The widget renders with action "contact"; a token minted for any other
// action (or another site) is rejected.
export const TURNSTILE_ACTION = "contact";

const ALLOWED_HOSTNAMES = new Set(["obsidura.com", "www.obsidura.com"]);

// Cloudflare's published test secrets. Tokens they validate carry dummy
// hostname/action values, so those checks are skipped for them.
const TEST_SECRET_PREFIXES = ["1x0000", "2x0000", "3x0000"];

export type TurnstileResult = "ok" | "failed" | "unavailable";

type SiteverifyResponse = {
  success: boolean;
  hostname?: string;
  action?: string;
  "error-codes"?: string[];
};

export async function verifyTurnstile(
  token: string,
  secret: string | undefined,
  remoteIp?: string
): Promise<TurnstileResult> {
  if (!secret) {
    // Loud in production so the check can't quietly ship disabled.
    console.error("TURNSTILE_SECRET_KEY is not set; skipping verification");
    return "unavailable";
  }

  if (!token || token.length > 2048) {
    return "failed";
  }

  const body = new URLSearchParams({ secret, response: token });
  if (remoteIp) body.set("remoteip", remoteIp);

  let data: SiteverifyResponse;
  try {
    const response = await fetch(SITEVERIFY_URL, {
      method: "POST",
      body,
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      console.error("Turnstile siteverify HTTP", response.status);
      return "unavailable";
    }
    data = (await response.json()) as SiteverifyResponse;
  } catch (err) {
    console.error("Turnstile siteverify unreachable:", err);
    return "unavailable";
  }

  if (!data.success) {
    return "failed";
  }

  const isTestSecret = TEST_SECRET_PREFIXES.some((p) => secret.startsWith(p));
  if (!isTestSecret) {
    if (!data.hostname || !ALLOWED_HOSTNAMES.has(data.hostname)) {
      console.warn("Turnstile hostname mismatch:", data.hostname);
      return "failed";
    }
    if (data.action !== TURNSTILE_ACTION) {
      console.warn("Turnstile action mismatch:", data.action);
      return "failed";
    }
  }

  return "ok";
}
