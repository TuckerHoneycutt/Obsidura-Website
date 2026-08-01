import { handleContactSubmission } from "@/lib/contact";

export async function POST(request: Request) {
  let body: unknown;

  try {
    // The form submits JSON via fetch; accept a plain form post too so a
    // no-JavaScript submission (the form's native action) still works.
    if (request.headers.get("content-type")?.includes("application/json")) {
      body = await request.json();
    } else {
      body = Object.fromEntries(await request.formData());
    }
  } catch {
    return Response.json(
      { ok: false, message: "Invalid request body." },
      { status: 400 }
    );
  }

  const state = await handleContactSubmission(body, {
    RESEND_API_KEY: process.env.RESEND_API_KEY,
    CONTACT_FROM_EMAIL: process.env.CONTACT_FROM_EMAIL,
    CONTACT_TO_EMAIL: process.env.CONTACT_TO_EMAIL,
  });
  const status = state.ok ? 200 : state.fieldErrors ? 422 : 500;

  return Response.json(state, { status });
}
