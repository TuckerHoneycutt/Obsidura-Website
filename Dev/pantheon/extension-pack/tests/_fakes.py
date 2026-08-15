"""The slice of the runner shim's ctx the extension actions touch, faked.

Mirrors the contracts in actions/_compat.py: proxied resources answer with
the same envelope shapes the real connectors produce (s3 get/put, http
request, postgres query), and blob_put/blob_get behave like the kernel blob
store. Every proxied call is recorded so tests can assert on the audit
surface as well as the results.
"""

import base64
import hashlib
import os
import sys

ACTIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "actions")
if ACTIONS not in sys.path:
    sys.path.insert(0, ACTIONS)


class FakeResource:
    def __init__(self, ctx, name):
        self._ctx = ctx
        self._name = name

    def __getattr__(self, verb):
        return lambda **args: self._ctx._call(self._name, verb, args)


class FakeCtx:
    def __init__(self, objects=None, http=None):
        self.objects = dict(objects or {})  # object-store key -> bytes
        self.http = dict(http or {})        # (resource, path) -> (status, media, bytes)
        self.blobs = {}                     # sha256 -> (bytes, media_type)
        self.calls = []                     # every proxied (resource, verb, args)
        self.envelope = {"ts": "2026-08-15T00:00:00Z", "producer": "test@1"}

    def resource(self, name):
        return FakeResource(self, name)

    def _call(self, name, verb, args):
        self.calls.append((name, verb, args))
        if verb == "get":
            key = args["key"]
            if key not in self.objects:
                raise RuntimeError(f"NoSuchKey: {key}")
            return {"b64": base64.b64encode(self.objects[key]).decode("ascii")}
        if verb == "put":
            self.objects[args["key"]] = base64.b64decode(args["b64"])
            return {"etag": "fake"}
        if verb == "request":
            hit = self.http.get((name, args.get("path")))
            if hit is None:
                raise RuntimeError(f"no stub for {name} {args.get('path')}")
            status, media, body = hit
            return {
                "status": status,
                "headers": {"content-type": media},
                "body_b64": base64.b64encode(body).decode("ascii"),
            }
        if verb == "query":
            return {"row_count": 0, "rows": []}
        raise RuntimeError(f"fake ctx has no verb {verb}")

    def blob_put(self, data, media_type="application/octet-stream"):
        digest = hashlib.sha256(data).hexdigest()
        self.blobs[digest] = (data, media_type)
        return {"blob": digest, "media_type": media_type, "size_bytes": len(data)}

    def blob_get(self, digest):
        return self.blobs[digest][0]


def run_tests(namespace):
    """The shared bare-interpreter runner: every test_* in `namespace`."""
    failures = 0
    for name in sorted(namespace):
        fn = namespace[name]
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 — a test runner reports, never crashes
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print("FAILED" if failures else "OK")
    sys.exit(1 if failures else 0)
