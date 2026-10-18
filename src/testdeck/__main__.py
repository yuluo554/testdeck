"""``python -m testdeck`` 入口（README 里两条通路都要能用）。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
