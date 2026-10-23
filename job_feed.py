#!/usr/bin/env python3
"""Pull open roles from public Greenhouse / Lever / Ashby job-board APIs,
keep plausible early-career robotics/controls/embedded/mechatronics roles in
target metros, and write jobs_feed.json + jobs_feed.md.  Stdlib only.

Filtering is deliberately loose: hard drops are only defense/HVAC, wrong metro,
senior/intern titles, off-track titles, stale postings, and "3+ years required".
Everything else is kept and tagged with level_signal so the daily Claude task
makes the final call:
  title - title says new grad / entry level / Engineer I / associate ...
  body  - only the description says so
  none  - no level signal either way (still not senior, not 3+ yrs)

Usage:  python3 job_feed.py [--days 45] [--out DIR]
jobs_feed.md ends with a diagnostics section: per-stage drop counts and any
boards that failed (bad token / board moved) so they can be fixed or removed.
"""
import argparse, json, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# (ats, board_token, display name) -- tokens verified by probe on 2026-10-23.
# No public Greenhouse/Lever/Ashby board (check their careers pages directly instead):
#   Boston Dynamics, Symbotic, Aurora, Commonwealth Fusion Systems, Berkshire Grey, Vecna,
#   RightHand Robotics, Realtime Robotics, Skild AI, Mytra, K2 Space, Stoke Space, Zap Energy,
#   TAE, Viam, Hello Robot, Starship, Gatik, Monarch Tractor, Dusty Robotics, Brain Corp, Exotec.
COMPANIES = [
    # --- robotics / automation ---
    ("greenhouse", "locusrobotics", "Locus Robotics"),
    ("ashby", "gecko-robotics", "Gecko Robotics"),
    ("greenhouse", "agilityrobotics", "Agility Robotics"),
    ("ashby", "skydio", "Skydio"),
    ("greenhouse", "flyzipline", "Zipline"),
    ("lever", "dexterity", "Dexterity"),
    ("greenhouse", "figureai", "Figure"),
    ("greenhouse", "apptronik", "Apptronik"),
    ("greenhouse", "pathrobotics", "Path Robotics"),
    ("greenhouse", "formic", "Formic"),
    ("lever", "boxbot", "Boxbot"),
    ("lever", "anybotics", "ANYbotics"),
    ("ashby", "carbon-robotics", "Carbon Robotics"),
    ("lever", "picklerobot", "Pickle Robot"),
    ("ashby", "machina-labs", "Machina Labs"),
    ("lever", "brightmachines", "Bright Machines"),
    ("greenhouse", "neuralink", "Neuralink"),
    ("ashby", "standardbots", "Standard Bots"),
    ("greenhouse", "icarus", "Icarus Robotics"),
    ("ashby", "1x", "1X"),
    ("ashby", "reflexrobotics", "Reflex Robotics"),
    ("lever", "tutorintelligence", "Tutor Intelligence"),
    ("ashby", "physicalintelligence", "Physical Intelligence"),
    ("ashby", "thebotcompany", "The Bot Company"),
    ("ashby", "cobot", "Collaborative Robotics"),
    ("ashby", "dyna-robotics", "Dyna Robotics"),
    ("greenhouse", "diligentrobotics", "Diligent Robotics"),
    ("lever", "mujininc", "Mujin"),
    ("lever", "ambirobotics", "Ambi Robotics"),
    ("greenhouse", "nimblerobotics", "Nimble Robotics"),
    ("ashby", "serverobotics", "Serve Robotics"),
    ("ashby", "bedrock-robotics", "Bedrock Robotics"),
    ("lever", "field-ai", "Field AI"),
    ("ashby", "persona", "Persona AI"),
    ("ashby", "sanctuary", "Sanctuary AI"),
    ("lever", "agtonomy", "Agtonomy"),
    ("ashby", "built-robotics", "Built Robotics"),
    ("lever", "cobaltrobotics", "Cobalt Robotics"),
    ("ashby", "watney", "Watney Robotics"),
    ("lever", "robust-ai", "Robust AI"),
    ("greenhouse", "formlabs", "Formlabs"),
    ("greenhouse", "markforged", "Markforged"),
    # --- autonomy ---
    ("greenhouse", "waymo", "Waymo"),
    ("greenhouse", "nuro", "Nuro"),
    ("ashby", "applied", "Applied Intuition"),
    ("lever", "zoox", "Zoox"),
    ("greenhouse", "outrider", "Outrider"),
    ("greenhouse", "kodiak", "Kodiak Robotics"),
    ("greenhouse", "stackav", "Stack AV"),
    ("greenhouse", "maymobility", "May Mobility"),
    ("lever", "aeva", "Aeva"),
    # --- space / fusion / energy (ITAR mentions are tagged, not dropped) ---
    ("greenhouse", "spacex", "SpaceX"),
    ("greenhouse", "relativity", "Relativity Space"),
    ("greenhouse", "vardaspace", "Varda Space"),
    ("ashby", "impulse", "Impulse Space"),
    ("greenhouse", "inversionspace", "Inversion Space"),
    ("greenhouse", "astranis", "Astranis"),
    ("greenhouse", "rocketlab", "Rocket Lab"),
    ("greenhouse", "muonspace", "Muon Space"),
    ("greenhouse", "planetlabs", "Planet"),
    ("ashby", "radiant-industries", "Radiant"),
    ("ashby", "helion", "Helion"),
    ("greenhouse", "pacificfusion", "Pacific Fusion"),
]

TRACK_WORDS = re.compile(
    r"robot|controls?\b|autonom|embedded|firmware|mechatronic|motion|perception|slam|"
    r"navigation|locali[sz]ation|planning|test|integration|field|hardware|systems?\b|"
    r"electromechanical|mechanical|electrical|automation|manufacturing|software|"
    r"reliability|actuat|sensor|avionics|propulsion|gnc|guidance", re.I)
LEVEL_WORDS = re.compile(
    r"new.?grad|university grad|recent grad|entry.?level|early.?career|junior|"
    r"associate|engineer,? (i|1)\b|engineer,? level (i|1)\b|\b(i|1)\s*$|"
    r"rotational|graduate (program|engineer)|class of 202[67]|\b2027\b|"
    r"0\s*[-–to]+\s*2\s*years|1\s*[-–to]+\s*2\s*years|no (prior )?experience required", re.I)
SENIOR_WORDS = re.compile(r"senior|\bsr\.?\b|staff|principal|\blead\b|manager|director|head of|"
                          r"\bvp\b|intern(ship)?\b|co-?op\b|\bii\b|\biii\b|\biv\b|\b[2-5]\s*$", re.I)
DEFENSE_WORDS = re.compile(r"security clearance|secret clearance|ts/sci|top secret|"
                           r"defense contractor|weapons?\b|munitions?|department of defense|"
                           r"\bdod\b|hvac|starshield|missile|national security space", re.I)
NON_ENG_TITLE = re.compile(r"financ|sales|marketing|recruit|account(ing|ant)|legal|counsel|\bhr\b|people (ops|partner)|"
                           r"procurement|buyer|part.?time|clinical|customer success|business development", re.I)
ITAR_WORDS = re.compile(r"\bitar\b|export control|u\.?s\.? person", re.I)
YEARS_REQ = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:[-–]\s*\d{1,2}\s*)?(?:or more\s+)?years?"
                       r"(?:\s+of)?(?:\s+[\w/-]+){0,4}?\s+experience", re.I)
METROS = [
    ("NYC", r"(?<!, )new york|brooklyn|long island|glen cove|\bnyc\b|queens|manhattan|bronx|hoboken|"
            r"jersey city|newark|stony brook|farmingdale|hauppauge|melville|westchester|stamford"),
    ("Boston", r"boston|cambridge, ma|waltham|bedford, ma|wilmington, ma|somerville|watertown|"
               r"burlington, ma|lexington, ma|woburn|devens|billerica|marlborough|north reading|"
               r"andover|massachusetts|, ma\b"),
    ("SF Bay", r"san francisco|bay area|palo alto|mountain view|sunnyvale|san jose|oakland|"
               r"redwood city|menlo park|fremont|santa clara|berkeley|emeryville|hayward|"
               r"san carlos|foster city|burlingame|san mateo|milpitas|union city|alameda|richmond, ca"),
    ("LA", r"los angeles|el segundo|hawthorne|irvine|torrance|pasadena|santa monica|long beach|"
           r"culver city|burbank|gardena|carson|foothill ranch|van nuys|chatsworth|compton|"
           r"inglewood|orange county|costa mesa|tustin"),
    ("San Diego", r"san diego|carlsbad|poway|oceanside"),
    ("Chicago", r"chicago|evanston|naperville|schaumburg|skokie"),
    ("Seattle", r"seattle|bellevue|redmond|kirkland|everett|kent, wa|bothell|renton|tukwila|woodinville"),
]
METRO_ORDER = {m: i for i, (m, _) in enumerate(METROS)}
LEVEL_ORDER = {"title": 0, "body": 1, "none": 2}
MAX_NONE_IN_MD = 40  # keep the markdown short enough to read in one fetch


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "job-feed/1.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strip(html):
    # Greenhouse returns HTML-escaped markup, so decode entities BEFORE removing tags.
    text = unescape(unescape(html or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iso(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch(ats, token):
    """Yield dicts: title, location, url, posted(datetime|None), text, pay"""
    if ats == "greenhouse":
        data = get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        for j in data.get("jobs", []):
            pay = "; ".join(f"${p['min_cents']//100:,}-${p['max_cents']//100:,}"
                            for p in j.get("pay_input_ranges", []) if p.get("min_cents"))
            yield dict(title=j["title"], location=(j.get("location") or {}).get("name", ""),
                       url=j["absolute_url"], posted=iso(j.get("first_published") or j.get("updated_at")),
                       text=strip(j.get("content")), pay=pay)
    elif ats == "lever":
        for j in get(f"https://api.lever.co/v0/postings/{token}?mode=json"):
            c = j.get("categories") or {}
            sr = j.get("salaryRange") or {}
            pay = f"${sr['min']:,}-${sr['max']:,}" if sr.get("min") else ""
            yield dict(title=j["text"],
                       location=c.get("location", "") or "; ".join(c.get("allLocations", [])),
                       url=j["hostedUrl"], posted=iso(j.get("createdAt")),
                       text=(j.get("descriptionPlain", "") + " " +
                             " ".join(l.get("text", "") + " " + strip(l.get("content")) for l in j.get("lists", []))),
                       pay=pay)
    elif ats == "ashby":
        data = get(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true")
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            comp = (j.get("compensation") or {}).get("compensationTierSummary", "") or ""
            loc = " ; ".join([j.get("location", "") or ""] +
                             [s.get("location", "") for s in j.get("secondaryLocations", []) or []])
            yield dict(title=j["title"], location=loc, url=j["jobUrl"], posted=iso(j.get("publishedAt")),
                       text=j.get("descriptionPlain", "") or strip(j.get("descriptionHtml")), pay=comp)


def classify(job, stats):
    """Return job (with metro/level_signal/years_required/flags) or None; tally drop reasons."""
    title, text = job["title"], job["text"]
    if DEFENSE_WORDS.search(f"{title} {text}"):
        stats["defense/HVAC"] += 1; return None
    metro = next((m for m, rx in METROS if re.search(rx, job["location"], re.I)), None)
    if not metro:
        stats["outside target metros"] += 1; return None
    title_level = bool(LEVEL_WORDS.search(title))
    if SENIOR_WORDS.search(title) and not re.search(r"new.?grad|university grad|early.?career", title, re.I):
        stats["senior/intern title"] += 1; return None
    if not TRACK_WORDS.search(title) or NON_ENG_TITLE.search(title):
        stats["off-track title"] += 1; return None
    yrs = [int(y) for y in YEARS_REQ.findall(text)]
    years_required = min(yrs) if yrs else None
    if years_required is not None and years_required >= 3 and not title_level:
        stats["3+ years required"] += 1; return None
    if title_level:
        level = "title"
    elif LEVEL_WORDS.search(text):
        level = "body"
    else:
        level = "none"
    flags = []
    if ITAR_WORDS.search(text):
        flags.append("ITAR/US-person")
    if re.search(r"talent (pool|community|network)|general (interest|application)|open application", title, re.I):
        flags.append("talent pool")
    job.update(metro=metro, level_signal=level, years_required=years_required, flags=flags)
    stats["kept"] += 1
    return job


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45, help="drop postings older than this (undated are kept)")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=a.days)
    stats = {k: 0 for k in ["fetched", "older than cutoff", "defense/HVAC", "outside target metros",
                            "senior/intern title", "off-track title", "3+ years required", "kept"]}
    hits, failed, seen, board_counts = [], [], set(), []
    for ats, token, name in COMPANIES:
        try:
            jobs = list(fetch(ats, token))
        except Exception as e:  # bad token, moved board, timeout, schema change
            failed.append(f"{name} ({ats}/{token}): {type(e).__name__}: {e}")
            continue
        board_counts.append(f"{name} ({ats}): {len(jobs)}")
        for j in jobs:
            if j["url"] in seen:
                continue
            seen.add(j["url"])
            stats["fetched"] += 1
            if j["posted"] and j["posted"] < cutoff:
                stats["older than cutoff"] += 1
                continue
            j = classify(j, stats)
            if j:
                j.update(company=name, source=ats.capitalize())
                hits.append(j)
    hits.sort(key=lambda j: (LEVEL_ORDER[j["level_signal"]], METRO_ORDER[j["metro"]],
                             -(j["posted"].timestamp() if j["posted"] else 0)))
    rows = [{**{k: v for k, v in j.items() if k not in ("text", "posted")},
             "location": j["location"].strip(),
             "posted": j["posted"].date().isoformat() if j["posted"] else None,
             "snippet": j["text"][:600]} for j in hits]
    with open(f"{a.out}/jobs_feed.json", "w") as f:
        json.dump(rows, f, indent=2)

    today = now.astimezone(ET).date().isoformat()
    by_level = {lv: [r for r in rows if r["level_signal"] == lv] for lv in LEVEL_ORDER}
    headings = {"title": "Explicit entry-level in title",
                "body": "Entry-level signal in description only",
                "none": "No level signal (not senior, not 3+ yrs) - verify level"}
    with open(f"{a.out}/jobs_feed.md", "w") as f:
        f.write(f"# Job feed {today} ({len(rows)} candidates: "
                f"{len(by_level['title'])} title / {len(by_level['body'])} body / {len(by_level['none'])} none)\n\n")
        f.write(f"Generated {now.astimezone(ET):%Y-%m-%d %H:%M} ET from {len(COMPANIES) - len(failed)}"
                f"/{len(COMPANIES)} boards. Leads only - read each posting before using it.\n")
        for lv in LEVEL_ORDER:
            f.write(f"\n## {headings[lv]} ({len(by_level[lv])})\n\n")
            shown = by_level[lv] if lv != "none" else by_level[lv][:MAX_NONE_IN_MD]
            for r in shown:
                extra = []
                if r["years_required"] is not None:
                    extra.append(f"{r['years_required']}+ yrs")
                extra += r["flags"]
                f.write(f"- **{r['company']} - {r['title'].strip()}** | {r['metro']} ({r['location']}) | "
                        f"posted {r['posted'] or '?'} | {r['pay'] or 'pay not listed'}"
                        f"{' | ' + ', '.join(extra) if extra else ''}\n  {r['url']}\n")
            if not by_level[lv]:
                f.write("_none_\n")
            elif len(shown) < len(by_level[lv]):
                f.write(f"\n_{len(by_level[lv]) - len(shown)} more in jobs_feed.json (level_signal = none)._\n")
        f.write("\n## Diagnostics\n\n")
        f.write("Pipeline: " + " | ".join(f"{k}: {v}" for k, v in stats.items()) + "\n\n")
        f.write("Boards that failed (fix token or delete):\n")
        f.write("".join(f"- {x}\n" for x in failed) or "- none\n")
        f.write("\nJobs per board: " + "; ".join(board_counts) + "\n")
    print(f"{len(rows)} candidates -> jobs_feed.json / jobs_feed.md")
    print("Stats:", stats)
    if failed:
        print("\nBoards that failed (fix token or delete):", *failed, sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
