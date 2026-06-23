"""Pytest bootstrap: put `scripts/` on sys.path so tests import packages
(`rules`, `core`, `pipelines`, ...) the same way `main.py` does at runtime.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
