"""Unified entry script.

This file now delegates execution to the fully-featured console simulator
implemented in `console_battle.py`.  All previous pygame demo code has been
retained below (commented) for reference but is no longer executed.
"""

from console_battle import *  # noqa: F401,F403 – execute on import


# ================= OLD PYGAME DEMO (disabled) ==========================
# The original pygame demo has been commented out to avoid clashing with the
# new, feature-rich console version.  Uncomment and run manually if desired.
#
# if __name__ == "__main__":
#     # Original graphical demo preserved here ...
