"""
Agent Orchestrator — Coordinates all sub-agents in the pipeline.

Pipeline per cycle:
  1. Job Search Agent → finds new jobs from all sources
  2. AI Relevance Scoring → ranks jobs by fit
  3. Application Manager → queues high-relevance jobs
  4. Recruiter Finder → finds hiring managers for top jobs
  5. Email Drafter → drafts personalized outreach
  6. Notifier → sends email digest of new findings
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("Orchestrator")


class AgentOrchestrator:
    def __init__(self, config, job_searcher, recruiter_finder,
                 email_drafter, app_manager, notifier):
        self.config = config
        self.job_searcher = job_searcher
        self.recruiter_finder = recruiter_finder
        self.email_drafter = email_drafter
        self.app_manager = app_manager
        self.notifier = notifier
        self.data_dir = Path(config["data_dir"])
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def run_cycle(self):
        """Execute one full agent pipeline cycle."""
        cycle_start = datetime.now(timezone.utc)
        logger.info(f"🔄 Starting cycle at {cycle_start.isoformat()}")

        # ── Step 1: Search for jobs ──────────────────────────
        logger.info("━" * 50)
        logger.info("📡 STEP 1: Searching for jobs...")
        new_jobs = await self.job_searcher.search_all_sources()
        logger.info(f"   Found {len(new_jobs)} new job postings")

        if not new_jobs:
            logger.info("   No new jobs found this cycle. Sleeping...")
            return

        # ── Step 2: Score relevance with AI ──────────────────
        logger.info("━" * 50)
        logger.info("🧠 STEP 2: Scoring relevance with AI...")
        scored_jobs = await self.job_searcher.score_jobs(new_jobs)
        min_score = self.config.get("search", {}).get("min_relevance_score", 60)
        hot_jobs = [j for j in scored_jobs if j.get("relevance_score", 0) >= min_score]
        logger.info(f"   {len(hot_jobs)} jobs scored above threshold ({min_score})")

        # ── Step 3: Queue applications ───────────────────────
        logger.info("━" * 50)
        logger.info("📝 STEP 3: Queuing applications...")
        queued = await self.app_manager.queue_applications(hot_jobs)
        logger.info(f"   {len(queued)} new applications queued for review")

        # ── Step 4: Find recruiters ──────────────────────────
        logger.info("━" * 50)
        logger.info("🔍 STEP 4: Finding recruiters & hiring managers...")
        top_jobs = sorted(hot_jobs, key=lambda j: j.get("relevance_score", 0), reverse=True)[:10]
        recruiter_data = await self.recruiter_finder.find_for_jobs(top_jobs)
        logger.info(f"   Found info for {len(recruiter_data)} recruiters/hiring managers")

        # ── Step 5: Draft outreach emails ────────────────────
        logger.info("━" * 50)
        logger.info("✉️  STEP 5: Drafting outreach emails...")
        drafts = await self.email_drafter.draft_outreach(recruiter_data, top_jobs)
        logger.info(f"   {len(drafts)} outreach email drafts created")

        # ── Step 6: Send notification digest ─────────────────
        logger.info("━" * 50)
        logger.info("📧 STEP 6: Sending notification email...")
        await self.notifier.send_digest(
            new_jobs=hot_jobs,
            queued_apps=queued,
            recruiter_drafts=drafts,
            cycle_start=cycle_start,
        )
        logger.info("   ✅ Notification sent!")

        # ── Save cycle metadata ──────────────────────────────
        self._save_cycle_log(cycle_start, len(new_jobs), len(hot_jobs),
                             len(queued), len(recruiter_data), len(drafts))

    def _save_cycle_log(self, started, total_found, relevant, queued,
                        recruiters, drafts):
        """Persist cycle run log for debugging."""
        log_path = self.data_dir / "cycle_log.json"
        logs = []
        if log_path.exists():
            with open(log_path) as f:
                logs = json.load(f)

        logs.append({
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "jobs_found": total_found,
            "jobs_relevant": relevant,
            "apps_queued": queued,
            "recruiters_found": recruiters,
            "drafts_created": drafts,
        })

        # Keep last 100 cycles
        logs = logs[-100:]
        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2)
