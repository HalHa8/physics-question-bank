"""PhysicsBank compatibility entry point: uvicorn main:app."""

import sys

# Configure Windows redirected output before importing business dependencies.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mathbank.application_factory import create_application
from mathbank.application_bindings import install_legacy_facade

_application = create_application()
app = _application.app
install_legacy_facade(sys.modules[__name__], _application)
