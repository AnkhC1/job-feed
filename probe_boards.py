#!/usr/bin/env python3
"""One-off: find working Greenhouse/Lever/Ashby board tokens for companies by
trying slug variants. Writes probe_results.md. Stdlib only."""
import json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

NAMES = {
    # name: extra explicit slugs to try
    "Gecko Robotics": ["gecko"], "Skydio": [], "Zipline": ["flyzipline"], "Dexterity": ["dexterityai"],
    "Bear Robotics": [], "Symbotic": [], "Boxbot": [], "ANYbotics": [], "Carbon Robotics": ["carbonautonomous"],
    "RightHand Robotics": ["righthand"], "Vecna Robotics": [], "Berkshire Grey": ["bg"], "Pickle Robot": ["picklerobotcompany", "pickle"],
    "Realtime Robotics": ["rtr"], "Machina Labs": ["machina"], "Bright Machines": [], "Boston Dynamics": ["bdi"],
    "Icarus Robotics": ["icarusrobotics"], "Skild AI": ["skildai"], "Reflex Robotics": ["reflex"], "Mytra": ["mytra-ai"],
    "Tutor Intelligence": ["tutorintelligence", "tutor"], "The Bot Company": ["botcompany", "bot-co"],
    "Collaborative Robotics": ["cobot", "co-bot", "collabrobotics"], "Aurora": ["aurora", "aurora-innovation", "auroratech"],
    "Applied Intuition": [], "Outrider": ["outrider-ai"], "Varda Space": ["varda", "vardaspace", "varda-space-industries"],
    "Impulse Space": ["impulse"], "Commonwealth Fusion Systems": ["cfs", "commonwealthfusion", "cfs-energy"],
    "Helion": ["helion", "helionfusion"], "K2 Space": ["k2", "k2-space-corporation"], "Apex Space": ["apexspace", "apex-space-inc"],
    "Inversion Space": ["inversionspace"],
    # new candidates
    "Viam": [], "Nanotronics": [], "Hello Robot": [], "Diligent Robotics": [], "Mujin": [], "Plus One Robotics": [],
    "Ambi Robotics": [], "Nimble Robotics": ["nimble"], "Chef Robotics": [], "Miso Robotics": [], "Serve Robotics": [],
    "Starship Technologies": ["starship"], "Kodiak Robotics": ["kodiak"], "Gatik": [], "Stack AV": [], "May Mobility": [],
    "Monarch Tractor": [], "Bedrock Robotics": [], "Field AI": [], "Persona AI": [], "Sanctuary AI": [], "Glid": [],
    "Astranis": [], "Pacific Fusion": [], "Zap Energy": [], "TAE Technologies": ["tae"], "Avalanche Energy": [],
    "Rocket Lab": [], "Stoke Space": [], "Radiant Industries": ["radiant", "radiantnuclear"], "Muon Space": [],
    "Planet Labs": ["planet"], "Hermeus": [], "Firestorm Labs": [], "Electric Sheep Robotics": ["electricsheep"],
    "Simbe Robotics": ["simbe"], "Brain Corp": ["braincorp"], "Agtonomy": [], "Formlabs": [], "Markforged": [],
    "Desktop Metal": [], "Shape Robotics": [], "Built Robotics": [], "Canvas Construction": ["canvas"],
    "Dusty Robotics": [], "Cobalt Robotics": [], "Knightscope": [], "Saildrone": [], "Hyundai Boston Dynamics AI Institute": ["theaiinstitute", "rai-institute", "raiinstitute"],
    "Anyware Robotics": [], "Watney Robotics": [], "Robust AI": ["robustai"], "Covariant": [], "Agile Robots": [],
    "Exotec": [], "GreyOrange": [], "Ati Motors": [], "Seegrid": [], "Ouster": [], "Aeva": [], "Luminar": [],
}


def slugs(name, extra):
    words = re.sub(r"[^a-z0-9 ]", "", name.lower()).split()
    core = [w for w in words if w not in ("technologies", "industries", "inc", "the")]
    out = ["".join(words), "-".join(words), "".join(core), "-".join(core), words[0]] + extra
    base = "".join(core)
    out += [base + s for s in ("inc", "hq", "careers", "jobs", "co")] + ["join" + base, "fly" + base]
    seen, res = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s); res.append(s)
    return res


URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}


def probe(args):
    name, ats, slug = args
    try:
        req = urllib.request.Request(URLS[ats].format(slug), headers={"User-Agent": "job-feed-probe/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        n = len(data) if isinstance(data, list) else len(data.get("jobs", []))
        if ats == "lever" and n == 0:
            return None  # lever returns [] for nonexistent boards sometimes; treat as miss
        return (name, ats, slug, n)
    except Exception:
        return None


tasks = [(n, ats, s) for n, ex in NAMES.items() for s in slugs(n, ex) for ats in URLS]
with ThreadPoolExecutor(24) as pool:
    hits = [h for h in pool.map(probe, tasks) if h]

found = {}
for name, ats, slug, n in hits:
    found.setdefault(name, []).append((ats, slug, n))
with open("probe_results.md", "w") as f:
    f.write(f"# Board probe ({len(tasks)} requests)\n\n## Found\n")
    for name in NAMES:
        if name in found:
            f.write(f"- {name}: " + "; ".join(f"{a}/{s} ({n} jobs)" for a, s, n in found[name]) + "\n")
    f.write("\n## Not found on Greenhouse/Lever/Ashby\n")
    f.write(", ".join(n for n in NAMES if n not in found) + "\n")
print(open("probe_results.md").read())
