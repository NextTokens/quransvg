"""Repository-local entry point for the QCF v4 builder.

This keeps the quick-start command identical on Windows, macOS and Linux and
avoids asking contributors to configure PYTHONPATH by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qsvg4.__main__ import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
