#!/usr/bin/env python3
"""
Homestead Events Researcher Agent
Visits known event URLs to verify/update details, then runs broad discovery searches.
Outputs updated events.json and a research report.
"""

import json
import os
import re
import sys
import datetime
import anthropic

EVENTS_FILE = os.path.join(os.path.dirname(__file__), "../data/events.json")
LOG_DIR = os.path.join(os.path.dirname(__file__), "../logs")
DRAFTS_DIR = os.path.join(os.path.dirname(__file__), "../drafts")

RESEARCH_SYSTEM_PROMPT = """You are a research agent for the Farm2Table homestead events calendar.
Your job is to find accurate, up-to-date information about homesteading events, expos, and conferences.

When researching a known event URL:
- Find confirmed dates, location, ticket prices, speakers, and registration links
- Note if the event has been cancelled or postponed
- Flag any significant changes from what was previously known

When doing broad discovery:
- Search for homesteading, self-sufficiency, regenerative agriculture, and farm-to-table events
- Focus on 2026 events in the US (international notable ones are also welcome)
- Only include events with verified websites and at least partial date information
- Do not fabricate events — if you can't confirm it exists, skip it

Return your findings as structured JSON only. No prose outside the JSON block."""

KNOWN_EVENT_PROMPT = """Research this homestead event and return updated details.

Current record:
{event_json}

Visit the URL: {url}

Return a JSON object with these fields (only include fields where you found new or updated info):
{{
  "id": "{event_id}",
  "verified": true/false,
  "dates": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "notes": "any notes"}},
  "location": {{"venue": "", "city": "", "state": "", "region": ""}},
  "ticket_price": "",
  "speakers": [],
  "description": "",
  "highlights": [],
  "registration_url": "",
  "changes_noted": "summary of what changed or was confirmed",
  "last_researched": "{today}"
}}"""

BROAD_DISCOVERY_PROMPT = """Search for homesteading, self-sufficiency, regenerative agriculture, and farm-to-table events in 2026 that are NOT in this existing list:

{existing_event_names}

Focus on:
- Events with confirmed websites
- US events primarily (notable international ones welcome)
- Events happening in 2026
- Topics: homesteading, off-grid living, permaculture, regenerative farming, food preservation, animal husbandry, self-sufficiency, farm skills

Return a JSON array of newly discovered events in this format:
[
  {{
    "id": "short-kebab-id",
    "name": "Full Event Name",
    "status": "confirmed" or "pending",
    "dates": {{"start": "YYYY-MM-DD or null", "end": "YYYY-MM-DD or null", "notes": ""}},
    "location": {{"venue": "", "city": "", "state": "", "region": ""}},
    "url": "https://...",
    "description": "",
    "speakers": [],
    "ticket_price": "",
    "highlights": [],
    "source": "discovery",
    "verified": false,
    "social_posts": {{"facebook": null, "x": null, "youtube": null}},
    "posted": {{"facebook": false, "x": false, "youtube": false}},
    "last_researched": "{today}"
  }}
]

Only return events you can confirm exist. Return an empty array [] if nothing new found."""


def load_events():
    with open(EVENTS_FILE, "r") as f:
        return json.load(f)


def save_events(data):
    data["meta"]["last_updated"] = datetime.date.today().isoformat()
    data["meta"]["total_events"] = len(data["events"])
    with open(EVENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Saved {data['meta']['total_events']} events to events.json")


def log(message):
    today = datetime.date.today().isoformat()
    log_file = os.path.join(LOG_DIR, f"research_{today}.log")
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    print(line.strip())
    with open(log_file, "a") as f:
        f.write(line)


WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}


def _strip_js_comments(text):
    """Remove JS comments and trailing commas to make lax JSON parseable."""
    # Remove block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove line comments (but not URLs — only // not preceded by colon or slash)
    text = re.sub(r'(?<!:)(?<!/)//[^\n]*', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _balanced_extract(text, open_char, close_char):
    """Return the first balanced open_char...close_char substring, or None."""
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_from_text(text):
    """
    Robustly extract and parse a JSON object or array from a text that may
    contain prose, markdown code fences, or JavaScript-style comments.
    Returns the parsed object/list, or raises json.JSONDecodeError on failure.
    """
    # 1. Try markdown code fence (```json ... ``` or ``` ... ```)
    fence = re.search(r'```(?:json)?\s*([\[{].*?)\s*```', text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            try:
                return json.loads(_strip_js_comments(fence.group(1)))
            except json.JSONDecodeError:
                pass

    # 2. Try balanced extraction — prefer whichever opener appears first
    obj_pos = text.find('{')
    arr_pos = text.find('[')
    if arr_pos >= 0 and (obj_pos < 0 or arr_pos < obj_pos):
        pairs = [('[', ']'), ('{', '}')]
    else:
        pairs = [('{', '}'), ('[', ']')]
    for open_c, close_c in pairs:
        candidate = _balanced_extract(text, open_c, close_c)
        if candidate is None:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            try:
                return json.loads(_strip_js_comments(candidate))
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("No valid JSON found", text, 0)


def extract_json_from_blocks(content_blocks):
    """Concatenate all text blocks from the response."""
    texts = [b.text for b in content_blocks if hasattr(b, "text") and b.text]
    return "".join(texts)


def research_one_event(client, event, today):
    """Use web search to verify a single event. Returns response text."""
    prompt = KNOWN_EVENT_PROMPT.format(
        event_json=json.dumps(event, indent=2),
        url=event["url"],
        event_id=event["id"],
        today=today,
    )

    # web_search_20250305 is fully server-side — returns end_turn in one call
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )

    return extract_json_from_blocks(response.content)


def research_known_events(client, events_data):
    """Use web search to verify each known event and update the record."""
    today = datetime.date.today().isoformat()
    updated_count = 0

    for i, event in enumerate(events_data["events"]):
        log(f"Researching [{i+1}/{len(events_data['events'])}]: {event['name']}")

        try:
            response_text = research_one_event(client, event, today)
        except Exception as e:
            log(f"  ✗ API error: {e}")
            continue

        # Parse JSON from response
        try:
            updates = parse_json_from_text(response_text)
            # Merge updates into the event record
            for key, value in updates.items():
                if key not in ("id",) and value is not None:
                    if isinstance(value, dict) and isinstance(event.get(key), dict):
                        event[key].update({k: v for k, v in value.items() if v is not None})
                    else:
                        event[key] = value
            event["last_researched"] = today
            updated_count += 1
            log(f"  ✓ Updated: {updates.get('changes_noted', 'no changes noted')}")
        except json.JSONDecodeError as e:
            log(f"  ✗ JSON parse error: {e}")

    log(f"Known events research complete. Updated {updated_count} records.")
    return events_data


def discover_new_events(client, events_data):
    """Search broadly for new homesteading events not in the current calendar."""
    today = datetime.date.today().isoformat()
    existing_names = [e["name"] for e in events_data["events"]]

    log("Starting broad discovery search...")

    prompt = BROAD_DISCOVERY_PROMPT.format(
        existing_event_names="\n".join(f"- {n}" for n in existing_names),
        today=today,
    )

    # web_search_20250305 is server-side — single call returns end_turn
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = extract_json_from_blocks(response.content)

    try:
        new_events = parse_json_from_text(response_text)
        if not isinstance(new_events, list):
            new_events = [new_events] if new_events else []
        if new_events:
            events_data["events"].extend(new_events)
            log(f"Discovery found {len(new_events)} new events.")
            for e in new_events:
                log(f"  + {e['name']} ({e.get('dates', {}).get('start', 'date TBD')})")
        else:
            log("Discovery found no new events this run.")
    except json.JSONDecodeError as e:
        log(f"Discovery JSON parse error: {e}")
        log(f"Raw response: {response_text[:500]}")

    return events_data


def write_research_report(events_data):
    """Write a human-readable summary of the current calendar state."""
    today = datetime.date.today().isoformat()
    report_path = os.path.join(LOG_DIR, f"calendar_report_{today}.txt")

    confirmed = [e for e in events_data["events"] if e["status"] == "confirmed"]
    pending = [e for e in events_data["events"] if e["status"] == "pending"]

    # Sort confirmed by start date
    confirmed.sort(key=lambda e: e["dates"].get("start") or "9999")

    lines = [
        "=" * 60,
        f"HOMESTEAD EVENTS CALENDAR — {today}",
        f"Total Events: {len(events_data['events'])} | Confirmed: {len(confirmed)} | Pending: {len(pending)}",
        "=" * 60,
        "",
        "UPCOMING CONFIRMED EVENTS",
        "-" * 40,
    ]

    for e in confirmed:
        start = e["dates"].get("start", "TBD")
        end = e["dates"].get("end", "")
        date_str = f"{start}" + (f" – {end}" if end and end != start else "")
        lines.append(f"\n{e['name']}")
        lines.append(f"  Date: {date_str}")
        lines.append(f"  Location: {e['location'].get('city', '')}, {e['location'].get('state', '')}")
        lines.append(f"  URL: {e['url']}")
        if e.get("ticket_price"):
            lines.append(f"  Tickets: {e['ticket_price']}")
        if e.get("speakers"):
            lines.append(f"  Speakers: {', '.join(e['speakers'][:3])}" + (" +more" if len(e["speakers"]) > 3 else ""))

    if pending:
        lines += ["", "PENDING — DATES NEEDED", "-" * 40]
        for e in pending:
            lines.append(f"\n{e['name']}")
            lines.append(f"  Notes: {e['dates'].get('notes', 'check website')}")
            lines.append(f"  URL: {e['url']}")

    report_text = "\n".join(lines)
    with open(report_path, "w") as f:
        f.write(report_text)

    print(f"\n{report_text}\n")
    log(f"Report written to {report_path}")
    return report_path


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    # modes: full | known-only | discover-only | report-only

    client = anthropic.Anthropic()

    log(f"=== Homestead Events Researcher — mode: {mode} ===")
    events_data = load_events()

    if mode in ("full", "known-only"):
        events_data = research_known_events(client, events_data)
        save_events(events_data)

    if mode in ("full", "discover-only"):
        events_data = discover_new_events(client, events_data)
        save_events(events_data)

    report_path = write_research_report(events_data)
    log(f"=== Research run complete ===")
    return report_path


if __name__ == "__main__":
    main()
