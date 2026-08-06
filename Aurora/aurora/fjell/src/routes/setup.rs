use axum::{
    extract::Path,
    response::{Html, Redirect},
    routing::{get, post},
    Form,
};
use serde::Deserialize;

use crate::routes::hub::esc;

#[derive(Deserialize)]
pub struct SetupForm {
    pub api_key: String,
    pub ssh_key: Option<String>,
}

pub async fn setup_form(Path(username): Path<String>) -> Html<String> {
    // `username` is a URL path segment: whatever the caller typed, never a
    // roster lookup -- and this route answers 200 to an unauthenticated
    // request, on the same origin as Forgejo. Unescaped it was reflected XSS
    // into a title, a heading and an attribute at once; injected script there
    // can drive Forgejo as whoever followed the link. Escape ONCE, here, so
    // every interpolation below is covered by construction.
    let username = esc(&username);
    let html = format!(
        r#"<!DOCTYPE html>
<html><head><title>Setup — {username}</title></head>
<body style="font-family:system-ui;max-width:500px;margin:80px auto">
<h1>Setup: {username}</h1>
<form method="POST" action="/agent/{username}/setup">
  <p><label>OpenRouter API Key:<br>
    <input type="password" name="api_key" required style="width:100%;padding:8px">
  </label></p>
  <p><label>SSH Public Key (optional):<br>
    <textarea name="ssh_key" rows="4" style="width:100%;padding:8px"
      placeholder="ssh-ed25519 AAAA... your@laptop"></textarea>
  </label></p>
  <p><button type="submit" style="padding:10px 20px">Save</button></p>
</form>
<p><small>These values overwrite any previous submission. You can return to this page anytime to update.</small></p>
</body></html>"#,
        username = username
    );
    Html(html)
}

pub async fn setup_submit(
    Path(username): Path<String>,
    Form(form): Form<SetupForm>,
) -> Redirect {
    let container = format!("hermes-{}", username);

    // Write API key to .env (delete old, append new)
    let env_cmd = format!(
        "sed -i '/^OPENROUTER_API_KEY=/d' /opt/data/.env; echo 'OPENROUTER_API_KEY={}' >> /opt/data/.env",
        form.api_key
    );
    let _ = std::process::Command::new("docker")
        .args(["exec", &container, "sh", "-c", &env_cmd])
        .output();

    // Write SSH key to authorized_keys if provided
    if let Some(ssh_key) = form.ssh_key {
        let ssh_key = ssh_key.trim();
        if !ssh_key.is_empty() {
            let auth_path = std::env::var("AUTHORIZED_KEYS_PATH")
                .unwrap_or_else(|_| "/app/authorized_keys".to_string());

            // Remove old entry for this user
            if let Ok(content) = std::fs::read_to_string(&auth_path) {
                let marker = format!("hermes-{}", username);
                let kept: String = content
                    .lines()
                    .filter(|line| !line.contains(&marker))
                    .map(|line| format!("{}\n", line))
                    .collect();
                let _ = std::fs::write(&auth_path, kept);
            }

            // Append new entry
            let entry = format!(
                r#"command="docker exec -it hermes-{} bash",no-port-forwarding,no-X11-forwarding {}"#,
                username, ssh_key
            );
            if let Ok(mut file) = std::fs::OpenOptions::new().append(true).open(&auth_path) {
                use std::io::Write;
                let _ = file.write_all(format!("{}\n", entry).as_bytes());
            }
        }
    }

    Redirect::to(&format!("/agent/{}/", username))
}

pub fn router() -> axum::Router {
    axum::Router::new()
        // axum 0.8 replaced the `:param` capture syntax with `{param}`.
        // Using `:username` here panics at startup:
        //   "Path segments must not start with `:`"
        .route("/agent/{username}/setup", get(setup_form).post(setup_submit))
}

#[cfg(test)]
mod tests {
    use super::*;

    async fn form_for(username: &str) -> String {
        let Html(page) = setup_form(Path(username.to_string())).await;
        page
    }

    #[tokio::test]
    async fn the_path_segment_cannot_inject_markup() {
        let page = form_for("<img src=x onerror=alert(1)>").await;
        assert!(
            !page.contains("<img src=x"),
            "reflected XSS on an unauthenticated route sharing Forgejo's \
             origin:\n{page}"
        );
        assert!(page.contains("&lt;img src=x"), "{page}");
    }

    #[tokio::test]
    async fn the_path_segment_cannot_break_out_of_the_form_action() {
        // The attribute sink is the nastier of the two: it needs no angle
        // bracket, so a filter that only strips `<` would miss it.
        let page = form_for(r#"a" onmouseover="alert(1)"#).await;
        assert!(
            !page.contains(r#"" onmouseover"#),
            "attribute breakout in the form action:\n{page}"
        );
        assert!(page.contains("&quot;"), "{page}");
    }

    #[tokio::test]
    async fn an_ordinary_username_still_renders_readably() {
        let page = form_for("cumshit42069").await;
        assert!(page.contains("<h1>Setup: cumshit42069</h1>"), "{page}");
        assert!(
            page.contains(r#"action="/agent/cumshit42069/setup""#),
            "{page}"
        );
    }
}
