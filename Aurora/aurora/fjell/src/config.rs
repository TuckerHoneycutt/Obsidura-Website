use serde::Deserialize;

#[derive(Deserialize, Debug, Clone)]
pub struct AgentEntry {
    pub username: String,
    #[allow(dead_code)] // read by the roster JSON; the hub renders the username
    pub display_name: String,
}

/// Where compose mounts `Caddyfile.d`. Pinned against compose.yml by
/// tests/test_hub_conformance.py — a default nothing mounts is how this file
/// silently returned an empty roster before 2026-07-31.
pub const DEFAULT_AGENTS_JSON_PATH: &str = "/etc/aurora/roster/agents.json";

/// The provisioned agents, as `dev-admin reconcile` last wrote them.
///
/// Read per request rather than cached: reconcile rewrites this file when a
/// developer is added, and a hub that needs a restart to notice is a hub that
/// is wrong exactly when someone is waiting on it. Same contract as
/// agent-authz's owners.json.
pub fn load_agents() -> Vec<AgentEntry> {
    let path = std::env::var("AGENTS_JSON_PATH")
        .unwrap_or_else(|_| DEFAULT_AGENTS_JSON_PATH.to_string());
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

/// Forgejo's origin as seen from inside the compose network.
///
/// Service DNS, not `127.0.0.1`: production's Caddy is host-networked but
/// fjell is not, and a branch publishes no host ports at all.
pub fn forgejo_internal_url() -> String {
    std::env::var("FORGEJO_INTERNAL_URL")
        .unwrap_or_else(|_| "http://forgejo:3000".to_string())
}
