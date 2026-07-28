import {
  handleContactSubmission,
  type ContactState,
} from "../../lib/contact";

interface Env {
  RESEND_API_KEY?: string;
  CONTACT_FROM_EMAIL?: string;
  CONTACT_TO_EMAIL?: string;
}

type PagesFunction<E = unknown> = (context: {
  request: Request;
  env: E;
}) => Response | Promise<Response>;

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    const state: ContactState = {
      ok: false,
      message: "Invalid request body.",
    };
    return Response.json(state, { status: 400 });
  }

  const state = await handleContactSubmission(body, env);
  const status = state.ok ? 200 : state.fieldErrors ? 422 : 500;

  return Response.json(state, { status });
};
