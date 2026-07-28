"use server";

import { Resend } from "resend";

export type ContactState = {
  ok: boolean;
  message: string;
  fieldErrors?: {
    name?: string;
    email?: string;
    message?: string;
  };
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function str(formData: FormData, key: string): string {
  const v = formData.get(key);
  return typeof v === "string" ? v.trim() : "";
}

export async function sendContact(
  _prev: ContactState,
  formData: FormData
): Promise<ContactState> {
  // Honeypot — bots fill this; real users never see it.
  if (str(formData, "company_url")) {
    return { ok: true, message: "Message sent. We will be in touch shortly." };
  }

  const name = str(formData, "name");
  const email = str(formData, "email");
  const company = str(formData, "company");
  const message = str(formData, "message");

  const fieldErrors: ContactState["fieldErrors"] = {};
  if (!name || name.length < 2) {
    fieldErrors.name = "Please enter your name.";
  }
  if (!email || !EMAIL_RE.test(email)) {
    fieldErrors.email = "Please enter a valid email.";
  }
  if (!message || message.length < 10) {
    fieldErrors.message = "Please include a short message.";
  }
  if (Object.keys(fieldErrors).length > 0) {
    return {
      ok: false,
      message: "Check the highlighted fields and try again.",
      fieldErrors,
    };
  }

  const apiKey = process.env.RESEND_API_KEY;
  const from =
    process.env.CONTACT_FROM_EMAIL ?? "Obsidura <onboarding@resend.dev>";
  const to = process.env.CONTACT_TO_EMAIL ?? "contact@obsidura.com";

  if (!apiKey) {
    console.error("RESEND_API_KEY is not set");
    return {
      ok: false,
      message: "Email is not configured yet. Please try again later.",
    };
  }

  try {
    const resend = new Resend(apiKey);
    const { error } = await resend.emails.send({
      from,
      to: [to],
      replyTo: email,
      subject: `Contact from ${name}${company ? ` (${company})` : ""}`,
      text: [
        `Name: ${name}`,
        `Email: ${email}`,
        company ? `Company: ${company}` : null,
        "",
        message,
      ]
        .filter((line) => line !== null)
        .join("\n"),
    });

    if (error) {
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
