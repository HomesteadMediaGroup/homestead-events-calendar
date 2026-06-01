#!/usr/bin/env python3
"""
Homestead Events Content Generator
For each event without social posts, generates platform-specific drafts
using the Farm2Table voice and saves them to the drafts folder.
"""

import json
import os
import datetime
import anthropic

EVENTS_FILE = os.path.join(os.path.dirname(__file__), "../data/events.json")
DRAFTS_DIR = os.path.join(os.path.dirname(__file__), "../drafts")

VOICE_SYSTEM_PROMPT = """You are the social media voice for Farm2Table, a brand built around the homestead lifestyle, regenerative agriculture, and community-driven self-sufficiency.

VOICE & TONE:
- Warm, grounded, and community-first — speak like someone who actually homesteads
- Celebratory of the movement, not preachy
- Use dissociative language: say "the homestead community" or "folks in the movement" not "we/our community" in ways that feel like marketing
- Conversational but purposeful — every post has a clear call to action
- Avoid corporate-speak, buzzwords like "synergy" or "leverage"
- Lean into specifics: real speaker names, real skills (butchering, cheesemaking, foraging), real places

HASHTAGS (mix and match, don't use all):
#Farm2Table #HomesteadLife #HomesteadingCommunity #RegenerativeAg #OffGridLiving
#GrowYourOwn #SelfSufficiency #FoodFreedom #BackToBasics #HomesteadExpo

CONTENT PILLARS:
- Learn a skill (workshops, demos, hands-on)
- Find your people (community, family-friendly, connections)
- Hear from the best (notable speakers, practitioners)
- Get it done (tickets, registration, dates)

PLATFORM RULES:
- Facebook: 150-250 words. Event details up front, story in the middle, CTA at end. Use line breaks for readability.
- X: Lead tweet 240 chars max. Follow with a 3-tweet thread expanding on speakers, skills, and tickets.
- YouTube Community Post: 80-120 words. Casual, conversational. End with a question to drive comments."""

CONTENT_PROMPT = """Generate social media content for this homesteading event.

EVENT DATA:
{event_json}

Return a JSON object with these three keys:
{{
  "facebook": "full Facebook post text",
  "x": {{
    "lead": "lead tweet (240 chars max)",
    "thread": ["tweet 2 text", "tweet 3 text", "tweet 4 text"]
  }},
  "youtube": "YouTube community post text"
}}

Write all three. Use the Farm2Table voice. Include real details from the event data — specific speakers, skills, location, and dates. End every platform post with a clear CTA pointing to the event URL."""


def load_events():
    with open(EVENTS_FILE, "r") as f:
        return json.load(f)


def save_events(data):
    data["meta"]["last_updated"] = datetime.date.today().isoformat()
    with open(EVENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def format_date(event):
    start = event["dates"].get("start")
    end = event["dates"].get("end")
    if not start:
        return event["dates"].get("notes", "Dates TBD")
    if end and end != start:
        # e.g. "October 9–10, 2026"
        try:
            s = datetime.date.fromisoformat(start)
            e = datetime.date.fromisoformat(end)
            if s.month == e.month:
                return f"{s.strftime('%B')} {s.day}–{e.day}, {s.year}"
            return f"{s.strftime('%B %-d')} – {e.strftime('%B %-d, %Y')}"
        except Exception:
            return f"{start} – {end}"
    try:
        s = datetime.date.fromisoformat(start)
        return s.strftime("%B %-d, %Y")
    except Exception:
        return start


def save_draft(event, posts):
    today = datetime.date.today().isoformat()
    event_id = event["id"]
    draft_path = os.path.join(DRAFTS_DIR, f"{event_id}_{today}.json")

    draft = {
        "event_id": event_id,
        "event_name": event["name"],
        "generated_at": datetime.datetime.now().isoformat(),
        "status": "pending_review",
        "posts": posts,
    }

    with open(draft_path, "w") as f:
        json.dump(draft, f, indent=2)

    # Also write a human-readable version
    readable_path = os.path.join(DRAFTS_DIR, f"{event_id}_{today}.txt")
    lines = [
        f"DRAFT SOCIAL POSTS — {event['name']}",
        f"Generated: {today}",
        f"Status: PENDING REVIEW",
        "=" * 60,
        "",
        "FACEBOOK",
        "-" * 40,
        posts.get("facebook", ""),
        "",
        "X (TWITTER)",
        "-" * 40,
        f"LEAD TWEET:\n{posts.get('x', {}).get('lead', '')}",
        "",
        "THREAD:",
    ]
    for i, tweet in enumerate(posts.get("x", {}).get("thread", []), 2):
        lines.append(f"[{i}/4] {tweet}")
    lines += [
        "",
        "YOUTUBE COMMUNITY POST",
        "-" * 40,
        posts.get("youtube", ""),
        "",
        "=" * 60,
        "To approve: update status to 'approved' in the JSON file",
        f"JSON draft: {draft_path}",
    ]

    with open(readable_path, "w") as f:
        f.write("\n".join(lines))

    return draft_path, readable_path


def generate_content(client, event):
    """Generate social media posts for a single event."""
    # Add formatted date to event data for the prompt
    event_copy = dict(event)
    event_copy["formatted_date"] = format_date(event)

    prompt = CONTENT_PROMPT.format(event_json=json.dumps(event_copy, indent=2))

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        system=VOICE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text

    start = response_text.find("{")
    end = response_text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(response_text[start:end])

    raise ValueError(f"Could not parse JSON from response: {response_text[:200]}")


def main():
    import sys

    # Optional: pass event ID to generate for just one event
    target_id = sys.argv[1] if len(sys.argv) > 1 else None

    client = anthropic.Anthropic()
    events_data = load_events()

    generated = []
    skipped = []

    for event in events_data["events"]:
        if target_id and event["id"] != target_id:
            continue

        # Skip if already has posts drafted
        if any(event["social_posts"].get(p) for p in ("facebook", "x", "youtube")):
            skipped.append(event["name"])
            continue

        # Skip pending events with no dates (not enough info to write a useful post)
        if event["status"] == "pending" and not event["dates"].get("start"):
            print(f"Skipping (no dates): {event['name']}")
            skipped.append(event["name"])
            continue

        print(f"Generating content for: {event['name']}")

        try:
            posts = generate_content(client, event)
            draft_json, draft_txt = save_draft(event, posts)

            # Store posts back on the event record
            event["social_posts"]["facebook"] = posts.get("facebook")
            event["social_posts"]["x"] = posts.get("x")
            event["social_posts"]["youtube"] = posts.get("youtube")

            generated.append(event["name"])
            print(f"  ✓ Draft saved: {draft_txt}")

        except Exception as e:
            print(f"  ✗ Error: {e}")

    save_events(events_data)

    print(f"\nContent generation complete.")
    print(f"  Generated: {len(generated)} events")
    print(f"  Skipped: {len(skipped)} events")
    if generated:
        print(f"\nDrafts are in: {DRAFTS_DIR}")
        print("Review and approve before publishing.")


if __name__ == "__main__":
    main()
