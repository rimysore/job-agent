"""
Job Search Agent — Searches multiple sources for relevant job postings.

Sources:
  1. Google Jobs (via Serper API)
  2. Company career pages (Greenhouse, Lever, Ashby APIs)
  3. YC Work at a Startup
  4. Wellfound (AngelList)
  5. LinkedIn (via Google search)
  6. Direct startup career page scraping

Uses Claude AI to score relevance of each job against your profile.
"""

import json
import hashlib
import logging
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("JobSearcher")


class JobSearchAgent:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.startups = config.get("startups", [])
        self.search_config = config.get("search", {})
        self.data_dir = Path(config["data_dir"])
        self.seen_jobs_path = self.data_dir / "seen_jobs.json"
        self.jobs_path = self.data_dir / "job_queue.json"
        self.seen_jobs = self._load_seen_jobs()

        # API clients
        self.serper_key = config["api_keys"].get("serper", "")
        self.gemini_key = config["api_keys"].get("gemini", "")
        self.max_age_hours = 48  # Only jobs posted in last 48 hours

    def _is_within_age_limit(self, date_str: str) -> bool:
        """Check if a date string is within the max age limit (48 hours)."""
        if not date_str:
            return True  # If no date, include it (benefit of the doubt)
        try:
            # Handle various date formats
            for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"]:
                try:
                    posted = datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
                    return posted >= cutoff
                except ValueError:
                    continue
            return True  # If we can't parse, include it
        except Exception:
            return True

    def _load_seen_jobs(self) -> set:
        """Load set of already-seen job IDs to avoid duplicates."""
        if self.seen_jobs_path.exists():
            with open(self.seen_jobs_path) as f:
                return set(json.load(f))
        return set()

    def _save_seen_jobs(self):
        """Persist seen job IDs."""
        with open(self.seen_jobs_path, "w") as f:
            json.dump(list(self.seen_jobs), f)

    def _job_id(self, title: str, company: str, url: str) -> str:
        """Generate unique ID for a job posting."""
        raw = f"{title.lower().strip()}|{company.lower().strip()}|{url.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def search_all_sources(self) -> list[dict]:
        """Run all search sources in parallel and return new jobs."""
        tasks = [
            self._search_google_jobs(),
            self._search_greenhouse_boards(),
            self._search_lever_boards(),
            self._search_ashby_boards(),
            self._search_yc_jobs(),
            self._search_linkedin_jobs(),
            self._search_indeed_jobs(),
            self._search_startup_pages(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"   Source {i} failed: {result}")
            else:
                all_jobs.extend(result)

        # Deduplicate against seen jobs
        new_jobs = []
        for job in all_jobs:
            jid = self._job_id(job["title"], job["company"], job.get("url", ""))
            if jid not in self.seen_jobs:
                job["id"] = jid
                job["discovered_at"] = datetime.now(timezone.utc).isoformat()
                new_jobs.append(job)
                self.seen_jobs.add(jid)

        self._save_seen_jobs()
        self._save_jobs(new_jobs)
        return new_jobs

    def _save_jobs(self, jobs: list[dict]):
        """Append new jobs to the persistent job queue."""
        existing = []
        if self.jobs_path.exists():
            with open(self.jobs_path) as f:
                existing = json.load(f)
        existing.extend(jobs)
        # Keep last 1000 jobs
        existing = existing[-1000:]
        with open(self.jobs_path, "w") as f:
            json.dump(existing, f, indent=2)

    # ══════════════════════════════════════════════════════════
    # Source 1: Google Jobs via Serper API
    # ══════════════════════════════════════════════════════════
    async def _search_google_jobs(self) -> list[dict]:
        """Search Google Jobs using Serper API."""
        if not self.serper_key:
            logger.info("   ⏭️  Serper API key not set, skipping Google Jobs")
            return []

        jobs = []
        roles = self.profile.get("target_roles", [])
        locations = self.profile.get("preferred_locations", ["Remote"])

        async with aiohttp.ClientSession() as session:
            for role in roles[:5]:  # Limit to avoid rate limits
                for loc in locations[:3]:
                    query = f"{role} {loc}"
                    try:
                        resp = await session.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.serper_key,
                                "Content-Type": "application/json",
                            },
                            json={
                                "q": f"{query} jobs",
                                "type": "search",
                                "num": 20,
                                "tbs": "qdr:d2",  # Last 48 hours only
                            },
                        )
                        data = await resp.json()

                        for result in data.get("organic", []):
                            # Filter for job-related results
                            title = result.get("title", "")
                            link = result.get("link", "")
                            snippet = result.get("snippet", "")

                            if any(kw in link.lower() for kw in
                                   ["greenhouse", "lever", "ashby", "jobs",
                                    "careers", "wellfound", "linkedin.com/jobs"]):
                                jobs.append({
                                    "title": title,
                                    "company": self._extract_company(title, link),
                                    "url": link,
                                    "description": snippet,
                                    "location": loc,
                                    "source": "google_jobs",
                                    "search_query": query,
                                })

                        # Also check job listings in Serper
                        for job_result in data.get("jobs", []):
                            jobs.append({
                                "title": job_result.get("title", ""),
                                "company": job_result.get("companyName", ""),
                                "url": job_result.get("link", ""),
                                "description": job_result.get("snippet", ""),
                                "location": job_result.get("location", loc),
                                "source": "google_jobs",
                                "date_posted": job_result.get("date", ""),
                            })

                    except Exception as e:
                        logger.warning(f"   Google search failed for '{query}': {e}")

                    await asyncio.sleep(0.5)  # Rate limiting

        logger.info(f"   📡 Google Jobs: {len(jobs)} results")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 2: Greenhouse ATS API (public boards)
    # ══════════════════════════════════════════════════════════
    async def _search_greenhouse_boards(self) -> list[dict]:
        """Fetch jobs from Greenhouse public job board APIs."""
        greenhouse_companies = [
            s for s in self.startups
            if s.get("ats", "").lower() == "greenhouse" and s.get("domain")
        ]

        jobs = []
        async with aiohttp.ClientSession() as session:
            for company in greenhouse_companies:
                board_token = company["domain"].replace(".com", "").replace(".co", "").replace(".ai", "").replace(".io", "").replace("www.", "").replace(".", "")
                url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

                try:
                    resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=10))
                    if resp.status == 200:
                        data = await resp.json()
                        for job in data.get("jobs", []):
                            title = job.get("title", "")
                            if self._is_relevant_title(title):
                                posted_at = job.get("updated_at", "")
                                if not self._is_within_age_limit(posted_at):
                                    continue
                                loc = ""
                                if job.get("location", {}).get("name"):
                                    loc = job["location"]["name"]
                                jobs.append({
                                    "title": title,
                                    "company": company["name"],
                                    "url": job.get("absolute_url", ""),
                                    "description": self._strip_html(job.get("content", "")),
                                    "location": loc,
                                    "source": "greenhouse",
                                    "department": ", ".join(
                                        d.get("name", "") for d in job.get("departments", [])
                                    ),
                                    "posted_at": job.get("updated_at", ""),
                                })
                except Exception as e:
                    logger.debug(f"   Greenhouse {company['name']}: {e}")

                await asyncio.sleep(0.3)

        logger.info(f"   🌱 Greenhouse: {len(jobs)} results from {len(greenhouse_companies)} companies")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 3: Lever ATS API (public postings)
    # ══════════════════════════════════════════════════════════
    async def _search_lever_boards(self) -> list[dict]:
        """Fetch jobs from Lever public postings API."""
        lever_companies = [
            s for s in self.startups
            if s.get("ats", "").lower() == "lever" and s.get("domain")
        ]

        jobs = []
        async with aiohttp.ClientSession() as session:
            for company in lever_companies:
                slug = company["domain"].replace(".com", "").replace(".co", "").replace(".ai", "").replace(".io", "").replace("www.", "").replace(".", "")
                url = f"https://api.lever.co/v0/postings/{slug}"

                try:
                    resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=10))
                    if resp.status == 200:
                        data = await resp.json()
                        for job in data:
                            title = job.get("text", "")
                            if self._is_relevant_title(title):
                                loc_parts = []
                                if job.get("categories", {}).get("location"):
                                    loc_parts.append(job["categories"]["location"])
                                jobs.append({
                                    "title": title,
                                    "company": company["name"],
                                    "url": job.get("hostedUrl", ""),
                                    "description": job.get("descriptionPlain", ""),
                                    "location": ", ".join(loc_parts),
                                    "source": "lever",
                                    "department": job.get("categories", {}).get("team", ""),
                                    "commitment": job.get("categories", {}).get("commitment", ""),
                                    "posted_at": "",
                                })
                except Exception as e:
                    logger.debug(f"   Lever {company['name']}: {e}")

                await asyncio.sleep(0.3)

        logger.info(f"   🔧 Lever: {len(jobs)} results from {len(lever_companies)} companies")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 4: Ashby ATS API
    # ══════════════════════════════════════════════════════════
    async def _search_ashby_boards(self) -> list[dict]:
        """Fetch jobs from Ashby job board API."""
        ashby_companies = [
            s for s in self.startups
            if s.get("ats", "").lower() == "ashby" and s.get("domain")
        ]

        jobs = []
        async with aiohttp.ClientSession() as session:
            for company in ashby_companies:
                slug = company["domain"].replace(".com", "").replace(".co", "").replace(".ai", "").replace(".io", "").replace("www.", "").replace(".", "")
                url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

                try:
                    resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=10))
                    if resp.status == 200:
                        data = await resp.json()
                        for job in data.get("jobs", []):
                            title = job.get("title", "")
                            if self._is_relevant_title(title):
                                published = job.get("publishedAt", "")
                                if not self._is_within_age_limit(published):
                                    continue
                                jobs.append({
                                    "title": title,
                                    "company": company["name"],
                                    "url": job.get("jobUrl", ""),
                                    "description": job.get("descriptionPlain", ""),
                                    "location": job.get("location", ""),
                                    "source": "ashby",
                                    "department": job.get("departmentName", ""),
                                    "posted_at": job.get("publishedAt", ""),
                                })
                except Exception as e:
                    logger.debug(f"   Ashby {company['name']}: {e}")

                await asyncio.sleep(0.3)

        logger.info(f"   🔷 Ashby: {len(jobs)} results from {len(ashby_companies)} companies")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 5: YC Work at a Startup
    # ══════════════════════════════════════════════════════════
    async def _search_yc_jobs(self) -> list[dict]:
        """Search YC's Work at a Startup job board via Algolia API."""
        jobs = []
        roles = self.profile.get("target_roles", [])

        async with aiohttp.ClientSession() as session:
            for role in roles[:3]:
                try:
                    # YC uses Algolia for their job search
                    url = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"
                    params = {
                        "x-algolia-application-id": "45BWZJ1SGC",
                        "x-algolia-api-key": "MjBjYjRiMzY0NzdhZWY0NjExY2NhZjYxMGIxYjc2MTAwNWFkNTkwNTc4NjgxYjU0YzFhYTY2ZGRlOGY4OTdhZnJlc3RyaWN0SW5kaWNlcz0lNUIlMjJZQ0NvbXBhbnlfcHJvZHVjdGlvbiUyMiUyQyUyMllDQ29tcGFueV9CeV9MYXVuY2hfRGF0ZV9wcm9kdWN0aW9uJTIyJTVEJnRhZ0ZpbHRlcnM9JTVCJTIyeWNkY19wdWJsaWMlMjIlNUQmYW5hbHl0aWNzVGFncz0lNUIlMjJ5Y2RjJTIyJTVE",
                    }
                    payload = {
                        "requests": [{
                            "indexName": "YCJob_production",
                            "params": f"query={role}&hitsPerPage=20"
                        }]
                    }
                    resp = await session.post(url, params=params, json=payload,
                                              timeout=aiohttp.ClientTimeout(total=10))
                    if resp.status == 200:
                        data = await resp.json()
                        for result in data.get("results", []):
                            for hit in result.get("hits", []):
                                title = hit.get("title", "")
                                company = hit.get("company_name", "")
                                if self._is_relevant_title(title):
                                    slug = hit.get("slug", "")
                                    jobs.append({
                                        "title": title,
                                        "company": company,
                                        "url": f"https://www.workatastartup.com/jobs/{slug}" if slug else "",
                                        "description": hit.get("description", ""),
                                        "location": hit.get("pretty_location", ""),
                                        "source": "yc_wais",
                                        "remote": hit.get("remote", False),
                                        "salary_min": hit.get("salary_min"),
                                        "salary_max": hit.get("salary_max"),
                                    })
                except Exception as e:
                    logger.debug(f"   YC search failed for '{role}': {e}")

                await asyncio.sleep(0.5)

        logger.info(f"   🟠 YC WAIS: {len(jobs)} results")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 6: LinkedIn Jobs (via Google/Serper)
    # ══════════════════════════════════════════════════════════
    async def _search_linkedin_jobs(self) -> list[dict]:
        """Search LinkedIn job postings via Google (Serper API).
        
        LinkedIn doesn't have a public API for job search, so we use
        Google site: search to find LinkedIn job postings.
        """
        if not self.serper_key:
            logger.info("   ⏭️  No Serper key — skipping LinkedIn")
            return []

        jobs = []
        roles = self.profile.get("target_roles", [])
        locations = self.profile.get("preferred_locations", ["Remote"])

        async with aiohttp.ClientSession() as session:
            for role in roles[:5]:
                for loc in locations[:3]:
                    query = f'site:linkedin.com/jobs "{role}" "{loc}"'
                    try:
                        resp = await session.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.serper_key,
                                "Content-Type": "application/json",
                            },
                            json={"q": query, "num": 15, "tbs": "qdr:d2"},
                        )
                        data = await resp.json()

                        for result in data.get("organic", []):
                            title = result.get("title", "")
                            link = result.get("link", "")
                            snippet = result.get("snippet", "")

                            if "linkedin.com/jobs" in link and self._is_relevant_title(title):
                                company = self._extract_company(title, link)
                                jobs.append({
                                    "title": title.replace(" | LinkedIn", "").strip(),
                                    "company": company,
                                    "url": link,
                                    "description": snippet,
                                    "location": loc,
                                    "source": "linkedin",
                                    "search_query": f"{role} {loc}",
                                })

                    except Exception as e:
                        logger.debug(f"   LinkedIn search failed for '{role} {loc}': {e}")

                    await asyncio.sleep(0.5)

            # Also search LinkedIn for each tracked startup
            for startup in self.startups[:15]:
                query = f'site:linkedin.com/jobs "{startup["name"]}" (engineer OR developer OR AI)'
                try:
                    resp = await session.post(
                        "https://google.serper.dev/search",
                        headers={
                            "X-API-KEY": self.serper_key,
                            "Content-Type": "application/json",
                        },
                        json={"q": query, "num": 10, "tbs": "qdr:d2"},
                    )
                    data = await resp.json()

                    for result in data.get("organic", []):
                        title = result.get("title", "")
                        link = result.get("link", "")
                        snippet = result.get("snippet", "")

                        if "linkedin.com/jobs" in link:
                            jobs.append({
                                "title": title.replace(" | LinkedIn", "").strip(),
                                "company": startup["name"],
                                "url": link,
                                "description": snippet,
                                "location": startup.get("location", ""),
                                "source": "linkedin",
                                "search_query": startup["name"],
                            })

                except Exception as e:
                    logger.debug(f"   LinkedIn startup search failed for '{startup['name']}': {e}")

                await asyncio.sleep(0.4)

        logger.info(f"   💼 LinkedIn: {len(jobs)} results")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 7: Indeed Jobs (via Google/Serper)
    # ══════════════════════════════════════════════════════════
    async def _search_indeed_jobs(self) -> list[dict]:
        """Search Indeed job postings via Google (Serper API).
        
        Uses Google site: search to find Indeed listings since
        Indeed's API is restricted.
        """
        if not self.serper_key:
            logger.info("   ⏭️  No Serper key — skipping Indeed")
            return []

        jobs = []
        roles = self.profile.get("target_roles", [])
        locations = self.profile.get("preferred_locations", ["Remote"])

        async with aiohttp.ClientSession() as session:
            for role in roles[:5]:
                for loc in locations[:3]:
                    query = f'site:indeed.com/viewjob "{role}" "{loc}"'
                    try:
                        resp = await session.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.serper_key,
                                "Content-Type": "application/json",
                            },
                            json={"q": query, "num": 15, "tbs": "qdr:d2"},
                        )
                        data = await resp.json()

                        for result in data.get("organic", []):
                            title = result.get("title", "")
                            link = result.get("link", "")
                            snippet = result.get("snippet", "")

                            if "indeed.com" in link and self._is_relevant_title(title):
                                company = self._extract_company(title, link)
                                jobs.append({
                                    "title": title.replace(" - Indeed", "").replace(" | Indeed.com", "").strip(),
                                    "company": company,
                                    "url": link,
                                    "description": snippet,
                                    "location": loc,
                                    "source": "indeed",
                                    "search_query": f"{role} {loc}",
                                })

                    except Exception as e:
                        logger.debug(f"   Indeed search failed for '{role} {loc}': {e}")

                    await asyncio.sleep(0.5)

            # Search Indeed for tracked startups too
            for startup in self.startups[:15]:
                query = f'site:indeed.com "{startup["name"]}" (engineer OR developer OR AI)'
                try:
                    resp = await session.post(
                        "https://google.serper.dev/search",
                        headers={
                            "X-API-KEY": self.serper_key,
                            "Content-Type": "application/json",
                        },
                        json={"q": query, "num": 5, "tbs": "qdr:d2"},
                    )
                    data = await resp.json()

                    for result in data.get("organic", []):
                        title = result.get("title", "")
                        link = result.get("link", "")
                        snippet = result.get("snippet", "")

                        if "indeed.com" in link:
                            jobs.append({
                                "title": title.replace(" - Indeed", "").strip(),
                                "company": startup["name"],
                                "url": link,
                                "description": snippet,
                                "location": startup.get("location", ""),
                                "source": "indeed",
                                "search_query": startup["name"],
                            })

                except Exception as e:
                    logger.debug(f"   Indeed startup search failed for '{startup['name']}': {e}")

                await asyncio.sleep(0.4)

        logger.info(f"   📋 Indeed: {len(jobs)} results")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Source 8: Direct startup career page search
    # ══════════════════════════════════════════════════════════
    async def _search_startup_pages(self) -> list[dict]:
        """Search startup career pages directly via Google."""
        if not self.serper_key:
            return []

        jobs = []
        async with aiohttp.ClientSession() as session:
            for startup in self.startups:
                if startup.get("careers_url"):
                    query = f"site:{startup['domain']} (engineer OR developer) jobs"
                    try:
                        resp = await session.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.serper_key,
                                "Content-Type": "application/json",
                            },
                            json={"q": query, "num": 10, "tbs": "qdr:d2"},
                        )
                        data = await resp.json()
                        for result in data.get("organic", []):
                            title = result.get("title", "")
                            if self._is_relevant_title(title):
                                jobs.append({
                                    "title": title,
                                    "company": startup["name"],
                                    "url": result.get("link", ""),
                                    "description": result.get("snippet", ""),
                                    "location": "",
                                    "source": "direct_search",
                                })
                    except Exception as e:
                        logger.debug(f"   Direct search {startup['name']}: {e}")

                    await asyncio.sleep(0.5)

        logger.info(f"   🔎 Direct search: {len(jobs)} results")
        return jobs

    # ══════════════════════════════════════════════════════════
    # AI Relevance Scoring
    # ══════════════════════════════════════════════════════════
    async def score_jobs(self, jobs: list[dict]) -> list[dict]:
        """Use Google Gemini (FREE) to score each job's relevance to the profile."""
        if not self.gemini_key:
            logger.warning("   ⚠️  No Gemini API key — using keyword scoring")
            return self._keyword_score(jobs)

        client = genai.Client(api_key=self.gemini_key)

        # Process in batches of 10
        batch_size = 10
        scored = []

        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            jobs_text = "\n\n".join([
                f"JOB {j+1}:\n"
                f"Title: {job['title']}\n"
                f"Company: {job['company']}\n"
                f"Location: {job.get('location', 'N/A')}\n"
                f"Description: {job.get('description', 'N/A')[:500]}"
                for j, job in enumerate(batch)
            ])

            profile_summary = (
                f"Target roles: {', '.join(self.profile['target_roles'])}\n"
                f"Skills: {', '.join(self.profile['skills'][:20])}\n"
                f"Experience: {self.profile['experience_years']} years\n"
                f"Preferred locations: {', '.join(self.profile['preferred_locations'])}\n"
                f"Remote OK: {self.profile['remote_ok']}\n"
                f"Keywords: {', '.join(self.profile.get('target_keywords', []))}"
            )

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=(
                        f"Score each job's relevance to this candidate profile (0-100).\n\n"
                        f"CANDIDATE PROFILE:\n{profile_summary}\n\n"
                        f"JOBS:\n{jobs_text}\n\n"
                        f"Return ONLY a JSON array of objects with 'job_number' (1-indexed) "
                        f"and 'score' (0-100) and 'reason' (1 sentence). No other text."
                    ),
                    config=genai_types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=2000,
                    ),
                )

                text = response.text.strip()
                # Clean markdown fences
                text = text.replace("```json", "").replace("```", "").strip()
                scores = json.loads(text)

                for score_item in scores:
                    idx = score_item["job_number"] - 1
                    if 0 <= idx < len(batch):
                        batch[idx]["relevance_score"] = score_item["score"]
                        batch[idx]["relevance_reason"] = score_item.get("reason", "")

            except Exception as e:
                logger.warning(f"   AI scoring failed for batch: {e}")
                # Fallback to keyword scoring
                batch = self._keyword_score(batch)

            scored.extend(batch)
            await asyncio.sleep(2)  # Rate limiting for free tier

        # Ensure EVERY job has a score — assign 0 to any missed
        for job in scored:
            if "relevance_score" not in job or job["relevance_score"] is None:
                job["relevance_score"] = 0
                job["relevance_reason"] = "Not scored"

        return scored

    def _keyword_score(self, jobs: list[dict]) -> list[dict]:
        """Fallback keyword-based scoring."""
        keywords = set(
            [r.lower() for r in self.profile.get("target_roles", [])] +
            [k.lower() for k in self.profile.get("target_keywords", [])] +
            [s.lower() for s in self.profile.get("skills", [])]
        )

        for job in jobs:
            text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            matches = sum(1 for kw in keywords if kw in text)
            job["relevance_score"] = min(100, int(matches / max(len(keywords), 1) * 150))
            job["relevance_reason"] = f"Keyword match: {matches}/{len(keywords)}"

        return jobs

    # ══════════════════════════════════════════════════════════
    # Utilities
    # ══════════════════════════════════════════════════════════
    def _is_relevant_title(self, title: str) -> bool:
        """Quick filter on job title relevance."""
        title_lower = title.lower()
        # Must contain at least one relevant keyword
        relevant = ["engineer", "developer", "ml ", "ai ", "machine learning",
                     "software", "backend", "frontend", "full stack", "fullstack",
                     "platform", "infrastructure", "mlops", "data scientist",
                     "applied scientist", "llm", "nlp"]
        # Exclude irrelevant roles even if they contain "engineer"
        hard_exclude = ["desktop support", "help desk", "it support", "network admin",
                        "system administrator", "desktop engineer", "field service",
                        "support engineer", "hardware engineer", "mechanical engineer",
                        "civil engineer", "electrical engineer", "sales engineer",
                        "customer support", "technical support", "android", "ios "]
        exclude = self.search_config.get("exclude_keywords", [])
        all_excludes = [kw.lower() for kw in exclude] + hard_exclude

        has_relevant = any(kw in title_lower for kw in relevant)
        has_exclude = any(kw in title_lower for kw in all_excludes)

        return has_relevant and not has_exclude

    def _extract_company(self, title: str, url: str) -> str:
        """Try to extract company name from title or URL."""
        # Try common patterns
        if " at " in title:
            return title.split(" at ")[-1].strip()
        if " - " in title:
            return title.split(" - ")[-1].strip()
        # Extract from URL domain
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "").split(".")[0]
        return domain.title()

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags from text."""
        import re
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()[:2000]
