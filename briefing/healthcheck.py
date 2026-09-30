"""This entrypoint uses only the standard library, even if dependency installation fails."""
import os
import sys
from .http import ping

try:
    ping(os.environ.get("HEALTHCHECKS_PING_URL", ""), success="--fail" not in sys.argv)
except RuntimeError as error:
    print(str(error), file=sys.stderr)
    sys.exit(1)
