"""Shared fixtures for the dev-administration suite.

The Caddy write surface is neutralised for EVERY test in this package, not
per-module. It started life as an autouse fixture inside test_provision.py;
test_agent_addressing.py then had to re-type the same five patch targets by
hand, which is the second copy of a list whose whole purpose is that
forgetting an entry has already cost production an outage --
`write_via_caddy` was imported inside reconcile(), so the per-test
@patch bound nothing, the real writer ran, and the suite wrote an empty
agents.conf into production's Caddy container. Every /agent/<user>/ route
returned 502 until it was repaired by hand.

Package-scoped so a new test file cannot opt out by omission.

forgejo_utils.time.sleep is stubbed here for a different reason. Several
reconcile tests reach the real Forgejo helpers against forgejo.example.com,
which fails DNS resolution -- curl exit 6. Task 11 added exit 6 to the
retried set, so each of those calls went from failing instantly to sleeping
2+4+6+8+10 = 30 seconds, and the suite went from 2s to over 100s. The retry
LOGIC is still exercised (test_forgejo_utils patches sleep itself and
asserts the backoff schedule); only the wall-clock cost is removed.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_caddy_writes():
    """Neutralise reconcile's entire Caddy write surface, for every test here.

    Autouse and module-wide rather than per-test decorators, because getting
    this wrong once already cost production an outage: `write_via_caddy` was
    imported INSIDE reconcile(), so the per-test
    `@patch("dev_administration.provision.write_via_caddy")` bound nothing,
    the real function ran, and the suite wrote an empty agents.conf into
    production's Caddy container -- every /agent/<user>/ route returned 502
    until it was repaired by hand.

    Two independent defences now exist: those imports are module-level (so
    patching them works at all), and this fixture means a new test cannot
    forget them. The §5.3 project guard is the third -- it is what turned the
    silent clobber into a loud ProjectMismatch.
    """
    with patch("dev_administration.forgejo_utils.time.sleep"), \
         patch("dev_administration.provision.write_via_caddy"), \
         patch("dev_administration.provision.write_agent_chooser"), \
         patch("dev_administration.provision.write_denied_page"), \
         patch("dev_administration.provision.write_owners_map"), \
         patch("dev_administration.provision.reload_caddy"), \
         patch("dev_administration.provision.find_service_container",
               return_value="aurora-caddy-1"), \
         patch("dev_administration.provision.generate_caddy_agents_conf",
               return_value="caddy-conf"), \
         patch("dev_administration.provision.generate_agents_json",
               return_value="[]"):
        yield


