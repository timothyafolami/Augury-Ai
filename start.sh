#!/usr/bin/env bash
#
# One command to run Augury: installs everything, builds the interface, and
# serves the API and the UI from a single process on one port.
#
#   ./start.sh          replay a recorded review -- no API key, spends nothing
#   ./start.sh --live   review your own repositories -- needs a provider key
#
# There is one server. The interface is built to static files and served by the
# same FastAPI process that answers /api, so there is no second port to
# forward, no CORS to configure, and nothing to start in a second terminal.

set -euo pipefail

cd "$(dirname "$0")"

PORT="${AUGURY_PORT:-8000}"
LIVE=0
for argument in "$@"; do
  case "$argument" in
    --live) LIVE=1 ;;
    --help|-h)
      sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown option: $argument" >&2
      echo "try: ./start.sh [--live]" >&2
      exit 2
      ;;
  esac
done

say() { printf '\033[35m▸\033[0m %s\n' "$1"; }
die() { printf '\033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

# -- what has to be here ------------------------------------------------------

command -v uv >/dev/null 2>&1 || die \
  "uv is not installed. Install it with:
     curl -LsSf https://astral.sh/uv/install.sh | sh
   then run this script again."

say "installing the engine and its dependencies"
uv sync --extra experiments --quiet

# The interface needs Node once, to build. The engine never does, so a missing
# Node is a reason to skip the UI rather than a reason to stop: the CLI and the
# MCP server are unaffected.
if [ ! -d web/dist ]; then
  if command -v npm >/dev/null 2>&1; then
    say "building the interface (once)"
    (cd web && npm install --silent --no-audit --no-fund && npm run build --silent)
  else
    printf '\033[33m!\033[0m %s\n' \
      "npm not found, so the interface will not be built. The API still runs,
   and so do 'uv run augury review' and 'uv run augury mcp'. Install Node
   from https://nodejs.org and re-run this script to get the UI."
  fi
fi

# -- how it will run ----------------------------------------------------------

if [ "$LIVE" -eq 1 ]; then
  # Any one of the four is enough; the settings module decides which provider
  # that implies and says so if the choice is ambiguous.
  if [ -z "${GROQ_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ] &&
     [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${DEEPSEEK_API_KEY:-}" ] &&
     [ ! -f .env ]; then
    die "--live needs a provider key. Copy .env.example to .env and fill in one
   of GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY or DEEPSEEK_API_KEY,
   or run ./start.sh with no arguments to replay a recorded review for free."
  fi
  say "live mode: reviews cost money, and the spend ceiling in the interface is enforced"
else
  export AUGURY_REPLAY_ONLY=1
  # Pinned to what the recordings were made against. A cassette is keyed by
  # model id, so a different one here would miss every call and the run would
  # stop with an empty report.
  export AUGURY_PROVIDER=groq
  export AUGURY_MODEL=openai/gpt-oss-120b
  say "replay mode: no API key needed, nothing is spent"
  say "point it at eval/cases/B01-orders-service/repo (Python),"
  say "              eval/cases/E01-go-inventory/repo (Go),"
  say "           or eval/cases/F01-ts-checkout/repo (TypeScript)"
fi

say "http://localhost:${PORT}"
echo

AUGURY_PORT="$PORT" exec uv run --extra experiments python -m augury.server
