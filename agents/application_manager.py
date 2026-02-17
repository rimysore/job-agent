"""
Application Manager — Queues applications and pre-fills basic details.

Maintains a review queue so the user can:
  - See all queued applications
  - Review pre-filled data
  - Fill remaining fields
  - Submit when ready
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("AppManager")


class ApplicationManager:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.data_dir = Path(config["data_dir"])
        self.queue_path = self.data_dir / "application_queue.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_queue(self) -> list:
        if self.queue_path.exists():
            with open(self.queue_path) as f:
                return json.load(f)
        return []

    def _save_queue(self, queue: list):
        with open(self.queue_path, "w") as f:
            json.dump(queue, f, indent=2)

    async def queue_applications(self, jobs: list[dict]) -> list[dict]:
        """Add jobs to the application queue with pre-filled data."""
        queue = self._load_queue()
        existing_urls = {app["job_url"] for app in queue}
        new_apps = []

        for job in jobs:
            url = job.get("url", "")
            if not url or url in existing_urls:
                continue

            application = self._create_application(job)
            queue.append(application)
            new_apps.append(application)
            existing_urls.add(url)

        # Sort queue: pending first, then by relevance
        queue.sort(key=lambda a: (
            0 if a["status"] == "pending_review" else 1,
            -a.get("relevance_score", 0),
        ))

        self._save_queue(queue)
        return new_apps

    def _create_application(self, job: dict) -> dict:
        """Create an application entry with pre-filled data from profile."""
        return {
            # ── Job Info ─────────────────────────────────────
            "job_id": job.get("id", ""),
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_url": job.get("url", ""),
            "job_location": job.get("location", ""),
            "job_source": job.get("source", ""),
            "job_description": job.get("description", "")[:1000],
            "relevance_score": job.get("relevance_score", 0),
            "relevance_reason": job.get("relevance_reason", ""),

            # ── Pre-filled Application Data ──────────────────
            "prefilled": {
                "full_name": self.profile["name"],
                "email": self.profile["email"],
                "phone": self.profile.get("phone", ""),
                "location": self.profile.get("location", ""),
                "linkedin_url": self.profile.get("linkedin_url", ""),
                "github_url": self.profile.get("github_url", ""),
                "portfolio_url": self.profile.get("portfolio_url", ""),
                "resume_url": self.profile.get("resume_url", ""),
                "years_of_experience": self.profile.get("experience_years", ""),
                "education": self.profile.get("education", []),
                "skills": self.profile.get("skills", []),
                "work_authorization": "Authorized" if not self.profile.get("visa_required") else "Requires sponsorship",
                "willing_to_relocate": True,
                "remote_preference": "Yes" if self.profile.get("remote_ok") else "No preference",
                "salary_expectation": self.profile.get("min_salary", ""),
                "earliest_start_date": "2 weeks notice",
                "how_did_you_hear": f"Found via {job.get('source', 'job board')}",
            },

            # ── Fields that need manual input ────────────────
            "needs_manual_input": [
                "cover_letter",
                "why_this_company",
                "additional_info",
                "referral_code",
                "custom_questions",
            ],

            # ── Status Tracking ──────────────────────────────
            "status": "pending_review",  # pending_review → reviewed → applied → rejected/interview
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "applied_at": None,
            "notes": "",
        }

    async def get_pending(self) -> list[dict]:
        """Get all pending applications."""
        queue = self._load_queue()
        return [a for a in queue if a["status"] == "pending_review"]

    async def update_status(self, job_url: str, status: str, notes: str = ""):
        """Update application status."""
        queue = self._load_queue()
        for app in queue:
            if app["job_url"] == job_url:
                app["status"] = status
                app["updated_at"] = datetime.now(timezone.utc).isoformat()
                if notes:
                    app["notes"] = notes
                if status == "applied":
                    app["applied_at"] = datetime.now(timezone.utc).isoformat()
                break
        self._save_queue(queue)

    async def get_stats(self) -> dict:
        """Get application pipeline statistics."""
        queue = self._load_queue()
        stats = {
            "total": len(queue),
            "pending_review": 0,
            "reviewed": 0,
            "applied": 0,
            "interview": 0,
            "rejected": 0,
            "skipped": 0,
        }
        for app in queue:
            status = app.get("status", "pending_review")
            if status in stats:
                stats[status] += 1
        return stats
