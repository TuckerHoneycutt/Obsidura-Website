# `aurora-cli:local` -- the containerised MCP facade (Task 11, spec 7.3).
#
# Shape mirrors dev-administration/Dockerfile: python slim, the docker client,
# pyyaml, PYTHONPATH, an ENTRYPOINT on the module. Decision D-A is why the
# `pip install` line has exactly one name on it -- every runtime dependency is
# a thing that must exist in the host venv, in a fresh worktree AND here.
#
# THE MOUNTS ARE NOT OPTIONAL, AND THERE ARE THREE. Spec 7.3's registration
# command gives this image only the docker socket:
#
#     docker run -i --rm -v /var/run/docker.sock:/var/run/docker.sock \
#         aurora-cli:local mcp
#
# That cannot work for anything beyond the handshake, for three measured
# reasons rather than one:
#
#  1. `branch up` runs `git worktree add` and `cp --reflink` against HOST
#     paths, and Compose resolves bind sources host-side, so a container
#     holding only the socket has no repository and every relative bind it
#     declares resolves against a path that does not exist on the host.
#  2. **`docker.io` does NOT ship the Compose plugin.** Measured in this
#     image: `docker compose version` -> "'compose' is not a docker command";
#     `/usr/libexec/docker/cli-plugins/` holds `docker-buildx` and nothing
#     else. Debian trixie's `docker-compose` package is 2.26.1 -- a DIFFERENT
#     MAJOR VERSION from the v5.3.1 this chunk measured everything against
#     (profile-agnostic `down`, NDJSON from `ps --format json`, `!reset` and
#     `!override` across an `include:` boundary). Installing it would put an
#     unmeasured Compose in front of production's daemon, so the plugin is
#     MOUNTED from the host instead: same binary, no version drift. Verified
#     -- `docker compose version` inside this image then reports v5.3.1.
#  3. `git` refuses a bind-mounted repository owned by another uid ("detected
#     dubious ownership"), so the container runs as the host user rather than
#     as root. That is also what stops a root process writing into
#     production's checkout.
#
# The working form, derived (production root is the value
# `identity.production_root()` resolves to; `aurora branch ls` prints it):
#
#     docker run -i --rm \
#         --user "$(id -u):$(getent group docker | cut -d: -f3)" \
#         -v /var/run/docker.sock:/var/run/docker.sock \
#         -v /usr/libexec/docker/cli-plugins/docker-compose:/usr/libexec/docker/cli-plugins/docker-compose:ro \
#         -v <production root>:<production root> \
#         -w <production root> \
#         aurora-cli:local mcp
#
# The repository path must be identical on both sides because every path this
# tool hands to Compose is interpreted by the DAEMON, on the host, not inside
# this container. docs/post-implementation-steps.md (Task 12) carries the
# derived form.
#
# `docker-entrypoint.sh` puts `$PWD/aurora-cli` on PYTHONPATH ahead of the
# baked-in copy, so with the mount above the code that runs is the code in the
# mounted checkout -- one source of truth -- and `identity.package_root()`
# (which is `__file__`-relative, two levels up) resolves to the checkout
# rather than to a stub inside the image.

FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

RUN apt-get update -qq && \
    apt-get install -y -qq docker.io curl git && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyyaml

# `/home` IS A SYMLINK TO `/var/home` ON THIS HOST, and the container must
# agree or nothing works. Every production container carries
# `com.docker.compose.project.working_dir=/home/...` -- the UNRESOLVED form --
# while Python resolves the checkout to `/var/home/...`.
# `identity.production_project()` compares those two after `Path.resolve()`,
# which is correct on the host because the symlink makes them the same file,
# and WRONG in a stock Debian container where `/home` is an ordinary empty
# directory. Measured, without this line:
#
#   $ ... aurora-cli:local branch ls
#   error: The checkout at /var/home/.../<checkout> declares compose project
#   '<name>', but containers with that label were deployed from
#   ['/home/.../<checkout>']. ... Refusing to choose between them.
#
# i.e. the facade refuses to identify production and every lifecycle tool
# stops -- failing safe, but stopping. Mounting the checkout at the
# unresolved path instead does not fix it: a linked worktree's `.git` file
# records the `/var/home/...` gitdir, so git then cannot find the repository
# at all (also measured).
#
# This is the one host-shaped assumption in the image, stated here rather
# than discovered later. On a host where `/home` is an ordinary directory the
# link is still consistent -- `/home/x` and `/var/home/x` resolve to the same
# place in both directions -- but if that host has no `/var/home` at all, drop
# this line and mount the checkout at whatever path its own labels carry.
RUN if [ ! -L /home ]; then rmdir /home && ln -s /var/home /home; fi

# The fallback copy. It exists so `initialize` and `tools/list` answer with no
# mount at all -- which is what makes the image smoke-testable, and what lets a
# misconfigured registration fail with a JSON-RPC error a caller can read
# rather than an import traceback on a closed pipe. Anything that touches the
# repository needs the mount, and says so.
#
# The manifests are deliberately NOT baked in beside it. `branch-env.yaml` is
# a safety artefact -- it is what tells the facade which variables are secret
# -- and a stale copy of it inside an image is a second source of truth for
# exactly the wrong thing. Without the mount the facade cannot read it, cannot
# verify its own output, and therefore refuses to produce a tool result at
# all; see `mcp._emit`, where that coupling is what makes the handshake still
# answering safe rather than lax.
COPY aurora_cli /app/aurora-cli/aurora_cli
COPY docker-entrypoint.sh /usr/local/bin/aurora-cli-entrypoint
RUN chmod +x /usr/local/bin/aurora-cli-entrypoint

WORKDIR /app

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/local/bin/aurora-cli-entrypoint"]
CMD ["mcp"]
