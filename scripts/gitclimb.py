#!/usr/bin/env python3
"""GitClimb: GitHub's contribution calendar as an animated climbing wall.

Python 3.11+ standard library only. No external services or SVG scripts.
Demo data is opt-in and always labelled. Failed API calls never publish a demo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import random
import sys
import urllib.error
import urllib.request

QUERY = """query($login:String!) {
  user(login:$login) { contributionsCollection {
    contributionCalendar { totalContributions weeks {
      contributionDays { date weekday contributionCount }
    } }
  } }
}"""
THEMES = {
    "light": dict(bg="#f4faf6", wall="#e7f2eb", panel="#deebe2", ink="#24483e",
                  muted="#627c70", mint="#63bfa1", pale="#b7e5d0", line="#c9ded1",
                  hole="#cad9cf", cream="#fffdf7", lavender="#b3a2d4", peach="#eeb39b"),
    "dark": dict(bg="#172b26", wall="#203a31", panel="#274339", ink="#e6f7ee",
                 muted="#a8c6b7", mint="#89d7b8", pale="#3a705c", line="#3b5b4c",
                 hole="#345347", cream="#f3f3da", lavender="#c8b6ed", peach="#f0b8a2"),
}


def fetch_calendar(username: str, token: str) -> dict:
    if not token:
        raise ValueError("GITHUB_TOKEN is required for live data. Use --demo only for a labelled preview.")
    req = urllib.request.Request("https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": username}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "GitClimb/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"GitHub API returned HTTP {exc.code}; check token access. Existing wall is preserved.") from None
    if data.get("errors"):
        messages = "; ".join(e.get("message", "GraphQL error") for e in data["errors"])
        raise ValueError(f"GitHub GraphQL: {messages}")
    user = data.get("data", {}).get("user")
    if not user:
        raise ValueError(f"GitHub user not found: {username}")
    return user["contributionsCollection"]["contributionCalendar"]


def demo_calendar() -> dict:
    rng = random.Random(42)
    start = dt.date(2025, 10, 5)
    weeks = []
    for w in range(53):
        days = []
        for r in range(7):
            n = rng.choice([0, 0, 1, 2, 3, 5, 8, 12])
            # A connected demonstration route; never used in production.
            if r == max(0, 6 - w // 8):
                n = max(1, n)
            days.append(dict(date=(start + dt.timedelta(days=7*w+r)).isoformat(),
                             weekday=r, contributionCount=n))
        weeks.append({"contributionDays": days})
    return dict(weeks=weeks, totalContributions=sum(d["contributionCount"]
                for w in weeks for d in w["contributionDays"]))


def normalize(calendar: dict) -> list[dict]:
    weeks = calendar.get("weeks")
    if not isinstance(weeks, list) or not 1 <= len(weeks) <= 54:
        raise ValueError("Calendar must contain 1–54 weeks.")
    cells = []
    dates = set()
    for col, week in enumerate(weeks):
        rows = set()
        for day in week.get("contributionDays", []):
            date = dt.date.fromisoformat(day["date"])
            row, count = day["weekday"], day["contributionCount"]
            if type(row) is not int or row not in range(7) or row in rows:
                raise ValueError("Invalid or duplicate weekday in a week.")
            if type(count) is not int or count < 0 or date in dates:
                raise ValueError("Invalid count or duplicate date.")
            if (date.weekday()+1) % 7 != row:
                raise ValueError("Date does not match its Sunday-based weekday.")
            rows.add(row)
            dates.add(date)
            cells.append(dict(col=col, row=row, count=count, date=date.isoformat()))
    if not cells:
        raise ValueError("Empty calendar data.")
    return cells


def find_route(cells: list[dict]) -> list[dict]:
    """Longest forward route with a bounded reach, using active holds only.

    Columns stay chronological; progress toward the top-right breaks length ties. If empty weeks
    split the wall, choose one connected route rather than inventing bridging holds.
    """
    active = sorted((c for c in cells if c["count"] > 0), key=lambda c:(c["col"], -c["row"]))
    if not active:
        return []
    scores, parents = [], []
    max_col = max(c['col'] for c in cells)
    one_column = len({c['col'] for c in active}) == 1
    for i, c in enumerate(active):
        ideal_row = 6 * (1 - c['col'] / max(1, max_col))
        quality = -abs(c['row'] - ideal_row)
        score, parent = (1, quality), None
        for j in range(i):
            p = active[j]
            dx, dy = c["col"]-p["col"], c["row"]-p["row"]
            # Same-column moves can go upward; forward moves may traverse sideways.
            if (dx == 0 and (not one_column or dy >= 0)) or dx > 3 or math.hypot(dx, dy) > 3.1:
                continue
            candidate = (scores[j][0]+1, scores[j][1]+quality)
            if candidate > score:
                score, parent = candidate, j
        scores.append(score)
        parents.append(parent)
    i = max(range(len(active)), key=lambda k:(scores[k], active[k]["col"]))
    route = []
    while i is not None:
        route.append(active[i])
        i = parents[i]
    return route[::-1]


def svg_text(x, y, text, size=14, fill="#24483e", weight=400, extra=""):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" {extra}>{html.escape(str(text))}</text>')


def hold(x, y, color, size=6, rotation=0, title=""):
    # All holds are the same size. Shape/colour are decorative, not count scales.
    return (f'<g transform="translate({x:.2f} {y:.2f}) rotate({rotation})">'
            f'<title>{html.escape(title)}</title>'
            f'<path d="M {-size} 0 Q {-size} {-size} 0 {-size+1} '
            f'Q {size+3} {-size+1} {size} 2 Q 2 {size+2} {-size} 0Z" '
            f'fill="{color}"/><path d="M -3 -2 Q 0 -4 3 -2" '
            f'fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="1.2"/>'
            '<circle cx="1" cy="0" r="1" fill="#24483e" opacity=".45"/></g>')


def animation_tag(attribute: str, values: list[str], times: list[float], duration: float) -> str:
    return (f'<animate attributeName="{attribute}" values="{";".join(values)}" '
            f'keyTimes="{";".join(f"{v:.6f}" for v in times)}" dur="{duration:.2f}s" '
            'repeatCount="indefinite" calcMode="linear"/>')


def render_wall(calendar: dict, username: str, theme="light", demo=False) -> tuple[str, list[dict]]:
    t = THEMES[theme]
    cells = normalize(calendar)
    route = find_route(cells)
    cols = len(calendar["weeks"])
    pitch = min(19, 846 / max(1, cols-1))
    ox, oy, row_pitch = 60, 145, 24
    def pos(c):
        return (ox+c["col"]*pitch, oy+c["row"]*row_pitch)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 400" role="img" aria-labelledby="title desc">',
           f'<title id="title">{html.escape(username)} — GitClimb</title>',
           '<desc id="desc">Contribution dates become equal-size climbing holds. A climber follows a connected route through active dates. Empty dates are bolt holes.</desc>',
           '<style>text{font-family:"Arial Rounded MT Bold",Nunito,"Trebuchet MS",sans-serif} '
           '@media(prefers-reduced-motion:reduce){.motion{display:none}}</style>',
           f'<rect width="960" height="400" rx="24" fill="{t["bg"]}"/>',
           svg_text(34, 43, "THE WALL", 12, t["muted"], 700, 'letter-spacing="2"'),
           svg_text(34, 77, "GitClimb", 29, t["ink"], 700),
           svg_text(208, 76, "A little progress. A new route.", 14, t["muted"]),
           f'<rect x="726" y="29" width="202" height="35" rx="17" fill="{t["pale"]}"/>',
           svg_text(827, 51, "sample data · preview" if demo else "@"+username, 12, t["ink"], 700, 'text-anchor="middle"'),
           f'<rect x="28" y="102" width="904" height="230" rx="18" fill="{t["wall"]}"/>',
           f'<path d="M 235 102 L 292 332 M 585 102 L 525 332 M 780 102 L 854 332" stroke="{t["panel"]}" stroke-width="2"/>']
    months = set()
    for c in cells:
        x, y = pos(c)
        date = dt.date.fromisoformat(c["date"])
        if date.day <= 7 and (date.year, date.month) not in months:
            months.add((date.year, date.month))
            out.append(svg_text(x, 124, date.strftime("%b"), 10, t["muted"]))
        if c["count"]:
            color = [t["mint"], t["lavender"], t["peach"]][(c["col"]+c["row"]) % 3]
            out.append(hold(x,y,color,rotation=((c["col"]*7+c["row"]*11)%36)-18,
                            title=f'{c["date"]}: {c["count"]} contributions'))
        else:
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.8" fill="{t["hole"]}"><title>{c["date"]}: 0 contributions</title></circle>')
    if route:
        points = [pos(c) for c in route]
        d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x,y in points)
        out.append(f'<path d="{d}" fill="none" stroke="{t["mint"]}" stroke-width="1.6" stroke-dasharray="3 5" opacity=".55"/>')
        # Poses progress one reachable hold at a time; hands lead, body follows.
        # The off hand and feet smear the wall, as in indoor climbing.
        states=[]
        for i,(x,y) in enumerate(points):
            previous=points[max(0,i-1)]
            if i:
                states.append((previous[0]-5,previous[1]+20,x,y))
            states.append((x-5,y+20,x,y))
        if len(states)==1:
            states.append(states[0])
        states.append(states[-1])
        times=[i/(len(states)-1)*.93 for i in range(len(states))]
        states.append(states[0]); times.append(1.0)
        duration=max(8,len(points)*.9)
        # Hide reset instead of traversing empty gaps back to the start.
        def group_motion():
            return (f'<animate attributeName="opacity" values="1;0;0;1" keyTimes="0;.93;.999;1" calcMode="discrete" dur="{duration:.2f}s" repeatCount="indefinite"/>')
        out.append('<g class="motion">'+group_motion())
        bx,by,_,_=states[0]
        values=[f'{a:.2f} {b:.2f}' for a,b,_,_ in states]
        out.append(f'<g transform="translate({bx:.2f} {by:.2f})"><animateTransform attributeName="transform" type="translate" values="{";".join(values)}" keyTimes="{";".join(f"{v:.6f}" for v in times)}" dur="{duration:.2f}s" repeatCount="indefinite"/>')
        out.extend([
            '<path d="M -3 9 L -10 20 L -15 18 M 4 9 L 11 17 L 9 24" fill="none" stroke="#37594c" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>',
            '<path d="M -5 0 L -13 -8 L -12 -17" fill="none" stroke="#dca88c" stroke-width="3.5" stroke-linecap="round"/>',
            f'<rect x="-6" y="-4" width="13" height="16" rx="5" fill="{t["lavender"]}"/>',
            '<circle cy="-12" r="5.5" fill="#eac0a2"/><path d="M -5 -12 Q -7 -23 4 -18 Q 8 -15 5 -10 L 2 -16Z" fill="#4b3b35"/><circle cx="6" cy="-16" r="3" fill="#4b3b35"/>',
            f'<ellipse cx="0" cy="9" rx="7" ry="2" fill="{t["mint"]}"/>',
            '<path d="M -15 18 L -18 18 M 9 24 L 13 24" stroke="#243c32" stroke-width="3" stroke-linecap="round"/>',
            '</g>'])
        # Separate arm in wall coordinates ensures hand contacts the selected hold.
        paths=[]
        for a,b,x,y in states:
            paths.append(f'M {a+5:.2f} {b-1:.2f} Q {a+11:.2f} {(b+y)/2:.2f} {x:.2f} {y:.2f}')
        out.append(f'<path d="{paths[0]}" fill="none" stroke="#dca88c" stroke-width="3.5" stroke-linecap="round">'+animation_tag("d",paths,times,duration)+'</path></g>')
    else:
        out.append(svg_text(480, 219, "A fresh wall. Your next contribution places the first hold.", 15,t["muted"],extra='text-anchor="middle"'))
    out.append(svg_text(34, 361, "equal-size holds · active contribution days", 12,t["muted"]))
    out.append(svg_text(926,361,f'{len(route)} holds on this route',12,t["muted"],extra='text-anchor="end"'))
    note = "Design preview — sample activity, not Inno’s contribution history." if demo else f'{cells[0]["date"]} → {cells[-1]["date"]} · public activity visible to the workflow token'
    out.append(svg_text(34, 384, note,10,t["muted"]))
    out.append('</svg>')
    return "\n".join(out), route


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--username',default='Innoffline')
    source=p.add_mutually_exclusive_group()
    source.add_argument('--demo',action='store_true')
    source.add_argument('--calendar',type=Path,help='Local GitHub contributionCalendar JSON')
    p.add_argument('--output',type=Path,default=Path('dist'))
    args=p.parse_args()
    try:
        calendar=demo_calendar() if args.demo else (json.loads(args.calendar.read_text()) if args.calendar else fetch_calendar(args.username,os.environ.get('GITHUB_TOKEN','')))
        # Validate both outputs before writing any bytes.
        rendered=[render_wall(calendar,args.username,theme,args.demo)[0] for theme in THEMES]
        args.output.mkdir(parents=True,exist_ok=True)
        for name,svg in zip(['climb.svg','climb-dark.svg'],rendered):
            (args.output/name).write_text(svg,encoding='utf-8')
        print(f'Generated two walls in {args.output}. Demo: {args.demo}.')
    except (ValueError,KeyError,TypeError, OSError,urllib.error.URLError) as exc:
        print(f'GitClimb failed: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
