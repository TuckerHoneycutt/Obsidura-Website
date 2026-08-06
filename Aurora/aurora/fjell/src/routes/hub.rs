//! The hub — the stack's front door.
//!
//! Two fixed destinations (Forgejo, AFFiNE) and one that depends on who is
//! asking: the caller's OWN agent. See `identity.rs` for how "who is asking"
//! is established, and the design spec for why the hub is mounted under
//! `/git/` rather than at the site root.

use axum::extract::Request;
use axum::http::{header, StatusCode};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::get;

use crate::config::{forgejo_internal_url, load_agents, AgentEntry};
use crate::identity::{resolve, Caller};

const HUB_CSS: &str = include_str!("../../static/hub.css");
/// The illustrated plate behind the page. Vendored, not hotlinked, for the
/// same reason as the stylesheet: this host has no route off the tailnet.
const HUB_BG: &[u8] = include_bytes!("../../static/hub-bg.webp");
/// The plate's path, named once. It appears twice -- on the route below and
/// inside `hub.css` -- and those are otherwise unrelated string literals that
/// a rename would silently desynchronise, leaving a page with no background
/// and a green build. `the_stylesheet_asks_for_a_path_the_router_serves` ties
/// them together.
const BG_ROUTE: &str = "/hub-bg.webp";

/// FNV-1a over the plate, evaluated at compile time so the ETag costs nothing
/// per request and changes exactly when the bytes do.
const fn fnv1a(bytes: &[u8]) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    let mut i = 0;
    while i < bytes.len() {
        hash ^= bytes[i] as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
        i += 1;
    }
    hash
}
const HUB_BG_ETAG: u64 = fnv1a(HUB_BG);

/// The username is attacker-influenced input arriving over the network, and
/// the cost of being wrong about that is stored XSS on the stack's front door.
/// `&` FIRST, or it would re-escape the ampersands the later rules introduce.
pub(crate) fn esc(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// One row of the plate.
///
/// EVERY parameter is interpolated as raw HTML, and `href` lands inside a
/// double-quoted attribute. Callers escape; this function does not. Passing a
/// caller-supplied value as `name`, `blurb` or `href` without `esc` is stored
/// XSS on the stack's front door -- see `esc` above for why that matters here.
/// `mark` is the row's letter (A, B, Γ) and is never a link target.
fn door(href: Option<&str>, mark: &str, name: &str, blurb: &str) -> String {
    match href {
        Some(href) => format!(
            r#"<a class="door" href="{href}">
      <span class="mark">{mark}</span>
      <span class="text"><span class="name">{name}</span><span class="blurb">{blurb}</span></span>
      <span class="arrow" aria-hidden="true">&rarr;</span>
    </a>"#
        ),
        None => format!(
            r#"<div class="door door--off">
      <span class="mark">{mark}</span>
      <span class="text"><span class="name">{name}</span><span class="blurb">{blurb}</span></span>
      <span class="arrow"></span>
    </div>"#
        ),
    }
}

fn agent_door(caller: &Caller, agents: &[AgentEntry]) -> String {
    match caller {
        // The ROSTER's spelling wins over the caller's: Caddy's generated
        // routes are literal paths built from `developers.yaml`, so
        // `/agent/Alice/` is a 404 even when Forgejo calls you `Alice`.
        Caller::Identified(login) => match agents
            .iter()
            .find(|a| a.username.eq_ignore_ascii_case(login))
        {
            Some(entry) => door(
                Some(&format!("/agent/{}/", esc(&entry.username))),
                "&Gamma;",
                "Your agent",
                "Your own Hermes container. Nobody else can open it.",
            ),
            None => door(
                None,
                "&Gamma;",
                "No agent yet",
                "Ask an admin to add you to <code>developers.yaml</code>.",
            ),
        },
        Caller::Anonymous => door(
            Some("/git/user/login?redirect_to=%2Fgit%2F.hub%2F"),
            "&Gamma;",
            "Your agent",
            "Sign in to Forgejo and this becomes a door to your own agent.",
        ),
        Caller::Unavailable(reason) => door(
            None,
            "&Gamma;",
            "Your agent",
            &format!(
                "Could not confirm who you are &mdash; {}. Reload, or open \
                 Forgejo directly.",
                esc(reason)
            ),
        ),
    }
}

/// The plaque under the plate. It is the only place the caller's own name
/// appears, so every caller state has to have something to say here.
fn plaque(caller: &Caller) -> String {
    match caller {
        Caller::Identified(login) => format!("Signed in as {}", esc(login)),
        Caller::Anonymous => String::from("Not signed in"),
        Caller::Unavailable(reason) => format!("Identity unavailable &mdash; {}", esc(reason)),
    }
}

pub fn render_hub(caller: &Caller, agents: &[AgentEntry]) -> String {
    format!(
        r#"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aurora</title>
<link rel="stylesheet" href="hub.css">
</head>
<body>
<main>
  <header class="masthead">
    <h1>Aurora</h1>
    <div class="meander" aria-hidden="true"></div>
    <p class="tagline">create without limit</p>
  </header>
  <nav class="doors">
    {forgejo}
    {affine}
    {agent}
  </nav>
  <p class="plaque-row"><span class="plaque">{plaque}</span></p>
</main>
</body>
</html>
"#,
        forgejo = door(
            Some("/git/"),
            "A",
            "Forgejo",
            "Repositories, issues, and the account everything here signs in with.",
        ),
        affine = door(
            Some("/affine/"),
            "B",
            "AFFiNE",
            "The shared workspace &mdash; docs and whiteboards.",
        ),
        agent = agent_door(caller, agents),
        plaque = plaque(caller),
    )
}

async fn hub(request: Request) -> Html<String> {
    let cookie = request
        .headers()
        .get(header::COOKIE)
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());
    let caller = resolve(cookie.as_deref(), &forgejo_internal_url()).await;
    Html(render_hub(&caller, &load_agents()))
}

async fn css() -> Response {
    ([(header::CONTENT_TYPE, "text/css; charset=utf-8")], HUB_CSS).into_response()
}

async fn bg(request: Request) -> Response {
    // `max-age` on an unversioned filename with no validator was a trap: change
    // the plate and a caller keeps the old one until the age expires, with no
    // cache-buster short of renaming the file. `no-cache` means "revalidate",
    // not "do not store", so the steady state is a ~200-byte 304 rather than a
    // repeated 177 KB download.
    let etag = format!("\"{HUB_BG_ETAG:016x}\"");
    let known = request
        .headers()
        .get(header::IF_NONE_MATCH)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v.split(',').any(|candidate| candidate.trim() == etag));

    if known {
        return (
            StatusCode::NOT_MODIFIED,
            [
                (header::CACHE_CONTROL, "no-cache".to_string()),
                (header::ETAG, etag),
            ],
        )
            .into_response();
    }

    (
        [
            (header::CONTENT_TYPE, "image/webp".to_string()),
            (header::CACHE_CONTROL, "no-cache".to_string()),
            (header::ETAG, etag),
        ],
        HUB_BG,
    )
        .into_response()
}

pub fn router() -> axum::Router {
    axum::Router::new()
        .route("/", get(hub))
        .route("/hub.css", get(css))
        .route(BG_ROUTE, get(bg))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The doors only. Whole-page comparisons stopped proving anything about
    /// the doors the moment the plaque became a second caller-dependent term:
    /// a page-level `assert_ne!` passes on the plaque alone even if the agent
    /// door has been reduced to a constant.
    fn doors_of(page: &str) -> &str {
        let open = r#"<nav class="doors">"#;
        let start = page.find(open).expect("no doors block on the page");
        let end = page[start..].find("</nav>").expect("unterminated doors block") + start;
        &page[start..end]
    }

    fn roster(names: &[&str]) -> Vec<AgentEntry> {
        names
            .iter()
            .map(|n| AgentEntry {
                username: n.to_string(),
                display_name: n.to_string(),
            })
            .collect()
    }

    #[test]
    fn the_agent_link_is_the_callers_own_agent() {
        let agents = roster(&["alice", "bob", "carol"]);
        let page = render_hub(&Caller::Identified("bob".into()), &agents);

        assert!(
            page.contains(r#"href="/agent/bob/""#),
            "bob was not routed to his own agent:\n{page}"
        );
        // The whole point of the feature: nobody else's agent is on the page.
        for other in ["alice", "carol"] {
            assert!(
                !page.contains(&format!("/agent/{other}/")),
                "{other}'s agent leaked onto bob's hub:\n{page}"
            );
        }
    }

    #[test]
    fn each_developer_gets_a_different_page() {
        let agents = roster(&["alice", "bob"]);
        let a = render_hub(&Caller::Identified("alice".into()), &agents);
        let b = render_hub(&Caller::Identified("bob".into()), &agents);
        // On the DOORS, not the whole page. The plaque is a second
        // caller-dependent term, so a page-level `assert_ne!` passes on the
        // plaque alone even after the agent door is reduced to a constant --
        // which is the one thing this test exists to catch.
        assert_ne!(
            doors_of(&a),
            doors_of(&b),
            "the doors rendered identically for two different callers, so the \
             agent door is not discriminating by identity at all"
        );
    }

    #[test]
    fn an_unrostered_login_gets_no_agent_link() {
        let agents = roster(&["alice"]);
        let page = render_hub(&Caller::Identified("mallory".into()), &agents);
        assert!(
            !page.contains("/agent/"),
            "a caller with no agent was offered an agent link:\n{page}"
        );
        assert!(page.contains("No agent yet"), "{page}");
        assert!(
            page.contains("mallory"),
            "the page must say who it thinks you are:\n{page}"
        );
    }

    #[test]
    fn the_roster_spelling_wins_over_the_callers_spelling() {
        // Caddy's routes are literal paths generated from developers.yaml.
        let agents = roster(&["cumshit42069"]);
        let page = render_hub(&Caller::Identified("CumShit42069".into()), &agents);
        assert!(
            page.contains(r#"href="/agent/cumshit42069/""#),
            "linked to a path Caddy does not route:\n{page}"
        );
        assert!(!page.contains("/agent/CumShit42069/"), "{page}");
    }

    #[test]
    fn anonymous_gets_a_sign_in_route_and_no_agent_link() {
        let agents = roster(&["alice", "bob"]);
        let page = render_hub(&Caller::Anonymous, &agents);
        assert!(
            !page.contains("/agent/"),
            "an unauthenticated visitor was shown an agent link, which also \
             leaks the roster:\n{page}"
        );
        assert!(page.contains("/git/user/login"), "{page}");
    }

    #[test]
    fn unavailable_does_not_tell_a_signed_in_user_to_sign_in() {
        let agents = roster(&["alice"]);
        let page = render_hub(&Caller::Unavailable("Forgejo answered 502".into()), &agents);
        // On the DOORS, not the page: the plaque also names the reason, so a
        // page-level check would survive the blurb losing it entirely.
        assert!(
            doors_of(&page).contains("Forgejo answered 502"),
            "the outage reason never reached the agent door:\n{page}"
        );
        assert!(
            !page.contains("/git/user/login"),
            "an outage was reported as 'you are signed out', which loops the \
             user through a login that will appear to do nothing:\n{page}"
        );
    }

    #[test]
    fn the_two_fixed_doors_are_always_present() {
        for caller in [
            Caller::Anonymous,
            Caller::Identified("alice".into()),
            Caller::Unavailable("x".into()),
        ] {
            let page = render_hub(&caller, &roster(&["alice"]));
            assert!(page.contains(r#"href="/git/""#), "{caller:?}: {page}");
            assert!(page.contains(r#"href="/affine/""#), "{caller:?}: {page}");
        }
    }

    #[test]
    fn a_hostile_login_is_escaped() {
        let agents = roster(&["alice"]);
        let page = render_hub(
            &Caller::Identified("<script>alert(1)</script>".into()),
            &agents,
        );
        assert!(
            !page.contains("<script>alert(1)</script>"),
            "stored XSS on the front door:\n{page}"
        );
        assert!(page.contains("&lt;script&gt;"), "{page}");
    }

    #[test]
    fn an_empty_roster_never_produces_a_bare_agent_link() {
        let page = render_hub(&Caller::Identified("alice".into()), &[]);
        assert!(!page.contains("/agent/"), "{page}");
    }

    #[test]
    fn the_stylesheet_is_vendored_not_hotlinked() {
        let page = render_hub(&Caller::Anonymous, &roster(&["alice"]));
        assert!(page.contains(r#"href="hub.css""#), "{page}");
        for remote in ["http://", "https://", "//cdn", "unpkg", "jsdelivr"] {
            assert!(
                !page.contains(remote),
                "the hub reaches off-host for {remote}, which does not work on \
                 an air-gapped tailnet:\n{page}"
            );
        }
        // `url("https://…")` does not contain `url(http`. This file's house
        // style is quoted `url()` -- it acquired its first one with the plate
        // -- so the naive check had become unable to fire. Strip the quotes
        // first. The data URI survives: it reads `url(data:` either way, and
        // the `http://www.w3.org/2000/svg` inside it is an XML namespace name
        // that no browser ever fetches.
        let unquoted: String = HUB_CSS.chars().filter(|c| !matches!(c, '"' | '\'')).collect();
        for remote in ["@import", "url(http", "url(//"] {
            assert!(
                !unquoted.contains(remote),
                "hub.css pulls in a remote asset via {remote}"
            );
        }
        assert!(
            !page.contains("<script"),
            "the hub is server-rendered on purpose; a <script> tag means the \
             identity logic moved somewhere untested:\n{page}"
        );
    }

    #[test]
    fn the_stylesheet_asks_for_a_path_the_router_serves() {
        // Two unrelated string literals -- the route and the CSS `url()` --
        // that must agree. Renaming either alone ships a page with no plate
        // and a 404 in the console, and every other test stays green.
        let file = BG_ROUTE.trim_start_matches('/');
        assert!(
            HUB_CSS.contains(&format!(r#"url("{file}")"#)),
            "hub.css does not ask for {BG_ROUTE}, which is what the router serves"
        );
    }

    #[test]
    fn the_plate_is_a_real_webp_and_is_not_empty() {
        // include_bytes! of a truncated or wrong-format file builds cleanly and
        // fails only in the browser.
        assert!(HUB_BG.len() > 1024, "the plate is {} bytes", HUB_BG.len());
        assert_eq!(&HUB_BG[..4], b"RIFF", "the plate is not a RIFF container");
        assert_eq!(&HUB_BG[8..12], b"WEBP", "the plate is not a WEBP");
    }

    #[test]
    fn every_caller_state_says_who_it_thinks_you_are() {
        // The plaque is the only place the caller's name appears now, so each
        // state has to have something to say. Previously only the unrostered
        // Identified case was covered, which left the ordinary signed-in path
        // -- the common one -- asserting nothing.
        let agents = roster(&["alice"]);
        for (caller, expected) in [
            (Caller::Identified("alice".into()), "Signed in as alice"),
            (Caller::Identified("mallory".into()), "Signed in as mallory"),
            (Caller::Anonymous, "Not signed in"),
            (
                Caller::Unavailable("Forgejo answered 502".into()),
                "Identity unavailable",
            ),
        ] {
            let page = render_hub(&caller, &agents);
            let plaque = page
                .find(r#"<span class="plaque">"#)
                .map(|i| &page[i..])
                .unwrap_or_else(|| panic!("{caller:?}: no plaque on the page:\n{page}"));
            assert!(
                plaque.contains(expected),
                "{caller:?}: plaque does not say {expected:?}:\n{page}"
            );
        }
    }

    #[test]
    fn a_hostile_roster_name_cannot_break_out_of_the_href() {
        // The roster is admin-written, so this is not an exploit today -- but
        // the href is the one place a roster value lands in an attribute, and
        // dropping its `esc` was invisible to every other test in this file.
        let hostile = r#"a" onmouseover="alert(1)"#;
        let page = render_hub(&Caller::Identified(hostile.into()), &roster(&[hostile]));
        assert!(
            !doors_of(&page).contains(r#"" onmouseover"#),
            "the agent href broke out of its attribute:\n{page}"
        );
        assert!(doors_of(&page).contains("&quot;"), "{page}");
    }

    #[tokio::test]
    async fn the_router_actually_serves_both_assets() {
        use axum::body::Body;
        use axum::http::Request as HttpRequest;
        use tower::ServiceExt;

        // Deleting a `.route(...)` line is otherwise invisible: the constant,
        // the stylesheet and the bytes all still agree, and the page just
        // 404s in a browser nobody opened. Only `/` is left out here -- it
        // reaches Forgejo over the network.
        for (path, content_type) in [(BG_ROUTE, "image/webp"), ("/hub.css", "text/css")] {
            let response = router()
                .oneshot(
                    HttpRequest::builder()
                        .uri(path)
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .expect("router panicked");
            assert_eq!(response.status(), StatusCode::OK, "{path} is not served");
            let served = response
                .headers()
                .get(header::CONTENT_TYPE)
                .and_then(|v| v.to_str().ok())
                .unwrap_or("");
            assert!(
                served.starts_with(content_type),
                "{path} served as {served:?}, expected {content_type:?}"
            );
        }
    }
}
