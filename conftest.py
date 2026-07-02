"""Pytest root conftest.

Scripts under scripts/ are written to run standalone (python scripts/foo.py),
so they import siblings as top-level modules (e.g. `from common import ...`).
Tests import them as the scripts.* package instead, which leaves scripts/ off
sys.path. Add it here so both import styles resolve to the same modules.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
