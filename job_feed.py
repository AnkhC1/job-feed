#!/usr/bin/env python3
"""Pull open roles from public Greenhouse / Lever / Ashby job-board APIs,
filter for entry-level robotics/controls/embedded roles in target metros,
and write jobs_feed.json + jobs_feed.md.  Stdlib only.

Usage:  python3 job_feed.py [--days 30] [--out DIR]
Edit COMPANIES to add/remove employers. Board tokens are best guesses;
the run prints which ones returned 404 so you can fix or delete them.
"""
import argparse, json, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

# (ats, board_token, display name)
COMPANIES = [
    ("greenhouse", "locusrobotics", "Locus Robotics"),
    ("greenhouse", "geckorobotics", "Gecko Robotics"),
    ("greenhouse", "agilityrobotics", "Agility Robotics"),
    ("greenhouse", "skydio", "Skydio"),
    ("greenhouse", "zipline", "Zipline"),
    ("greenhouse", "dexterity", "Dexterity"),
    ("greenhouse", "figureai", "Figure"),
    ("greenhouse", "apptronik", "Apptronik"),
    ("greenhouse", "aurorainnovation", "Aurora"),
    ("greenhouse", "nuro", "Nuro"),
    ("greenhouse", "pathrobotics", "Path Robotics"),
    ("greenhouse", "formic", "Formic"),
    ("greenhouse", "bearrobotics", "Bear Robotics"),
    ("greenhouse", "sarcos", "Sarcos"),
    ("greenhouse", "symbotic", "Symbotic"),
    ("greenhouse", "boxbot", "Boxbot"),
    ("greenhouse", "anybotics", "ANYbotics"),
    ("greenhouse", "carbonrobotics", "Carbon Robotics"),
    ("greenhouse", "righthandrobotics", "RightHand Robotics"),
    ("greenhouse", "vecna", "Vecna Robotics"),
    ("greenhouse", "ghostautonomy", "Ghost Autonomy"),
    ("lever", "zoox", "Zoox"),
    ("lever", "bostondynamics", "Boston Dynamics"),
    ("lever", "shield-ai", "Shield AI (defense - will be filtered)"),
    ("lever", "outrider", "Outrider"),
    ("lever", "anduril", "Anduril (defense - will be filtered)"),
    ("ashby", "standardbots", "Standard Bots"),
    ("ashby", "icarus", "Icarus Robotics"),
    ("ashby", "skild", "Skild AI"),
    ("ashby", "1x", "1X"),
    ("ashby", "reflex-robotics", "Reflex Robotics"),
    ("ashby", "mytra", "Mytra"),
    ("ashby", "tutor-intelligence", "Tutor Intelligence"),
]

TRACK_WORDS = re.compile(r"robot|controls?|autonom|embedded|firmware|mechatronic|"
                         r"motion|perception|slam|navigation|test.*(robot|system)|"
                         r"integration|field|hardware|systems? engineer|electromechanical", re.I)
LEVEL_WORDS = re.compile(r"new.?grad|university grad|recent grad|entry.?level|early career|"
                         r"associate|engineer (i|1)\b|engineer,? level (i|1)\b|"
                         r"rotational|graduate (program|engineer)|class of 202[67]|"
                         r"\b2027\b|0-2 years|0 to 2 years|1-2 years", re.I)
SENIOR_WORDS = re.compile(r"senior|sr\.?|staff|principal|lead|manager|director|head of|"
                          r"intern(ship)?\b|co-?op|\bii\b|\biii\b|\biv\b", re.I)
DEFENSE_WORDS = re.compile(r"security clearance|secret clearance|ts/sci|top secret|"
                           r"defense contractor|weapons?|munitions?|dod\b|department of defense|"
                           r"hvac|itar", re.I)
METROS = [
    ("NYC", r"new york|brooklyn|long island|glen cove|nyc|queens|manhattan|hoboken|jersey city|stony brook|farmingdale|hauppauge"),
    ("Boston", r"boston|cambridge, ma|waltham|bedford, ma|wilmington, ma|somerville|watertown, ma|burlington, ma|lexington, ma|woburn|massachusetts"),
    ("SF Bay", r"san francisco|bay area|palo alto|mountain view|sunnyvale|san jose|oakland|redwood city|menlo park|fremont|santa clara|south san francisco|berkeley"),
    ("LA", r"los angeles|el segundo|irvine|torrance|pasadena|santa monica|long beach|culver city"),
    ("San Diego", r"san diego|carlsbad"),
    ("Chicago", r"chicago|evanston|naperville"),
    ("Seattle", r"seattle|bellevue|redmond|kirkland"),
]
METRO_ORDER = {m: i for i, (m, _) in enumerate(METROS)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "job-feed/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strip(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


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
            text = strip(j.get("content"))
            pay = "; ".join(f"${p['min_cents']//100:,}-${p['max_cents']//100:,}" for p in j.get("pay_input_ranges", []) if p.get("min_cents"))
            yield dict(title=j["title"], location=(j.get("location") or {}).get("name", ""),
                       url=j["absolute_url"], posted=iso(j.get("first_published") or j.get("updated_at")),
                       text=text, pay=pay)
    elif ats == "lever":
        for j in get(f"https://api.lever.co/v0/postings/{token}?mode=json"):
            c = j.get("categories") or {}
            sr = j.get("salaryRange") or {}
            pay = f"${sr['min']:,}-${sr['max']:,}" if sr.get("min") else ""
            yield dict(title=j["text"], location=c.get("location", "") or "; ".join(c.get("allLocations", [])),
                       url=j["hostedUrl"], posted=iso(j.get("createdAt")),
                       text=j.get("descriptionPlain", "") + " " + " ".join(l.get("text", "") + " " + strip(l.get("content")) for l in j.get("lists", [])),
                       pay=pay)
    elif ats == "ashby":
        data = get(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true")
        for j in data.get("jobs", []):
            comp = (j.get("compensation") or {}).get("compensationTierSummary", "")
            yield dict(title=j["title"], location=j.get("location", "") + " " + " ".join(s.get("location", "") for s in j.get("secondaryLocations", [])),
                       url=j["jobUrl"], posted=iso(j.get("publishedAt")),
                       text=j.get("descriptionPlain", ""), pay=comp)


def classify(job):
    blob = f"{job['title']} {job['text']}"
    title = job["title"]
    if DEFENSE_WORDS.search(blob):
        return None
    metro = next((m for m, rx in METROS if re.search(rx, job["location"], re.I)), None)
    if not metro:
        return None
    if SENIOR_WORDS.search(title) and not re.search(r"new.?grad|university grad", title, re.I):
        return None
    if not TRACK_WORDS.search(title):
        return None
    if not LEVEL_WORDS.search(title) and not LEVEL_WORDS.search(job["text"][:6000]):
        return None
    yrs = re.findall(r"(\d+)\+?\s*(?:or more\s*)?years", job["text"], re.I)
    if yrs and min(int(y) for y in yrs) >= 3 and not LEVEL_WORDS.search(title):
        return None
    job["metro"] = metro
    return job


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45, help="drop postings older than this (undated are kept)")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
    hits, failed = [], []
    for ats, token, name in COMPANIES:
        try:
            jobs = list(fetch(ats, token))
        except (urllib.error.URLError, ValueError, KeyError) as e:
            failed.append(f"{name} ({ats}/{token}): {e}")
            continue
        for j in jobs:
            if j["posted"] and j["posted"] < cutoff:
                continue
            j = classify(j)
            if j:
                j.update(company=name, source=ats.capitalize())
                hits.append(j)
    hits.sort(key=lambda j: (METRO_ORDER[j["metro"]], -(j["posted"].timestamp() if j["posted"] else 0)))
    rows = [{**{k: v for k, v in j.items() if k not in ("text", "posted")},
             "posted": j["posted"].date().isoformat() if j["posted"] else None,
             "snippet": j["text"][:600]} for j in hits]
    with open(f"{a.out}/jobs_feed.json", "w") as f:
        json.dump(rows, f, indent=2)
    with open(f"{a.out}/jobs_feed.md", "w") as f:
        f.write(f"# Job feed {datetime.now().date()} ({len(rows)} candidates)\n\n")
        for r in rows:
            f.write(f"- **{r['company']} - {r['title']}** | {r['metro']} ({r['location'].strip()}) | posted {r['posted'] or '?'} | {r['pay'] or 'pay not listed'}\n  {r['url']}\n")
    print(f"{len(rows)} candidates -> jobs_feed.json / jobs_feed.md")
    if failed:
        print("\nBoards that failed (fix token or delete):", *failed, sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
