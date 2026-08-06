"""dev-admin's startup race.

`depends_on: [forgejo]` with no condition means `reconcile` runs the instant
Forgejo's CONTAINER starts, before Forgejo is SERVING, and dies with curl
exit 22. Observed on this host: dev-admin Exited (1) after every fresh
deploy, with a traceback that names the admin token and so reads like an
auth failure. It is not - the identical request succeeds once Forgejo is up.
"""

from conftest import compose_config


def test_forgejo_declares_a_healthcheck():
    healthcheck = compose_config()["services"]["forgejo"].get("healthcheck")
    assert healthcheck, (
        "Forgejo declares no healthcheck, so nothing downstream can gate on "
        "it actually serving"
    )
    assert "healthz" in " ".join(healthcheck["test"]), (
        "Health must be checked against Forgejo's own /api/healthz, which "
        "reports cache and database readiness, not merely a listening socket"
    )


def test_dev_admin_waits_for_forgejo_to_be_healthy():
    depends = compose_config()["services"]["dev-admin"].get("depends_on") or {}
    assert "forgejo" in depends, "dev-admin must still depend on forgejo"
    assert depends["forgejo"].get("condition") == "service_healthy", (
        "A bare depends_on waits for the container to START, not for Forgejo "
        "to SERVE. That is the race that kills dev-admin on every deploy."
    )


def test_forgejo_healthcheck_probes_the_real_port_and_endpoint():
    """The healthcheck's contents, not merely its existence.

    Mutating the port to 3999, or replacing the command with something that
    always exits 0, both left the suite green -- and the first of those is
    exactly the "Forgejo never goes healthy, dev-admin blocks forever"
    scenario, which is strictly worse than the race it replaces.
    """
    healthcheck = compose_config()["services"]["forgejo"]["healthcheck"]
    command = " ".join(healthcheck["test"])

    assert "curl" in command, (
        "the probe must actually make a request; a command that merely exits "
        "0 reports health it never checked"
    )
    assert "3000" in command, (
        f"probe does not target Forgejo's real port: {command!r}. A wrong "
        "port never goes healthy and dev-admin blocks on service_healthy "
        "forever."
    )
    assert "/api/healthz" in command
    assert healthcheck.get("retries", 0) >= 6, (
        f"retries={healthcheck.get('retries')} is too few to cover a slow "
        "boot; the gate then fails closed on a healthy Forgejo"
    )
    assert healthcheck.get("start_period"), (
        "no start_period, so early probe failures count against retries "
        "while Forgejo is still legitimately booting"
    )
