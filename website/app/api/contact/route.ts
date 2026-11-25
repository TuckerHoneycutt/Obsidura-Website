import { handleContactSubmission } from "@/lib/contact";

// Generous for a name, email, company and a 5,000-character message.
const MAX_BODY_BYTES = 16 * 1024;

// Production only accepts the real domain. Posting straight to the
// *.netlify.app hostname would skip Cloudflare's rate limiting entirely.
// Switched on by CONTACT_ENFORCE_HOST=true, set only in Netlify's production
// context (CONTEXT is a build-time variable and not guaranteed at function
// runtime). Deploy previews, branch deploys and local dev stay open.
const ALLOWED_HOSTS = new Set(["obsidura.com", "www.obsidura.com"]);
const enforceHost =
  process.env.CONTACT_ENFORCE_HOST === "true" ||
  process.env.CONTEXT === "production";

function reject(message: string, status: number) {
  return Response.json({ ok: false, message }, { status });
}

function clientIp(request: Request): string | undefined {
  const h = request.headers;
  return (
    h.get("cf-connecting-ip") ??
    h.get("x-nf-client-connection-ip") ??
    h.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    undefined
  );
}

export async function POST(request: Request) {
  if (enforceHost) {
    const host = request.headers.get("host")?.split(":")[0].toLowerCase();
    if (!host || !ALLOWED_HOSTS.has(host)) {
      return reject("Forbidden.", 403);
    }
    const origin = request.headers.get("origin");
    if (origin) {
      let originHost = "";
      try {
        originHost = new URL(origin).hostname;
      } catch {}
      if (!ALLOWED_HOSTS.has(originHost)) {
        return reject("Forbidden.", 403);
      }
    }
  }

  // JavaScript only: the form needs Turnstile, which needs JavaScript.
  // Visitors without it are pointed at the email address instead.
  if (!request.headers.get("content-type")?.includes("application/json")) {
    return reject("Unsupported request.", 415);
  }

  const declaredLength = Number(request.headers.get("content-length"));
  if (declaredLength > MAX_BODY_BYTES) {
    return reject("Message too large.", 413);
  }

  let body: unknown;
  try {
    // Content-Length can be absent or wrong, so measure what actually arrived.
    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) {
      return reject("Message too large.", 413);
    }
    body = JSON.parse(raw);
  } catch {
    return reject("Invalid request body.", 400);
  }

  const state = await handleContactSubmission(
    body,
    {
      RESEND_API_KEY: process.env.RESEND_API_KEY,
      CONTACT_FROM_EMAIL: process.env.CONTACT_FROM_EMAIL,
      CONTACT_TO_EMAIL: process.env.CONTACT_TO_EMAIL,
      TURNSTILE_SECRET_KEY: process.env.TURNSTILE_SECRET_KEY,
    },
    { ip: clientIp(request) }
  );

  const status = state.ok
    ? 200
    : state.code === "verification"
      ? 403
      : state.fieldErrors
        ? 422
        : 500;

  return Response.json(state, { status });
}
