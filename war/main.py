"""Unified entry script.

This file delegates execution to either the console or graphical (Pygame)
implementation depending on command-line flags.

Usage:
    python main.py            # run graphical advanced_battle (pygame)
    python main.py --console  # run ANSI/Colorama console_battle
"""

import sys

if __name__ == "__main__":
    if "--console" in sys.argv:
        from console_battle import *  # noqa: F401,F403 – executes console loop on import
    else:
        from advanced_battle import *  # noqa: F401,F403 – executes pygame loop on import

# Note: the original simple pygame demo remains below (commented out) for
# historical reference. It is not executed unless manually uncommented.
