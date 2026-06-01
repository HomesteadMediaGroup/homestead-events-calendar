#!/usr/bin/env python3
"""
Homestead Events — Email Draft Sender
Sends pending draft posts for review via AgentMail REST API.
Run after content_generator.py produces new drafts.
"""

import json
import os
import glob
import datetime
import subprocess
import tempfile

DRAFTS_DIR = os.path.join(os.path.dirname(__file__), "../drafts")

AGENTMAIL_INBOX   = "homesteadmedia@agentmail.to"
AGENTMAIL_TOKEN   = "am_us_inbox_0b123cf25c6a3bbe741734605fc1105fc575f41298f2e6ffef749657bceed1f4"
AGENTMAIL_API_URL = f"https://api.agentmail.to/v0/inboxes/{AGENTMAIL_INBOX}/messages/send"
RECIPIENT_EMAIL   = "farm2tabledirect@protonmail.com"


def load_pending_drafts():
    drafts = []
    for path in glob.glob(os.path.join(DRAFTS_DIR, "*.json")):
        with open(path) as f:
            draft = json.load(f)
        if draft.get("status") == "pending_review":
            drafts.append((path, draft))
    drafts.sort(key=lambda x: x[1].get("generated_at", ""))
    return drafts


def format_email_body(drafts):
    today = datetime.date.today().strftime("%B %-d, %Y")
    lines = [
        f"Farm2Table Events — Draft Review",
        f"Generated: {today}",
        f"Events in this batch: {len(drafts)}",
        "",
        "Review each draft below. To approve a post, open the corresponding",
        f".json file in {DRAFTS_DIR} and change status to 'approved'.",
        "",
        "=" * 60,
    ]

    for _, draft in drafts:
        event_name = draft["event_name"]
        posts = draft["posts"]
        x_posts = posts.get("x", {})

        lines += [
            "",
            f"EVENT: {event_name}",
            "=" * 60,
            "",
            "--- FACEBOOK ---",
            posts.get("facebook", "(none)"),
            "",
            "--- X (TWITTER) ---",
            f"LEAD: {x_posts.get('lead', '')}",
            "",
            "THREAD:",
        ]
        for i, tweet in enumerate(x_posts.get("thread", []), 2):
            lines.append(f"[{i}/4] {tweet}")

        lines += [
            "",
            "--- YOUTUBE COMMUNITY POST ---",
            posts.get("youtube", "(none)"),
            "",
            "-" * 60,
        ]

    lines += [
        "",
        f"Draft files: {DRAFTS_DIR}",
        "Approve by editing the .json status field to 'approved', then run publisher.py",
    ]

    return "\n".join(lines)


def send_via_agentmail(subject, body, recipient):
    payload = json.dumps({
        "to": [recipient],
        "subject": subject,
        "text": body,
    })

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(payload)
    tmp.close()

    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        AGENTMAIL_API_URL,
        "-H", f"Authorization: Bearer {AGENTMAIL_TOKEN}",
        "-H", "Content-Type: application/json",
        "-d", f"@{tmp.name}",
    ], capture_output=True, text=True)

    os.unlink(tmp.name)

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        response = {"raw": result.stdout[:300]}

    if result.returncode != 0 or "error" in result.stdout.lower():
        raise RuntimeError(f"AgentMail API error: {result.stdout[:300]}")

    return response


def mark_drafts_emailed(draft_paths):
    for path in draft_paths:
        with open(path) as f:
            draft = json.load(f)
        draft["emailed_at"] = datetime.datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(draft, f, indent=2)


def main():
    drafts = load_pending_drafts()

    if not drafts:
        print("No pending drafts to email.")
        return

    print(f"Found {len(drafts)} pending draft(s).")

    today = datetime.date.today().strftime("%B %-d, %Y")
    subject = f"Farm2Table Events — {len(drafts)} Draft Post(s) Ready for Review ({today})"
    body = format_email_body(drafts)

    print(f"Sending: {AGENTMAIL_INBOX} → {RECIPIENT_EMAIL}")

    try:
        response = send_via_agentmail(subject, body, RECIPIENT_EMAIL)
        mark_drafts_emailed([path for path, _ in drafts])
        print(f"✓ Email sent — {len(drafts)} event draft(s).")
        print(f"  Response: {json.dumps(response)[:120]}")
    except Exception as e:
        print(f"✗ Email failed: {e}")
        print("\nFalling back — printing drafts to console:\n")
        print(body)


if __name__ == "__main__":
    main()
