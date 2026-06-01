#!/usr/bin/env python3
"""
Homestead Events Calendar Builder
Reads events.json and generates a standalone HTML calendar with
clickable event chips that open a modal with full details + links.
"""

import json
import os
import datetime

EVENTS_FILE = os.path.join(os.path.dirname(__file__), "../data/events.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "../calendar.html")

REGION_COLORS = {
    "Southeast":  "#6ab04c",
    "South":      "#e67e22",
    "Midwest":    "#3498db",
    "Northwest":  "#8e44ad",
    "Northeast":  "#e74c3c",
    "Southwest":  "#f39c12",
    "Alaska":     "#1abc9c",
    "default":    "#546e7a",
}

def load_events():
    with open(EVENTS_FILE) as f:
        return json.load(f)

def month_name(n):
    return ["","January","February","March","April","May","June",
            "July","August","September","October","November","December"][n]

def build_calendar_months(events):
    """Return dict of {(year,month): [events]} for all confirmed/pending upcoming events."""
    months = {}
    today = datetime.date.today()

    for e in events:
        if e.get("status") in ("past", "completed", "archived"):
            continue
        start_str = e["dates"].get("start")
        if not start_str:
            continue
        try:
            start = datetime.date.fromisoformat(start_str)
        except ValueError:
            continue
        key = (start.year, start.month)
        months.setdefault(key, []).append(e)

    return dict(sorted(months.items()))

def event_chip_color(event):
    region = event.get("location", {}).get("region", "default")
    return REGION_COLORS.get(region, REGION_COLORS["default"])

def days_in_month(year, month):
    if month == 12:
        return (datetime.date(year + 1, 1, 1) - datetime.date(year, month, 1)).days
    return (datetime.date(year, month + 1, 1) - datetime.date(year, month, 1)).days

def first_weekday(year, month):
    return datetime.date(year, month, 1).weekday()  # 0=Mon

def format_date_range(event):
    start = event["dates"].get("start")
    end = event["dates"].get("end")
    notes = event["dates"].get("notes", "")
    if not start:
        return notes or "Date TBD"
    try:
        s = datetime.date.fromisoformat(start)
        if end and end != start:
            e = datetime.date.fromisoformat(end)
            if s.month == e.month:
                date_str = f"{s.strftime('%B')} {s.day}–{e.day}, {s.year}"
            else:
                date_str = f"{s.strftime('%B %-d')} – {e.strftime('%B %-d, %Y')}"
        else:
            date_str = s.strftime("%B %-d, %Y")
        if notes:
            date_str += f" <span class='date-note'>({notes})</span>"
        return date_str
    except Exception:
        return start

def speakers_html(event):
    speakers = event.get("speakers", [])
    if not speakers:
        return ""
    shown = speakers[:6]
    more = len(speakers) - 6
    html = ", ".join(shown)
    if more > 0:
        html += f" <em>+{more} more</em>"
    return html

def highlights_html(event):
    h = event.get("highlights", [])
    if not h:
        return ""
    return "".join(f'<span class="tag">{x}</span>' for x in h)

def modal_data(events):
    """Build JS object literal for all events."""
    items = []
    for e in events:
        if e.get("status") in ("past", "completed", "archived"):
            continue
        color = event_chip_color(e)
        loc = e.get("location", {})
        location_str = ", ".join(filter(None, [
            loc.get("venue", ""),
            loc.get("city", ""),
            loc.get("state", "")
        ]))
        ticket = e.get("ticket_price") or "See website for pricing"
        speakers = e.get("speakers", [])
        highlights = e.get("highlights", [])
        url = e.get("url", "#")

        obj = {
            "id": e["id"],
            "name": e["name"],
            "color": color,
            "date": format_date_range(e),
            "location": location_str,
            "description": e.get("description", ""),
            "speakers": speakers,
            "highlights": highlights,
            "ticket_price": ticket,
            "url": url,
            "status": e.get("status", "confirmed"),
            "verified": e.get("verified", False),
        }
        items.append(obj)
    return json.dumps(items, indent=2)

def calendar_grid_html(year, month, month_events):
    """Build one month's grid HTML."""
    dim = days_in_month(year, month)
    # first_weekday: 0=Mon, convert to 0=Sun
    fw = (first_weekday(year, month) + 1) % 7

    # Map day → list of events
    day_events = {}
    for e in month_events:
        start_str = e["dates"].get("start", "")
        end_str = e["dates"].get("end", start_str)
        try:
            s = datetime.date.fromisoformat(start_str)
            en = datetime.date.fromisoformat(end_str) if end_str else s
        except Exception:
            continue
        for d in range(s.day, min(en.day + 1, dim + 1)):
            if s.month == year or en.month == month:
                day_events.setdefault(d, []).append(e)

    cells = []
    # Empty cells before first day
    for _ in range(fw):
        cells.append('<div class="day empty"></div>')

    today = datetime.date.today()

    for day in range(1, dim + 1):
        is_today = (datetime.date(year, month, day) == today)
        today_class = " today" if is_today else ""
        evs = day_events.get(day, [])
        chips = ""
        for e in evs:
            color = event_chip_color(e)
            # Only show chip on start day
            start_str = e["dates"].get("start", "")
            try:
                sd = datetime.date.fromisoformat(start_str)
                if sd.day != day or sd.month != month:
                    # continuation — show thin bar
                    chips += f'<div class="chip continuation" style="background:{color}88;" data-id="{e["id"]}"></div>'
                    continue
            except Exception:
                pass
            name_short = e["name"][:28] + "…" if len(e["name"]) > 28 else e["name"]
            chips += (f'<div class="chip" style="background:{color};" '
                      f'data-id="{e["id"]}" onclick="openModal(\'{e["id"]}\')">'
                      f'{name_short}</div>')

        cells.append(
            f'<div class="day{today_class}">'
            f'<span class="day-num">{day}</span>'
            f'{chips}'
            f'</div>'
        )

    # Fill trailing cells
    total = fw + dim
    remainder = (7 - total % 7) % 7
    for _ in range(remainder):
        cells.append('<div class="day empty"></div>')

    return "\n".join(cells)

def build_html(events_data):
    events = events_data["events"]
    last_updated = events_data["meta"].get("last_updated", "")
    months = build_calendar_months(events)

    legend_html = "".join(
        f'<span class="legend-item"><span class="legend-dot" style="background:{c};"></span>{r}</span>'
        for r, c in REGION_COLORS.items() if r != "default"
    )

    months_html = ""
    for (year, month), month_events in months.items():
        grid = calendar_grid_html(year, month, month_events)
        months_html += f"""
        <div class="month-block">
          <h2 class="month-title">{month_name(month)} {year}</h2>
          <div class="cal-grid">
            <div class="dow">Sun</div><div class="dow">Mon</div><div class="dow">Tue</div>
            <div class="dow">Wed</div><div class="dow">Thu</div><div class="dow">Fri</div>
            <div class="dow">Sat</div>
            {grid}
          </div>
        </div>"""

    events_js = modal_data(events)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Homestead Events Calendar 2026 — Farm2Table</title>
<style>
  :root {{
    --green: #6ab04c;
    --dark: #2d4a1e;
    --bg: #f9f6f1;
    --card: #ffffff;
    --border: #ddd;
    --shadow: 0 2px 12px rgba(0,0,0,0.10);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Georgia, serif; background: var(--bg); color: #222; }}

  header {{
    background: var(--dark);
    color: white;
    padding: 28px 32px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }}
  header h1 {{ font-size: 1.6rem; font-weight: normal; letter-spacing: 0.5px; }}
  header .sub {{ font-size: 0.85rem; opacity: 0.7; margin-top: 4px; }}
  .updated {{ font-size: 0.78rem; opacity: 0.6; }}

  .legend {{
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 10px 32px;
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: center;
    font-size: 0.82rem;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{ width: 11px; height: 11px; border-radius: 50%; display: inline-block; }}

  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 60px; }}

  .month-block {{ margin-bottom: 48px; }}
  .month-title {{
    font-size: 1.3rem;
    font-weight: normal;
    color: var(--dark);
    border-bottom: 2px solid var(--green);
    padding-bottom: 6px;
    margin-bottom: 12px;
  }}

  .cal-grid {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
    background: var(--border);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }}
  .dow {{
    background: var(--dark);
    color: white;
    text-align: center;
    font-size: 0.75rem;
    padding: 6px 2px;
    letter-spacing: 0.5px;
  }}
  .day {{
    background: var(--card);
    min-height: 90px;
    padding: 6px 5px 5px;
    position: relative;
    vertical-align: top;
  }}
  .day.empty {{ background: #f3f0eb; }}
  .day.today {{ background: #f0f8ec; }}
  .day-num {{
    font-size: 0.78rem;
    color: #999;
    display: block;
    margin-bottom: 4px;
    font-family: sans-serif;
  }}
  .day.today .day-num {{ color: var(--green); font-weight: bold; }}

  .chip {{
    display: block;
    font-size: 0.7rem;
    font-family: sans-serif;
    color: white;
    padding: 3px 5px;
    border-radius: 3px;
    margin-bottom: 2px;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
    transition: opacity 0.15s;
  }}
  .chip:hover {{ opacity: 0.85; }}
  .chip.continuation {{
    height: 5px;
    padding: 0;
    border-radius: 0;
    cursor: pointer;
  }}

  /* Modal */
  .overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.55);
    z-index: 100;
    justify-content: center;
    align-items: flex-start;
    padding: 40px 16px;
    overflow-y: auto;
  }}
  .overlay.active {{ display: flex; }}
  .modal {{
    background: var(--card);
    border-radius: 10px;
    max-width: 560px;
    width: 100%;
    box-shadow: 0 8px 40px rgba(0,0,0,0.2);
    overflow: hidden;
    position: relative;
  }}
  .modal-header {{
    padding: 20px 24px 16px;
    color: white;
  }}
  .modal-header h2 {{ font-size: 1.15rem; font-weight: normal; line-height: 1.4; }}
  .modal-header .event-date {{ font-size: 0.85rem; opacity: 0.9; margin-top: 6px; }}
  .modal-body {{ padding: 20px 24px 24px; }}
  .modal-close {{
    position: absolute;
    top: 14px; right: 16px;
    background: none; border: none;
    color: white; font-size: 1.4rem;
    cursor: pointer; opacity: 0.8;
    line-height: 1;
  }}
  .modal-close:hover {{ opacity: 1; }}

  .detail-row {{
    display: flex;
    gap: 10px;
    margin-bottom: 12px;
    font-size: 0.9rem;
    align-items: flex-start;
  }}
  .detail-label {{
    font-family: sans-serif;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #888;
    min-width: 72px;
    padding-top: 2px;
  }}
  .detail-value {{ color: #333; line-height: 1.5; }}

  .tags {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 4px; }}
  .tag {{
    background: #f0f0f0;
    border-radius: 3px;
    padding: 2px 7px;
    font-size: 0.72rem;
    font-family: sans-serif;
    color: #555;
  }}

  .modal-actions {{
    display: flex;
    gap: 10px;
    margin-top: 20px;
    flex-wrap: wrap;
  }}
  .btn {{
    display: inline-block;
    padding: 10px 20px;
    border-radius: 5px;
    text-decoration: none;
    font-family: sans-serif;
    font-size: 0.85rem;
    font-weight: bold;
    transition: opacity 0.15s;
  }}
  .btn:hover {{ opacity: 0.85; }}
  .btn-primary {{ background: var(--green); color: white; }}
  .btn-secondary {{
    background: white;
    color: var(--dark);
    border: 2px solid var(--dark);
  }}

  .verified-badge {{
    display: inline-block;
    font-family: sans-serif;
    font-size: 0.7rem;
    background: #e8f5e0;
    color: #4a7c2f;
    border-radius: 3px;
    padding: 2px 6px;
    margin-left: 8px;
    vertical-align: middle;
  }}

  @media (max-width: 600px) {{
    .cal-grid {{ font-size: 0.7rem; }}
    .day {{ min-height: 60px; }}
    .chip {{ font-size: 0.62rem; padding: 2px 3px; }}
    header h1 {{ font-size: 1.2rem; }}
  }}
</style>
</head>
<body>

<header>
  <div>
    <h1>🌱 Homestead Events Calendar</h1>
    <div class="sub">Farm2Table — 2026 Conference & Expo Guide</div>
  </div>
  <div class="updated">Updated: {last_updated}</div>
</header>

<div class="legend">
  <strong style="font-family:sans-serif;font-size:0.8rem;">Region:</strong>
  {legend_html}
</div>

<main>
{months_html}
</main>

<!-- Modal Overlay -->
<div class="overlay" id="overlay" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="modal-header" id="modal-header">
      <button class="modal-close" onclick="closeModalDirect()">✕</button>
      <h2 id="modal-title"></h2>
      <div class="event-date" id="modal-date"></div>
    </div>
    <div class="modal-body">
      <div class="detail-row">
        <span class="detail-label">Location</span>
        <span class="detail-value" id="modal-location"></span>
      </div>
      <div class="detail-row" id="modal-ticket-row">
        <span class="detail-label">Tickets</span>
        <span class="detail-value" id="modal-ticket"></span>
      </div>
      <div class="detail-row" id="modal-speakers-row">
        <span class="detail-label">Speakers</span>
        <span class="detail-value" id="modal-speakers"></span>
      </div>
      <div class="detail-row" id="modal-desc-row">
        <span class="detail-label">About</span>
        <span class="detail-value" id="modal-desc"></span>
      </div>
      <div class="detail-row" id="modal-tags-row">
        <span class="detail-label">Topics</span>
        <div class="detail-value tags" id="modal-tags"></div>
      </div>
      <div class="modal-actions">
        <a id="modal-btn-tickets" class="btn btn-primary" href="#" target="_blank" rel="noopener">
          🎟 Get Tickets / Register
        </a>
        <a id="modal-btn-info" class="btn btn-secondary" href="#" target="_blank" rel="noopener">
          ℹ More Info
        </a>
      </div>
    </div>
  </div>
</div>

<script>
const EVENTS = {events_js};
const eventMap = {{}};
EVENTS.forEach(e => eventMap[e.id] = e);

function openModal(id) {{
  const e = eventMap[id];
  if (!e) return;

  document.getElementById('modal-header').style.background = e.color;
  document.getElementById('modal-title').innerHTML =
    e.name + (e.verified ? '<span class="verified-badge">✓ Verified</span>' : '');
  document.getElementById('modal-date').textContent = e.date;
  document.getElementById('modal-location').textContent = e.location || 'TBD';

  const ticketEl = document.getElementById('modal-ticket');
  ticketEl.textContent = e.ticket_price || 'See website';
  document.getElementById('modal-ticket-row').style.display = e.ticket_price ? '' : 'none';

  const speakersEl = document.getElementById('modal-speakers');
  if (e.speakers && e.speakers.length) {{
    const shown = e.speakers.slice(0, 6);
    const more = e.speakers.length - 6;
    speakersEl.innerHTML = shown.join(', ') + (more > 0 ? ` <em>+${{more}} more</em>` : '');
    document.getElementById('modal-speakers-row').style.display = '';
  }} else {{
    document.getElementById('modal-speakers-row').style.display = 'none';
  }}

  document.getElementById('modal-desc').textContent = e.description || '';
  document.getElementById('modal-desc-row').style.display = e.description ? '' : 'none';

  const tagsEl = document.getElementById('modal-tags');
  tagsEl.innerHTML = '';
  if (e.highlights && e.highlights.length) {{
    e.highlights.forEach(h => {{
      const span = document.createElement('span');
      span.className = 'tag';
      span.textContent = h;
      tagsEl.appendChild(span);
    }});
    document.getElementById('modal-tags-row').style.display = '';
  }} else {{
    document.getElementById('modal-tags-row').style.display = 'none';
  }}

  document.getElementById('modal-btn-tickets').href = e.url;
  document.getElementById('modal-btn-info').href = e.url;

  document.getElementById('overlay').classList.add('active');
  document.body.style.overflow = 'hidden';
}}

function closeModalDirect() {{
  document.getElementById('overlay').classList.remove('active');
  document.body.style.overflow = '';
}}

function closeModal(e) {{
  if (e.target === document.getElementById('overlay')) closeModalDirect();
}}

document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeModalDirect();
}});
</script>
</body>
</html>"""

def main():
    data = load_events()
    html = build_html(data)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    count = sum(1 for e in data["events"] if e.get("status") not in ("past","completed","archived") and e["dates"].get("start"))
    print(f"✓ Calendar built → {OUTPUT_FILE}")
    print(f"  {count} upcoming events across {len(set((datetime.date.fromisoformat(e['dates']['start']).month) for e in data['events'] if e.get('dates',{}).get('start') and e.get('status') not in ('past','completed','archived')))} months")

if __name__ == "__main__":
    main()
