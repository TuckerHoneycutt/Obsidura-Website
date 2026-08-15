"""ext_actions — the extension pack's task bodies, as a runner package.

Symlinked into the runner directory as `runner/ext_actions`, so definition
entries read `ext_actions.<module>.run`. The modules import their shared
helpers as top-level names (`from _compat import …`) so the same files run
standalone under the devserver harness; putting this package directory on
sys.path makes those imports resolve in the packaged case too.
"""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
