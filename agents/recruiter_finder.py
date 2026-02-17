"""
Recruiter Finder Agent — Finds hiring managers & recruiters for target jobs.

Uses Google search to find LinkedIn profiles and public info about
recruiters and engineering managers at target companies.
"""

import json
import logging
import aiohttp
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("RecruiterFinder")


class RecruiterFinderAgent:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.data_dir = Path(config["data_dir"])
        self.recruiters_path = self.data_dir / "recruiters.json"
        self.serper_key = config["api_keys"].get("serper", "")
        self.gemini_key = config["api_keys"].get("gemini", "")

    def _load_existing(self) -> dict:
        """Load existing recruiter data."""
        if self.recruiters_path.exists():
            with open(self.recruiters_path) as f:
                return json.load(f)
        return {}

    def _save_recruiters(self, data: dict):
        """Save recruiter data."""
        with open(self.recruiters_path, "w") as f:
            json.dump(data, f, indent=2)

    async def find_for_jobs(self, jobs: list[dict]) -> list[dict]:
        """Find recruiters and hiring managers for a list of jobs."""
        existing = self._load_existing()
        results = []

        # Group jobs by company
        companies = {}
        for job in jobs:
            company = job.get("company", "")
            if company and company not in companies:
                companies[company] = job

        for company, sample_job in companies.items():
            if company in existing:
                results.append(existing[company])
                continue

            recruiter_info = await self._search_company_recruiters(company, sample_job)
            if recruiter_info:
                existing[company] = recruiter_info
                results.append(recruiter_info)

            await asyncio.sleep(1)  # Rate limiting

        self._save_recruiters(existing)
        return results

    async def _search_company_recruiters(self, company: str, job: dict) -> dict | None:
        """Search for recruiters at a specific company."""
        if not self.serper_key:
            logger.info(f"   ⏭️  No Serper key — skipping recruiter search for {company}")
            return None

        recruiter_data = {
            "company": company,
            "job_title": job.get("title", ""),
            "job_url": job.get("url", ""),
            "found_at": datetime.now(timezone.utc).isoformat(),
            "people": [],
        }

        # Search queries to find relevant people AT THIS SPECIFIC COMPANY for THIS JOB
        job_title = job.get("title", "")
        search_queries = [
            f'site:linkedin.com/in "{company}" "recruiter" OR "talent acquisition"',
            f'site:linkedin.com/in "{company}" "engineering manager" OR "hiring"',
            f'site:linkedin.com/in "{company}" "CTO" OR "VP engineering" OR "head of engineering"',
        ]

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    resp = await session.post(
                        "https://google.serper.dev/search",
                        headers={
                            "X-API-KEY": self.serper_key,
                            "Content-Type": "application/json",
                        },
                        json={"q": query, "num": 5},
                    )
                    data = await resp.json()

                    for result in data.get("organic", []):
                        link = result.get("link", "")
                        title = result.get("title", "")
                        snippet = result.get("snippet", "")

                        if "linkedin.com/in/" in link:
                            person = self._parse_linkedin_result(title, snippet, link, company)
                            if person:
                                # Check for duplicates
                                existing_urls = [p["linkedin_url"] for p in recruiter_data["people"]]
                                if person["linkedin_url"] not in existing_urls:
                                    recruiter_data["people"].append(person)

                except Exception as e:
                    logger.debug(f"   Recruiter search failed for {company}: {e}")

                await asyncio.sleep(0.5)

        # Find email addresses for each person
        if recruiter_data["people"]:
            recruiter_data = await self._find_emails(recruiter_data)

        # Use AI to analyze and enrich the recruiter data
        if recruiter_data["people"] and self.gemini_key:
            recruiter_data = await self._enrich_with_ai(recruiter_data)

        if recruiter_data["people"]:
            logger.info(f"   👤 {company}: Found {len(recruiter_data['people'])} contacts")
            return recruiter_data

        return None

    def _parse_linkedin_result(self, title: str, snippet: str,
                               url: str, company: str) -> dict | None:
        """Parse a LinkedIn search result into a person record."""
        # LinkedIn titles are usually "Name - Title - Company | LinkedIn"
        parts = title.replace(" | LinkedIn", "").split(" - ")
        if len(parts) < 2:
            return None

        name = parts[0].strip()
        role = parts[1].strip() if len(parts) > 1 else ""

        # Determine person type
        role_lower = role.lower()
        person_type = "other"
        if any(kw in role_lower for kw in ["recruit", "talent", "people"]):
            person_type = "recruiter"
        elif any(kw in role_lower for kw in ["engineering manager", "eng manager",
                                              "head of eng", "vp eng", "director eng"]):
            person_type = "hiring_manager"
        elif any(kw in role_lower for kw in ["cto", "co-founder", "founder", "ceo"]):
            person_type = "leadership"
        elif any(kw in role_lower for kw in ["engineer", "developer", "tech lead"]):
            person_type = "engineer"

        return {
            "name": name,
            "role": role,
            "person_type": person_type,
            "linkedin_url": url.split("?")[0],  # Clean URL
            "snippet": snippet[:300],
            "company": company,
            "email": "",  # Will be populated by email finder
        }

    async def _find_emails(self, recruiter_data: dict) -> dict:
        """Try to find email addresses for each person via Google search."""
        if not self.serper_key:
            return recruiter_data

        company = recruiter_data["company"]

        # Try to find company domain first
        domain = ""
        for startup in self.config.get("startups", []):
            if startup["name"].lower() == company.lower():
                domain = startup.get("domain", "")
                break

        async with aiohttp.ClientSession() as session:
            for person in recruiter_data["people"]:
                name = person["name"]
                # Search for email
                queries = [
                    f'"{name}" "{company}" email "@"',
                    f'"{name}" "{company}" contact email',
                ]
                if domain:
                    queries.insert(0, f'"{name}" "@{domain}"')

                for query in queries[:2]:
                    try:
                        resp = await session.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.serper_key,
                                "Content-Type": "application/json",
                            },
                            json={"q": query, "num": 5},
                        )
                        data = await resp.json()

                        # Search snippets for email patterns
                        import re
                        email_pattern = re.compile(
                            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                        )
                        for result in data.get("organic", []):
                            snippet = result.get("snippet", "")
                            title = result.get("title", "")
                            text = f"{title} {snippet}"
                            emails = email_pattern.findall(text)
                            for email in emails:
                                # Filter out generic/spam emails
                                email_lower = email.lower()
                                if any(skip in email_lower for skip in
                                       ["example.com", "email.com", "test.com",
                                        "sentry.io", "github.com", "noreply",
                                        "support@", "info@", "hello@", "contact@"]):
                                    continue
                                person["email"] = email
                                break
                            if person["email"]:
                                break

                    except Exception as e:
                        logger.debug(f"   Email search failed for {name}: {e}")

                    await asyncio.sleep(0.3)

                    if person["email"]:
                        break

                # If no email found via search, generate likely pattern
                if not person["email"] and domain:
                    name_parts = name.lower().split()
                    if len(name_parts) >= 2:
                        first = name_parts[0]
                        last = name_parts[-1]
                        # Most common pattern: first.last@company.com
                        person["email"] = f"{first}.{last}@{domain}"
                        person["email_guessed"] = True

        return recruiter_data

    async def _enrich_with_ai(self, recruiter_data: dict) -> dict:
        """Use Gemini to analyze and add insights about each recruiter."""
        try:
            client = genai.Client(api_key=self.gemini_key)

            people_text = "\n".join([
                f"- {p['name']} | {p['role']} | {p['person_type']} | {p['snippet']}"
                for p in recruiter_data["people"]
            ])

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=(
                    f"Analyze these people at {recruiter_data['company']} for a job outreach strategy. "
                    f"For each person, provide a JSON array with:\n"
                    f"- 'name': their name\n"
                    f"- 'priority': 'high', 'medium', or 'low' for outreach\n"
                    f"- 'outreach_angle': 1 sentence on best way to approach them\n"
                    f"- 'talking_points': list of 2-3 things to mention based on their role\n\n"
                    f"People:\n{people_text}\n\n"
                    f"Job being applied to: {recruiter_data['job_title']}\n\n"
                    f"Return ONLY valid JSON array, no markdown."
                ),
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1500,
                ),
            )

            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            insights = json.loads(text)

            for insight in insights:
                for person in recruiter_data["people"]:
                    if person["name"].lower() == insight.get("name", "").lower():
                        person["outreach_priority"] = insight.get("priority", "medium")
                        person["outreach_angle"] = insight.get("outreach_angle", "")
                        person["talking_points"] = insight.get("talking_points", [])

        except Exception as e:
            logger.warning(f"   AI enrichment failed: {e}")

        return recruiter_data
