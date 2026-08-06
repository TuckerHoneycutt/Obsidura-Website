//! Who is asking?
//!
//! fjell has no session of its own. The only identity signal a browser on this
//! stack will hand it is Forgejo's session cookie, and that cookie is
//! `Path=/git` (measured 2026-07-31: `session=…; Path=/git; HttpOnly`). So the
//! hub is mounted under `/git/` by Caddy purely so the cookie arrives, and we
//! ask Forgejo — the actual identity provider — whose it is.
//!
//! **Forgejo's REST API does not accept session cookies**, which is why the
//! profile settings page is the only thing asked. Measured against a branch
//! stack running Forgejo 15.0.5 with a session the web UI simultaneously
//! accepted:
//!
//! ```text
//! GET /git/api/v1/user   Cookie: session=…  ->  401 {"message":"token is required"}
//! GET /git/user/settings Cookie: session=…  ->  200 (signed in as cumshit42069)
//! ```
//!
//! We never trust anything the caller says about themselves: the username comes
//! from Forgejo's answer to a cookie the browser sent. And the hub only
//! *routes* — `/agent/<user>/*` is still gated by agent-authz, so a caller who
//! edits the link gets the "not your agent" page rather than someone else's
//! agent.

use std::sync::OnceLock;

use reqwest::StatusCode;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Caller {
    /// No usable session — show a sign-in route.
    Anonymous,
    /// Forgejo confirmed this login.
    Identified(String),
    /// Forgejo could not be asked, or answered something we cannot read.
    /// Distinct from `Anonymous` on purpose: telling a signed-in developer to
    /// "sign in" because the backend was down is a lie, and it loops them.
    Unavailable(String),
}

/// The username out of Forgejo's profile settings form.
///
/// The page carries exactly one `<input name="name" …>` and it is the
/// account's own username field (measured on Forgejo 15.0.5):
///
/// ```text
/// <input name="name" value="cumshit42069" data-name="cumshit42069" autofocus required  maxlength="40">
/// ```
///
/// Attribute order is not assumed — a template that reorders them is a
/// cosmetic change and must not silently sign everybody out.
fn username_from_settings_page(html: &str) -> Option<String> {
    for tag in html.split("<input").skip(1) {
        let tag = &tag[..tag.find('>').unwrap_or(tag.len())];
        if !tag.contains("name=\"name\"") {
            continue;
        }
        // `continue`, not `?`: a `?` here returns from the FUNCTION, so one
        // matching tag with no `value=` aborted the whole scan and signed a
        // logged-in developer out.
        let Some(rest) = tag.split("value=\"").nth(1) else { continue };
        let Some(end) = rest.find('"') else { continue };
        if end > 0 {
            return Some(rest[..end].to_string());
        }
    }
    None
}

/// One client for the process. Built per `resolve()` it discarded its
/// connection pool on every hub page load.
fn client() -> &'static reqwest::Client {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            // Do NOT follow redirects. Forgejo answers an unauthenticated
            // /user/settings with `303 -> /user/login`, and following it lands on
            // a 200 login page — which is indistinguishable from a signed-in page
            // that simply stopped carrying the field we look for. The redirect
            // itself is the cleanest "not signed in" signal there is.
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .expect("a client whose only setting is a redirect policy")
    })
}

/// Resolve the caller by replaying their cookies to Forgejo's profile page.
///
/// `base` is Forgejo's *internal* origin (compose service DNS), never a
/// user-supplied value — the caller's cookies are forwarded verbatim and must
/// only ever reach Forgejo.
pub async fn resolve(cookie: Option<&str>, base: &str) -> Caller {
    let cookie = match cookie {
        Some(c) if !c.trim().is_empty() => c,
        _ => return Caller::Anonymous,
    };
    let base = base.trim_end_matches('/');

    let response = match client()
        .get(format!("{base}/user/settings"))
        .header("Cookie", cookie)
        .send()
        .await
    {
        Ok(r) => r,
        Err(_) => return Caller::Unavailable("Forgejo did not answer".to_string()),
    };
    let status = response.status();
    if status.is_redirection()
        || status == StatusCode::UNAUTHORIZED
        || status == StatusCode::FORBIDDEN
    {
        return Caller::Anonymous;
    }
    if !status.is_success() {
        return Caller::Unavailable(format!("Forgejo answered {}", status.as_u16()));
    }
    match response.text().await {
        Ok(body) => match username_from_settings_page(&body) {
            Some(name) => Caller::Identified(name),
            // Signed in, but the page no longer carries the field. Reporting
            // "signed out" here would send a signed-in developer to a login
            // that returns them to the same page.
            None => Caller::Unavailable(
                "Forgejo's profile page no longer names the signed-in account".to_string(),
            ),
        },
        Err(_) => Caller::Unavailable("Forgejo's answer could not be read".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    /// Verbatim from Forgejo 15.0.5, captured 2026-07-31 in the `hub` branch
    /// stack. A hand-written approximation would prove only that the parser
    /// matches the author's memory of the template.
    const REAL_SETTINGS_INPUT: &str = concat!(
        r#"<form class="ui form" action="/git/user/settings" method="post">"#,
        r#"<div class="field"><label for="username">Username</label>"#,
        r#"<input name="name" value="cumshit42069" data-name="cumshit42069" autofocus required  maxlength="40">"#,
        r#"</div></form>"#,
    );

    /// An HTTP stub answering everything with one response, recording what it
    /// was asked. The `Location:` header is always present so a 3xx is a real
    /// redirect.
    async fn stub(status: u16, body: &'static str) -> (String, Arc<Mutex<Vec<String>>>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let seen = Arc::new(Mutex::new(Vec::new()));
        let log = Arc::clone(&seen);
        tokio::spawn(async move {
            loop {
                let Ok((mut sock, _)) = listener.accept().await else { return };
                let log = Arc::clone(&log);
                tokio::spawn(async move {
                    let mut buf = vec![0u8; 16384];
                    let n = sock.read(&mut buf).await.unwrap_or(0);
                    log.lock()
                        .unwrap()
                        .push(String::from_utf8_lossy(&buf[..n]).to_string());
                    let response = format!(
                        "HTTP/1.1 {status} X\r\nContent-Type: text/html\r\nLocation: /user/login\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                        body.len()
                    );
                    let _ = sock.write_all(response.as_bytes()).await;
                    let _ = sock.flush().await;
                });
            }
        });
        (format!("http://{addr}"), seen)
    }

    #[tokio::test]
    async fn no_cookie_is_anonymous_without_asking_forgejo() {
        // Nothing listens on port 1: if we asked, this would be Unavailable.
        assert_eq!(resolve(None, "http://127.0.0.1:1").await, Caller::Anonymous);
        assert_eq!(resolve(Some("   "), "http://127.0.0.1:1").await, Caller::Anonymous);
    }

    #[tokio::test]
    async fn the_callers_cookie_identifies_them_off_the_profile_page() {
        let (base, seen) = stub(200, REAL_SETTINGS_INPUT).await;
        assert_eq!(
            resolve(Some("session=SENTINEL9"), &base).await,
            Caller::Identified("cumshit42069".into())
        );
        let asked: Vec<String> = seen.lock().unwrap().clone();
        assert_eq!(asked.len(), 1, "{asked:?}");
        assert!(asked[0].starts_with("GET /user/settings "), "{}", asked[0]);
        assert!(
            asked[0].contains("session=SENTINEL9"),
            "Forgejo was asked without the caller's cookie, so it can only \
             ever answer 'anonymous':\n{}",
            asked[0]
        );
    }

    #[tokio::test]
    async fn a_redirect_to_the_login_page_is_anonymous() {
        // Forgejo answers an unauthenticated /user/settings with 303. If the
        // client followed it, the login page's 200 would be read as a
        // signed-in page with a missing field — Unavailable, not Anonymous.
        let (base, _) = stub(303, "").await;
        assert_eq!(resolve(Some("session=stale"), &base).await, Caller::Anonymous);
    }

    #[tokio::test]
    async fn a_signed_in_page_that_lost_the_field_is_not_reported_as_signed_out() {
        let (base, _) = stub(200, "<html>no such input</html>").await;
        match resolve(Some("session=x"), &base).await {
            Caller::Unavailable(_) => {}
            other => panic!(
                "a Forgejo template change would sign every developer out and \
                 send them to a login that returns them here: {other:?}"
            ),
        }
    }

    #[tokio::test]
    async fn an_unreachable_forgejo_is_unavailable_not_anonymous() {
        match resolve(Some("session=x"), "http://127.0.0.1:1").await {
            Caller::Unavailable(_) => {}
            other => panic!("an outage must not read as signed-out: {other:?}"),
        }
    }

    #[tokio::test]
    async fn an_outage_is_unavailable_not_anonymous() {
        let (base, _) = stub(500, "").await;
        match resolve(Some("session=x"), &base).await {
            Caller::Unavailable(_) => {}
            other => panic!("a Forgejo outage must not read as signed-out: {other:?}"),
        }
    }

    #[test]
    fn the_username_is_read_out_of_the_real_forgejo_markup() {
        assert_eq!(
            username_from_settings_page(REAL_SETTINGS_INPUT).as_deref(),
            Some("cumshit42069")
        );
    }

    #[test]
    fn attribute_order_is_not_assumed() {
        let reordered = r#"<input value="bob" required name="name" maxlength="40">"#;
        assert_eq!(username_from_settings_page(reordered).as_deref(), Some("bob"));
    }

    #[test]
    fn a_different_input_is_not_mistaken_for_the_username() {
        // The login page carries name="user_name"; the settings page also has
        // inputs for the full name, e-mail and so on.
        let other = concat!(
            r#"<input name="user_name" value="whoever">"#,
            r#"<input name="full_name" value="Someone Else">"#,
        );
        assert_eq!(username_from_settings_page(other), None);
    }

    #[test]
    fn a_matching_tag_without_a_value_does_not_abort_the_scan() {
        // These used to return None from the whole function, signing a
        // logged-in developer out over one unexpected tag.
        for markup in [
            concat!(r#"<input name="name" required>"#, r#"<input name="name" value="bob">"#),
            concat!(r#"<input name="name" value="">"#, r#"<input name="name" value="bob">"#),
        ] {
            assert_eq!(username_from_settings_page(markup).as_deref(), Some("bob"));
        }
    }
}
