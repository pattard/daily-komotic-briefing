from .app import main
from .http import APIError
import sys

try:
    sys.exit(main())
except (APIError, RuntimeError, ValueError) as error:
    print(f"BRIEFING FAILED: {error}", file=sys.stderr)
    sys.exit(1)
