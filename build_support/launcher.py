"""PyInstaller entry point. Normal application entry/UI is not modified."""
import os
from pathlib import Path
import sys
from build_support.paths import prepare_frozen_launch


def launch():
    # Resolve the packaging-only test destination before changing working dir.
    smoke=os.environ.get('AMCAD_PACKAGING_SMOKE_DIR')
    smoke=Path(smoke).resolve() if smoke else None
    prepare_frozen_launch(sys.argv)
    if smoke:
        from build_support.smoke_check import run
        return run(smoke)
    from app.main import main
    return main()


if __name__=='__main__':raise SystemExit(launch())
