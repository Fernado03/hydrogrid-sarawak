"""Pytest bootstrap for HydroGrid Sarawak.

Adds the src directory to sys.path so tests can import hydrogrid modules
without requiring a full package installation during Phase 0.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))