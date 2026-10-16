#!/usr/bin/env python3
"""
Homestead Events Calendar Builder
Reads events.json and generates a standalone HTML calendar with
clickable event chips that open a modal with full details + links.
"""

import json
import os
import base64
import datetime

EVENTS_FILE  = os.path.join(os.path.dirname(__file__), "../data/events.json")
OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "../calendar.html")
LOGO_FILE    = os.path.join(os.path.dirname(__file__), "../farm2table_logo_round.png")

def load_logo_b64():
    try:
        with open(LOGO_FILE, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""

# Farm2Table brand palette — red accent on dark
REGION_COLORS = {
    "Southeast":  "#c0392b",
    "South":      "#e67e22",
    "Midwest":    "#2980b9",
    "Northwest":  "#8e44ad",
    "Northeast":  "#c0392b",
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

        ticket_url = e.get("ticket_url", url)

        obj = {
            "id": e["id"],
            "name": e["name"],
            "color": color,
            "date": ("Next dates coming soon — last held " + format_date_range(e)) if e.get("status") in ("past", "completed", "archived") else format_date_range(e),
            "location": location_str,
            "description": e.get("description", ""),
            "speakers": speakers,
            "highlights": highlights,
            "ticket_price": ticket,
            "url": url,
            "ticket_url": ticket_url,
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
    events     = events_data["events"]
    last_updated = events_data["meta"].get("last_updated", "")
    months     = build_calendar_months(events)
    logo_b64   = load_logo_b64()
    logo_src   = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""

    legend_html = "".join(
        f'<span class="legend-item"><span class="legend-dot" style="background:{c};"></span><span>{r}</span></span>'
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

    awaiting = [e for e in events if e.get("status") in ("past", "completed", "archived") and not e.get("recurrence")]
    if awaiting:
        chips = "".join(
            f'<button class="chip" style="background:{event_chip_color(e)};opacity:.7;margin:4px;padding:6px 10px;border:0;color:#fff;cursor:pointer;border-radius:4px;" onclick="openModal(\'{e["id"]}\')">{e["name"]}</button>'
            for e in awaiting)
        months_html += f'''
        <div class="month-block">
          <h2 class="month-title">Awaiting 2027 Dates</h2>
          <p style="margin:0 0 8px;opacity:.8;">These events have wrapped for 2026. We'll post new dates as soon as they're announced.</p>
          <div>{chips}</div>
        </div>'''

    events_js  = modal_data(events)
    logo_html  = f'<img src="{logo_src}" class="header-logo" alt="The Farm2Table Show">' if logo_src else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Homestead Events Calendar 2026 — The Farm2Table Show</title>

<!-- Open Graph / Social Preview -->
<meta property="og:type"        content="website">
<meta property="og:url"         content="https://homestead-events-calendar.netlify.app/calendar.html">
<meta property="og:title"       content="2026 Homestead Events Calendar — The Farm2Table Show">
<meta property="og:description" content="14 verified homestead conferences, expos & festivals across America. Click any event for dates, speakers, ticket prices & more.">
<meta property="og:image"       content="https://homestead-events-calendar.netlify.app/og-preview.jpg">
<meta property="og:image:width"  content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name"   content="The Farm2Table Show">

<!-- Twitter / X Card -->
<meta name="twitter:card"        content="summary_large_image">
<meta name="twitter:site"        content="@TF2TDS">
<meta name="twitter:title"       content="2026 Homestead Events Calendar — The Farm2Table Show">
<meta name="twitter:description" content="14 verified homestead conferences, expos & festivals across America. Click any event for dates, speakers, ticket prices & more.">
<meta name="twitter:image"       content="https://homestead-events-calendar.netlify.app/og-preview.jpg">
<style>
  :root {{
    --red:    #cc1100;
    --red2:   #a30e00;
    --black:  #0d0d0d;
    --dark:   #1a1a1a;
    --cream:  #f5f0e8;
    --card:   #ffffff;
    --border: #ddd;
    --text:   #1a1a1a;
  }}
  @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Georgia&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Georgia, serif; background: var(--cream); color: var(--text); }}

  /* ── HEADER ── */
  header {{
    background: var(--black);
    color: white;
    padding: 0;
    border-bottom: 4px solid var(--red);
  }}
  .header-inner {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 18px 24px;
    display: flex;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
  }}
  .header-logo {{
    width: 80px;
    height: 80px;
    object-fit: contain;
    flex-shrink: 0;
  }}
  .header-text {{ flex: 1; }}
  .header-eyebrow {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--red);
    margin-bottom: 4px;
  }}
  .header-title {{
    font-family: 'Oswald', sans-serif;
    font-size: 1.9rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: white;
    line-height: 1.1;
  }}
  .header-title span {{ color: var(--red); }}
  .header-sub {{
    font-size: 0.8rem;
    color: #999;
    margin-top: 5px;
    font-family: sans-serif;
  }}
  .header-right {{
    text-align: right;
    font-family: sans-serif;
    font-size: 0.75rem;
    color: #777;
  }}
  .header-right strong {{
    display: block;
    font-size: 1.1rem;
    color: white;
    font-family: 'Oswald', sans-serif;
    letter-spacing: 1px;
  }}

  /* ── RED STRIPE ── */
  .stripe {{
    background: var(--red);
    padding: 7px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .stripe-tagline {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.78rem;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: white;
  }}

  /* ── LEGEND ── */
  .legend {{
    background: var(--dark);
    padding: 9px 24px;
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: center;
    border-bottom: 1px solid #333;
  }}
  .legend-label {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #888;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .legend-item span:last-child {{
    font-family: sans-serif;
    font-size: 0.75rem;
    color: #ccc;
  }}

  /* ── MAIN ── */
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 60px; }}

  /* ── MONTH ── */
  .month-block {{ margin-bottom: 52px; }}
  .month-title {{
    font-family: 'Oswald', sans-serif;
    font-size: 1.4rem;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--black);
    padding-bottom: 8px;
    margin-bottom: 12px;
    border-bottom: 3px solid var(--red);
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .month-title::before {{
    content: '';
    display: inline-block;
    width: 6px;
    height: 22px;
    background: var(--red);
    border-radius: 2px;
  }}

  /* ── CALENDAR GRID ── */
  .cal-grid {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
    background: #c8c0b0;
    border: 2px solid var(--black);
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  }}
  .dow {{
    background: var(--black);
    color: white;
    text-align: center;
    font-family: 'Oswald', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 7px 2px;
  }}
  .day {{
    background: var(--card);
    min-height: 95px;
    padding: 6px 5px 5px;
    vertical-align: top;
  }}
  .day.empty {{ background: #ece8e0; }}
  .day.today {{ background: #fff5f5; border-left: 3px solid var(--red); }}
  .day-num {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.78rem;
    color: #aaa;
    display: block;
    margin-bottom: 4px;
  }}
  .day.today .day-num {{ color: var(--red); font-weight: 600; }}

  /* ── CHIPS ── */
  .chip {{
    display: block;
    font-size: 0.68rem;
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
    transition: filter 0.15s, transform 0.1s;
    font-weight: 600;
    letter-spacing: 0.2px;
  }}
  .chip:hover {{ filter: brightness(1.15); transform: translateY(-1px); }}
  .chip.continuation {{ height: 4px; padding: 0; border-radius: 0; cursor: pointer; margin-bottom: 1px; }}

  /* ── MODAL ── */
  .overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.72);
    z-index: 100;
    justify-content: center;
    align-items: flex-start;
    padding: 40px 16px;
    overflow-y: auto;
  }}
  .overlay.active {{ display: flex; }}
  .modal {{
    background: var(--card);
    border-radius: 8px;
    max-width: 580px;
    width: 100%;
    box-shadow: 0 12px 48px rgba(0,0,0,0.4);
    overflow: hidden;
    position: relative;
    border-top: 5px solid var(--red);
  }}
  .modal-header {{
    background: var(--black);
    padding: 20px 24px 16px;
    color: white;
  }}
  .modal-logo-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }}
  .modal-logo {{
    width: 36px;
    height: 36px;
    object-fit: contain;
    opacity: 0.9;
  }}
  .modal-brand {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--red);
  }}
  .modal-header h2 {{
    font-family: 'Oswald', sans-serif;
    font-size: 1.2rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    line-height: 1.3;
    color: white;
  }}
  .event-date {{
    font-size: 0.83rem;
    color: #bbb;
    margin-top: 5px;
    font-family: sans-serif;
  }}
  .event-color-bar {{
    height: 4px;
    width: 100%;
  }}
  .modal-body {{ padding: 20px 24px 24px; }}
  .modal-close {{
    position: absolute;
    top: 12px; right: 14px;
    background: none; border: none;
    color: #888; font-size: 1.3rem;
    cursor: pointer;
    line-height: 1;
    transition: color 0.15s;
  }}
  .modal-close:hover {{ color: white; }}

  .detail-row {{
    display: flex;
    gap: 10px;
    margin-bottom: 13px;
    font-size: 0.88rem;
    align-items: flex-start;
  }}
  .detail-label {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #999;
    min-width: 72px;
    padding-top: 3px;
  }}
  .detail-value {{ color: #222; line-height: 1.55; }}

  .tags {{ display: flex; flex-wrap: wrap; gap: 5px; }}
  .tag {{
    background: #f0ece4;
    border-radius: 3px;
    padding: 3px 8px;
    font-size: 0.7rem;
    font-family: sans-serif;
    color: #555;
    border: 1px solid #ddd;
  }}

  .modal-actions {{
    display: flex;
    gap: 10px;
    margin-top: 22px;
    flex-wrap: wrap;
    padding-top: 18px;
    border-top: 1px solid #eee;
  }}
  .btn {{
    display: inline-block;
    padding: 11px 22px;
    border-radius: 4px;
    text-decoration: none;
    font-family: 'Oswald', sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    transition: opacity 0.15s, transform 0.1s;
  }}
  .btn:hover {{ opacity: 0.88; transform: translateY(-1px); }}
  .btn-primary {{ background: var(--red); color: white; }}
  .btn-secondary {{ background: var(--black); color: white; }}

  .date-note {{
    font-size: 0.78rem; color: #aaa; font-style: italic; font-family: sans-serif;
  }}
  .verified-badge {{
    display: inline-block;
    font-family: sans-serif;
    font-size: 0.65rem;
    background: rgba(204,17,0,0.12);
    color: var(--red);
    border: 1px solid rgba(204,17,0,0.3);
    border-radius: 3px;
    padding: 2px 6px;
    margin-left: 8px;
    vertical-align: middle;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  /* ── FOOTER ── */
  footer {{
    background: var(--black);
    border-top: 4px solid var(--red);
    padding: 24px;
    text-align: center;
    color: #666;
    font-family: sans-serif;
    font-size: 0.78rem;
  }}
  footer a {{ color: var(--red); text-decoration: none; }}
  footer .footer-logo {{ width: 50px; height: 50px; object-fit: contain; opacity: 0.7; margin-bottom: 10px; }}

  @media (max-width: 640px) {{
    .header-logo {{ width: 55px; height: 55px; }}
    .header-title {{ font-size: 1.3rem; }}
    .cal-grid {{ font-size: 0.7rem; }}
    .day {{ min-height: 64px; }}
    .chip {{ font-size: 0.6rem; padding: 2px 3px; }}
  }}
</style>
</head>
<body>

<header>
  <div class="header-inner">
    {logo_html}
    <div class="header-text">
      <div class="header-eyebrow">The Farm2Table Show Presents</div>
      <div class="header-title">2026 Homestead Events <span>Calendar</span></div>
      <div class="header-sub">Conferences · Expos · Festivals · Summits across America</div>
    </div>
    <div class="header-right">
      <strong>{len([e for e in events if e.get('status') not in ('past','completed','archived') and e['dates'].get('start')])} Events</strong>
      Updated {last_updated}
    </div>
  </div>
</header>

<div class="stripe">
  <span class="stripe-tagline">Know Where the Community Gathers · Click Any Event for Details & Tickets</span>
</div>

<div class="legend">
  <span class="legend-label">Region —</span>
  {legend_html}
</div>

<main>
{months_html}
</main>

<footer>
  {logo_html.replace('class="header-logo"', 'class="footer-logo"') if logo_html else ""}
  <div>© 2026 The Farm2Table Show &nbsp;·&nbsp; <a href="https://t.me/farm2tableinsiders">Farm2Table Insiders</a></div>
  <div style="margin-top:6px;">Calendar data updated weekly. Verify details at official event websites before purchasing tickets.</div>
</footer>

<!-- Modal Overlay -->
<div class="overlay" id="overlay" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="event-color-bar" id="modal-colorbar"></div>
    <div class="modal-header">
      <button class="modal-close" onclick="closeModalDirect()">✕</button>
      <div class="modal-logo-row">
        {logo_html.replace('class="header-logo"','class="modal-logo"') if logo_html else ""}
        <span class="modal-brand">The Farm2Table Show — Event Guide</span>
      </div>
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

  document.getElementById('modal-colorbar').style.background = e.color;
  document.getElementById('modal-title').innerHTML =
    e.name + (e.verified ? '<span class="verified-badge">✓ Verified</span>' : '');
  document.getElementById('modal-date').innerHTML = e.date;
  document.getElementById('modal-location').textContent = e.location || 'TBD';

  const ticketEl = document.getElementById('modal-ticket');
  ticketEl.textContent = e.ticket_price || 'See website';
  document.getElementById('modal-ticket-row').style.display = '';

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

  document.getElementById('modal-btn-tickets').href = e.ticket_url || e.url;
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
