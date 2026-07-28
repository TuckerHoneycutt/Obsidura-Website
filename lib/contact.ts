export type ContactState = {
  ok: boolean;
  message: string;
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
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function parseContactInput(body: unknown): ContactInput {
  if (!body || typeof body !== "object") {
    return { name: "", email: "", message: "" };
  }

  const record = body as Record<string, unknown>;
  return {
    name: str(record.name),
    email: str(record.email),
    company: str(record.company),
    message: str(record.message),
    company_url: str(record.company_url),
  };
}

export function validateContactInput(input: ContactInput): ContactState {
  const fieldErrors: ContactState["fieldErrors"] = {};
  if (!input.name || input.name.length < 2) {
    fieldErrors.name = "Please enter your name.";
  }
  if (!input.email || !EMAIL_RE.test(input.email)) {
    fieldErrors.email = "Please enter a valid email.";
  }
  if (!input.message || input.message.length < 10) {
    fieldErrors.message = "Please include a short message.";
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

    return {
      ok: true,
      message: "Message sent. We will be in touch shortly.",
    };
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
  }
): Promise<ContactState> {
  const input = parseContactInput(body);

  if (input.company_url) {
    return { ok: true, message: "Message sent. We will be in touch shortly." };
  }

  const validation = validateContactInput(input);
  if (!validation.ok || validation.fieldErrors) {
    return validation;
  }

  return sendContactEmail(input, env);
}
