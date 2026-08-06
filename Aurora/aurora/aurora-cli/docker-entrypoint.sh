#!/bin/sh
# Prefer the MOUNTED checkout's package over the copy baked into the image.
#
# The registration form is `-v <production root>:<production root> -w
# <production root>`, so when the mount is present the working directory holds
# a real repository and `$PWD/aurora-cli` is the real package. Running that
# copy rather than the image's means the container and the host run the same
# code, and -- because `identity.package_root()` is `__file__`-relative, two
# directories up -- it also means `branch-env.yaml`, `branch-services.yaml`
# and `.env.template` resolve to the checkout's, not to files that are not in
# the image at all.
#
# Without the mount, `/app/aurora-cli` answers. That is enough for
# `initialize` and `tools/list`; anything touching the repository fails with a
# message rather than an import error.
set -eu

PYTHONPATH="${PWD}/aurora-cli:/app/aurora-cli${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

exec python -m aurora_cli "$@"
