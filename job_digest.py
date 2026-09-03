"""
Daily Job Digest — pulls remote listings from two free, public, ToS-safe
APIs (RemoteOK + Remotive), scores each against your profile, and writes
a ranked shortlist to job_digest.json.

WHY THESE TWO SOURCES:
- Both have official public JSON APIs, no auth, no scraping, no ToS risk.
- Naukri/LinkedIn don't offer a public jobs API, so they're intentionally
  left out here — add company-career-page feeds instead (see bottom note).

DEPLOY:
- Push this to a Replit project, add `requests` to requirements,
  and set it up as a Scheduled Deployment (once daily).
"""

import requests
import json
from datetime import datetime, timezone

# ---- Tune this to match how you want to be matched ----
PROFILE_KEYWORDS = {
    "sql": 3, "python": 3, "machine learning": 3, "ml": 2,
    "data analyst": 3, "business analyst": 3, "analytics": 3,
    "bi ": 2, "business intelligence": 2, "power bi": 2,
    "decision scien": 3, "product analyst": 2, "credit risk": 3,
    "risk analyst": 3, "lending": 2, "fintech": 2, "data scien": 2,
    "etl": 1, "looker": 1, "tableau": 1, "stakeholder": 1,
}

# Soft deprioritization, not a hard filter — senior-only roles score lower,
# not zero, since titles are inconsistent across companies.
DEPRIORITIZE_KEYWORDS = [
    "senior ", "staff ", "principal ", "director ", " vp ", "lead ",
    "5+ years", "7+ years", "10+ years",
]

MIN_SCORE_TO_INCLUDE = 3
DIGEST_CAP = 30

SEARCH_TERMS = [
    "data analyst", "business analyst", "sql", "python analytics",
    "risk analyst", "decision science",
]


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


def fetch_remoteok():
    jobs = []
    try:
        resp = requests.get(
            "https://remoteok.com/api", timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = resp.json()
        for job in data[1:]:  # first element is RemoteOK's legal notice, not a job
            jobs.append({
                "source": "RemoteOK",
                "title": job.get("position", ""),
                "company": job.get("company", ""),
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
                    "title": job.get("title", ""),
                    "company": job.get("company_name", ""),
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


def main():
    all_jobs = dedupe(fetch_remoteok() + fetch_remotive(SEARCH_TERMS))

    scored = []
    for job in all_jobs:
        s = score_job(job["title"], job["description"], job["tags"])
        if s >= MIN_SCORE_TO_INCLUDE:
            job["score"] = s
            scored.append(job)

    scored.sort(key=lambda x: x["score"], reverse=True)
    shortlist = scored[:DIGEST_CAP]

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_matches": len(scored),
        "jobs": shortlist,
    }

    with open("job_digest.json", "w") as f:
        json.dump(digest, f, indent=2)

    print(f"Found {len(scored)} relevant jobs. Saved top {len(shortlist)} to job_digest.json\n")
    for job in shortlist[:10]:
        print(f"[{job['score']}] {job['title']} @ {job['company']} ({job['source']}) — {job['url']}")


if __name__ == "__main__":
    main()

# ---- NEXT STEPS (not automated here, on purpose) ----
# 1. India-specific boards (Naukri, Instahyre, iimjobs) have no public API —
#    don't scrape them. Instead, add company career-page RSS/JSON feeds here
#    as they become known (many list on their own site before Naukri).
# 2. For each shortlisted job, manually check the company's LinkedIn "People"
#    tab for the hiring manager — this stays a human step by design.
# 3. Ask Claude to draft a cold message per shortlisted job before sending.
