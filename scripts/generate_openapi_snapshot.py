#!/usr/bin/env python3
"""
Generates talent-os/backend/openapi.snapshot.json from the live FastAPI
app object (main.app.openapi()) -- no server needs to be running, no DB
needed (app.openapi() only introspects routes/pydantic models).

Used two ways:
  - locally, after changing routers/models, to refresh the committed
    snapshot: `python3 scripts/generate_openapi_snapshot.py`
  - in CI (.github/workflows/ci.yml), with --check: regenerate into a temp
    file and diff against the committed one, failing the build if the API
    surface changed without the snapshot being updated in the same PR.

Needs the same env vars as running the app for real (JWT_SECRET etc. --
core/config.py.Settings validates jwt_secret length at import time) --
CI sets throwaway ones, same as it does for pytest.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "talent-os" / "backend"
SNAPSHOT_PATH = BACKEND_DIR / "openapi.snapshot.json"

sys.path.insert(0, str(BACKEND_DIR))


def build_snapshot() -> str:
    import main  # noqa: E402  (needs sys.path insert above first)

    spec = main.app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main_cli():
    check = "--check" in sys.argv
    generated = build_snapshot()

    if check:
        if not SNAPSHOT_PATH.exists():
            print(f"MISMATCH: {SNAPSHOT_PATH} does not exist. Run "
                  f"`python3 scripts/generate_openapi_snapshot.py` and commit it.")
            return 1
        current = SNAPSHOT_PATH.read_text(encoding="utf-8")
        if current != generated:
            print("MISMATCH: openapi.snapshot.json is out of date with the live API surface.")
            print("Run `python3 scripts/generate_openapi_snapshot.py` locally and commit the diff.")
            return 1
        print("OK: openapi.snapshot.json matches the live API surface.")
        return 0

    SNAPSHOT_PATH.write_text(generated, encoding="utf-8")
    print(f"Wrote {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
