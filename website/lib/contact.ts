import { verifyTurnstile } from "@/lib/turnstile";

export type ContactState = {
  ok: boolean;
  message: string;
  // Lets the route pick a status without parsing messages.
  code?: "verification";
  fieldErrors?: {
    name?: string;
    email?: string;
    message?: string;
  };
};

export type ContactInput = {
  name: string;
  email: string;
  company?: string;
  message: string;
  company_url?: string;
  turnstileToken?: string;
  // Milliseconds between the form mounting and being submitted.
  elapsedMs?: number;
};

const MAX = { name: 100, email: 254, company: 150, message: 5000 } as const;

// Anything faster than this was not typed by a person. Unsigned and
// forgeable, so it only filters the laziest bots - Turnstile does the rest.
const MIN_ELAPSED_MS = 3000;

// One plain address: no lists (, ;), display names (< > "), or whitespace,
// since the value goes straight into the reply_to header.
const EMAIL_RE = /^[^\s@,;<>"()[\]\\]+@[^\s@,;<>"()[\]\\]+\.[^\s@,;<>"()[\]\\]+$/;

const SENT: ContactState = {
  ok: true,
  message: "Message sent. We will be in touch shortly.",
};

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

// Single-line fields feed the subject and reply_to headers: no control
// characters at all, CR/LF included.
function line(value: unknown): string {
  return str(value)
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s{2,}/g, " ");
}

// The message body keeps newlines and tabs but drops other control bytes.
function multiline(value: unknown): string {
  return str(value)
    .replace(/\r\n?/g, "\n")
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "");
}

export function parseContactInput(body: unknown): ContactInput {
  if (!body || typeof body !== "object") {
    return { name: "", email: "", message: "" };
  }

  const record = body as Record<string, unknown>;
  const elapsed = Number(record.elapsed_ms);
  return {
    name: line(record.name),
    email: line(record.email),
    company: line(record.company),
    message: multiline(record.message),
    company_url: str(record.company_url),
    turnstileToken: str(record.turnstileToken),
    elapsedMs: Number.isFinite(elapsed) ? elapsed : undefined,
  };
}

export function validateContactInput(input: ContactInput): ContactState {
  const fieldErrors: ContactState["fieldErrors"] = {};
  if (!input.name || input.name.length < 2) {
    fieldErrors.name = "Please enter your name.";
  } else if (input.name.length > MAX.name) {
    fieldErrors.name = `Please keep your name under ${MAX.name} characters.`;
  }
  if (
    !input.email ||
    input.email.length > MAX.email ||
    !EMAIL_RE.test(input.email)
  ) {
    fieldErrors.email = "Please enter a valid email.";
  }
  if (!input.message || input.message.length < 10) {
    fieldErrors.message = "Please include a short message.";
  } else if (input.message.length > MAX.message) {
    fieldErrors.message = `Please keep your message under ${MAX.message} characters.`;
  }
  if (input.company && input.company.length > MAX.company) {
    // No dedicated error slot for company; it is optional, so trim it.
    input.company = input.company.slice(0, MAX.company);
  }
  if (Object.keys(fieldErrors).length > 0) {
    return {
      ok: false,
      message: "Check the highlighted fields and try again.",
      fieldErrors,
    };
  }

  return { ok: true, message: "" };
}

export async function sendContactEmail(
  input: ContactInput,
  env: {
    RESEND_API_KEY?: string;
    CONTACT_FROM_EMAIL?: string;
    CONTACT_TO_EMAIL?: string;
  }
): Promise<ContactState> {
  const apiKey = env.RESEND_API_KEY;
  const from =
    env.CONTACT_FROM_EMAIL ?? "Obsidura <onboarding@resend.dev>";
  const to = env.CONTACT_TO_EMAIL ?? "contact@obsidura.com";

  if (!apiKey) {
    console.error("RESEND_API_KEY is not set");
    return {
      ok: false,
      message: "Email is not configured yet. Please try again later.",
    };
  }

  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [to],
        reply_to: input.email,
        subject: `Contact from ${input.name}${
          input.company ? ` (${input.company})` : ""
        }`,
        text: [
          `Name: ${input.name}`,
          `Email: ${input.email}`,
          input.company ? `Company: ${input.company}` : null,
          "",
          input.message,
        ]
          .filter((line) => line !== null)
          .join("\n"),
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("Resend error:", error);
      return {
        ok: false,
        message: "Could not send your message. Please try again shortly.",
      };
    }

    return SENT;
  } catch (err) {
    console.error("Contact send failed:", err);
    return {
      ok: false,
      message: "Could not send your message. Please try again shortly.",
    };
  }
}

export async function handleContactSubmission(
  body: unknown,
  env: {
    RESEND_API_KEY?: string;
    CONTACT_FROM_EMAIL?: string;
    CONTACT_TO_EMAIL?: string;
    TURNSTILE_SECRET_KEY?: string;
  },
  meta: { ip?: string } = {}
): Promise<ContactState> {
  const input = parseContactInput(body);

  // Honeypot filled or submitted inhumanly fast: pretend it worked so the
  // bot has nothing to learn from, and send nothing.
  if (
    input.company_url ||
    input.elapsedMs === undefined ||
    input.elapsedMs < MIN_ELAPSED_MS
  ) {
    return SENT;
  }

  const validation = validateContactInput(input);
  if (!validation.ok || validation.fieldErrors) {
    return validation;
  }

  // After validation, so a typo doesn't burn the single-use token.
  const verification = await verifyTurnstile(
    input.turnstileToken ?? "",
    env.TURNSTILE_SECRET_KEY,
    meta.ip
  );
  if (verification === "failed") {
    return {
      ok: false,
      code: "verification",
      message:
        "We couldn't verify this submission. Please try again, or email contact@obsidura.com.",
    };
  }
  // "unavailable" (Cloudflare unreachable or secret unset) fails open: a lost
  // lead costs more than a rare spam message, and the other checks still ran.

  return sendContactEmail(input, env);
}
