#!/bin/bash
# Homestead Events Calendar — Main Runner
# Usage:
#   ./run.sh phase1          — seed verification (research known events)
#   ./run.sh research        — full research (known + discovery)
#   ./run.sh generate        — generate social media drafts
#   ./run.sh email           — email pending drafts for review
#   ./run.sh calendar        — rebuild calendar.html from events.json
#   ./run.sh full            — research + generate + calendar + email (weekly cron)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$SCRIPT_DIR/agents"

# Activate virtual env if present
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

MODE="${1:-help}"

case "$MODE" in
  phase1)
    echo "=== Phase 1: Verifying seed events ==="
    python3 "$AGENTS/researcher.py" known-only
    ;;
  research)
    echo "=== Full Research: Known + Discovery ==="
    python3 "$AGENTS/researcher.py" full
    ;;
  generate)
    echo "=== Generating Social Media Drafts ==="
    python3 "$AGENTS/content_generator.py" "$2"
    ;;
  email)
    echo "=== Emailing Pending Drafts ==="
    python3 "$AGENTS/email_drafts.py"
    ;;
  calendar)
    echo "=== Building Calendar HTML ==="
    python3 "$AGENTS/build_calendar.py"
    echo "  → $SCRIPT_DIR/calendar.html"
    ;;
  full)
    echo "=== Full Weekly Run ==="
    python3 "$AGENTS/researcher.py" full
    python3 "$AGENTS/content_generator.py"
    python3 "$AGENTS/build_calendar.py"
    python3 "$AGENTS/email_drafts.py"
    ;;
  help|*)
    echo "Homestead Events Calendar"
    echo ""
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  phase1     Verify the 15 seed events (dates, details, tickets)"
    echo "  research   Full research: verify known + discover new events"
    echo "  generate   Generate Facebook/X/YouTube drafts for new events"
    echo "  calendar   Rebuild calendar.html from current events.json"
    echo "  email      Email pending drafts for your review"
    echo "  full       research + generate + calendar + email (weekly cron)"
    echo ""
    echo "Examples:"
    echo "  ./run.sh phase1"
    echo "  ./run.sh generate hoa-2026    # generate for one specific event"
    echo "  ./run.sh calendar             # rebuild calendar after manual edits"
    ;;
esac
