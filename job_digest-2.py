"""
Daily Job Digest — v3
Outputs a clean, ranked JSON of apply-links (no email). Pulls from two kinds
of sources:

  1. Target companies you're actually interested in (Cred, Razorpay, Groww,
     Freshworks, etc.) — fetched directly from each company's own public ATS
     API (Greenhouse or Lever). This covers IN-OFFICE and hybrid roles, not
     just remote, and is why this list matters more than the remote boards.
  2. RemoteOK + Remotive — kept as a supplementary remote-only source.

WHY THIS IS SAFE (no scraping/ToS risk):
Greenhouse and Lever both publish official, public, unauthenticated JSON
APIs for any company's job board — this is the same data their own careers
page loads, just structured. No login, no HTML parsing, no rate-limit abuse.
Naukri/Instahyre have no such public API, so they're still not included —
don't add scraping for those, it's the one thing worth not automating.

IMPORTANT — VERIFY THE COMPANY SLUGS BELOW:
I've filled TARGET_COMPANIES with my best guesses at each company's
Greenhouse/Lever board slug. Some are confirmed, most are educated guesses —
many large Indian companies (Flipkart, Axis Bank, Bajaj Finserv, Zoho) run
their own custom career portals instead of Greenhouse/Lever, so they simply
won't return anything here, silently and harmlessly. To find a company's
real slug: open their careers page, and if it redirects to something like
boards.greenhouse.io/<slug> or jobs.lever.co/<slug>, that's your slug —
add it to the relevant list below.

DEPLOY: same as before — Replit, add `requests` to requirements.txt, run
python job_digest.py, then set up a Scheduled Deployment for daily runs.
"""

import requests
import json
from datetime import datetime, timezone

# ---- Relevance scoring (same logic as before) ----
PROFILE_KEYWORDS = {
    "sql": 3, "python": 2, "machine learning": 3, "ml": 1,
    "data analyst": 3, "business analyst": 3, "analytics": 2,
    "bi ": 2, "business intelligence": 2, "power bi": 2,
    "decision scien": 3, "product analyst": 2, "credit risk": 3,
    "risk analyst": 3, "lending": 2, "fintech": 2, "data scien": 2,
    "etl": 1, "looker": 1, "tableau": 1,
}

TITLE_MUST_CONTAIN = [
    "analyst", "analytics", "data scien", "decision scien", "bi ",
    "business intelligence", "risk", "sql", "quant",
]

DEPRIORITIZE_KEYWORDS = [
    "senior ", "staff ", "principal ", "director ", " vp ", "lead ",
    "5+ years", "7+ years", "10+ years",
]

# Applies only to the RemoteOK/Remotive (remote-board) source — jobs
# explicitly restricted to a non-India region get dropped from those.
LOCATION_BLOCK = [
    "usa only", "us only", "u.s. only", "uk only", "united kingdom only",
    "canada only", "eu only", "europe only", "australia only",
    "latam only", "emea only",
]

MIN_SCORE_TO_INCLUDE = 4
DIGEST_CAP = 40

# ---- Target companies — VERIFY/EDIT these slugs, see note above ----
TARGET_COMPANIES = {
    "greenhouse": [
        "postman",       # confirmed
        "razorpay",
        "cred",
        "groww",
        "navi",
        "freshworks",
        "chargebee",
        "clevertap",
        "moengage",
        "fractalanalytics",
        "tredence",
    ],
    "lever": [
        "zomato",
        "swiggy",
        "meesho",
        "sliceit",
        "jupiter",
        "latentview",
    ],
}

REMOTEOK_TAGS = "data,python,sql,analyst,bi,analytics"
REMOTIVE_SEARCH_TERMS = [
    "data analyst", "business analyst", "sql analyst",
    "risk analyst", "decision science", "credit risk",
]


def title_matches(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TITLE_MUST_CONTAIN)


def location_allowed(location: str) -> bool:
    loc = (location or "").strip().lower()
    return not any(blocked in loc for blocked in LOCATION_BLOCK)


def score_job(title, description, tags):
    text = f"{title} {description} {' '.join(tags)}".lower()
    score = 0
    for kw, weight in PROFILE_KEYWORDS.items():
        if kw in text:
            score += weight
    for kw in DEPRIORITIZE_KEYWORDS:
        if kw in text:
            score -= 2
    return score


# ---- Target-company ATS fetchers ----

def fetch_greenhouse(board_token):
    jobs = []
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true",
            timeout=15,
        )
        if resp.status_code != 200:
            return jobs  # slug likely wrong or company doesn't use Greenhouse — skip silently
        data = resp.json()
        for job in data.get("jobs", []):
            jobs.append({
                "source": f"Greenhouse:{board_token}",
                "company": board_token,
                "title": job.get("title", ""),
                "description": job.get("content", ""),
                "tags": [],
                "url": job.get("absolute_url", ""),
                "location": (job.get("location") or {}).get("name", ""),
            })
    except Exception as e:
        print(f"Greenhouse fetch failed for '{board_token}': {e}")
    return jobs


def fetch_lever(company_slug):
    jobs = []
    try:
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{company_slug}?mode=json",
            timeout=15,
        )
        if resp.status_code != 200:
            return jobs
        data = resp.json()
        for job in data:
            categories = job.get("categories", {}) or {}
            jobs.append({
                "source": f"Lever:{company_slug}",
                "company": company_slug,
                "title": job.get("text", ""),
                "description": job.get("descriptionPlain", "") or job.get("description", ""),
                "tags": [],
                "url": job.get("hostedUrl", ""),
                "location": categories.get("location", ""),
            })
    except Exception as e:
        print(f"Lever fetch failed for '{company_slug}': {e}")
    return jobs


def fetch_target_companies():
    jobs = []
    for slug in TARGET_COMPANIES["greenhouse"]:
        jobs.extend(fetch_greenhouse(slug))
    for slug in TARGET_COMPANIES["lever"]:
        jobs.extend(fetch_lever(slug))
    return jobs


# ---- Remote-board fetchers (unchanged from v2) ----

def fetch_remoteok():
    jobs = []
    try:
        resp = requests.get(
            f"https://remoteok.com/api?tags={REMOTEOK_TAGS}", timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = resp.json()
        for job in data[1:]:
            jobs.append({
                "source": "RemoteOK",
                "company": job.get("company", ""),
                "title": job.get("position", ""),
                "description": job.get("description", ""),
                "tags": job.get("tags", []),
                "url": job.get("url") or job.get("apply_url", ""),
                "location": job.get("location", ""),
            })
    except Exception as e:
        print(f"RemoteOK fetch failed: {e}")
    return jobs


def fetch_remotive(search_terms):
    jobs = []
    for term in search_terms:
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": term, "limit": 50},
                timeout=15,
            )
            data = resp.json()
            for job in data.get("jobs", []):
                jobs.append({
                    "source": "Remotive",
                    "company": job.get("company_name", ""),
                    "title": job.get("title", ""),
                    "description": job.get("description", ""),
                    "tags": job.get("tags", []),
                    "url": job.get("url", ""),
                    "location": job.get("candidate_required_location", ""),
                })
        except Exception as e:
            print(f"Remotive fetch failed for '{term}': {e}")
    return jobs


def dedupe(jobs):
    seen = set()
    unique = []
    for j in jobs:
        key = (j["title"].strip().lower(), j["company"].strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(j)
    return unique


def build_shortlist():
    target_jobs = fetch_target_companies()
    remote_jobs = [
        j for j in (fetch_remoteok() + fetch_remotive(REMOTIVE_SEARCH_TERMS))
        if location_allowed(j["location"])
    ]

    all_jobs = dedupe(target_jobs + remote_jobs)

    shortlist = []
    for job in all_jobs:
        if not title_matches(job["title"]):
            continue
        s = score_job(job["title"], job["description"], job["tags"])
        if s >= MIN_SCORE_TO_INCLUDE:
            job["score"] = s
            job.pop("description", None)  # keep the JSON readable, not full HTML dumps
            shortlist.append(job)

    shortlist.sort(key=lambda x: x["score"], reverse=True)
    return shortlist[:DIGEST_CAP]


def main():
    shortlist = build_shortlist()

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_matches": len(shortlist),
        "jobs": shortlist,
    }

    with open("job_digest.json", "w") as f:
        json.dump(digest, f, indent=2)

    print(f"Found {len(shortlist)} relevant jobs. Saved to job_digest.json\n")
    for job in shortlist[:15]:
        print(f"[{job['score']}] {job['title']} @ {job['company']} ({job['source']}, {job['location'] or 'location unspecified'})")
        print(f"    {job['url']}\n")


if __name__ == "__main__":
    main()

# ---- NEXT STEPS ----
# - Verify/replace the guessed slugs in TARGET_COMPANIES with real ones —
#   check each company's actual careers page URL.
# - For companies with no public ATS API (most banks, Flipkart, Zoho),
#   there's no safe automated pull — check those career pages manually,
#   maybe once a week rather than daily.
# - For each shortlisted job, manually check the company's LinkedIn "People"
#   tab for the hiring manager before messaging — ask Claude to draft the
#   message once you've picked a role.
