#!/usr/bin/env python3
"""
🤖 JobHunter AI — Autonomous Multi-Agent Job Search System
===========================================================
An always-on AI agent that searches for jobs, finds recruiters,
drafts outreach emails, and queues applications for your review.

Deploy on GitHub Actions for 24/7 autonomous operation.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import AgentOrchestrator
from agents.job_searcher import JobSearchAgent
from agents.recruiter_finder import RecruiterFinderAgent
from agents.email_drafter import EmailDraftAgent
from agents.application_manager import ApplicationManager
from agents.notifier import EmailNotifier
from config.loader import load_config

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("JobHunter")


async def main():
    """Main entry point for the Job Hunter agent system."""
    logger.info("=" * 60)
    logger.info("🚀 JobHunter AI — Starting Autonomous Job Search")
    logger.info("=" * 60)

    # ── Load Configuration ───────────────────────────────
    config = load_config()
    logger.info(f"📋 Profile: {config['profile']['name']}")
    logger.info(f"🎯 Target roles: {', '.join(config['profile']['target_roles'])}")
    logger.info(f"📧 Notifications → {config['profile']['email']}")
    logger.info(f"🏢 Tracking {len(config.get('startups', []))} startups")

    # ── Initialize Agents ────────────────────────────────
    notifier = EmailNotifier(config)
    app_manager = ApplicationManager(config)
    job_searcher = JobSearchAgent(config)
    recruiter_finder = RecruiterFinderAgent(config)
    email_drafter = EmailDraftAgent(config)

    orchestrator = AgentOrchestrator(
        config=config,
        job_searcher=job_searcher,
        recruiter_finder=recruiter_finder,
        email_drafter=email_drafter,
        app_manager=app_manager,
        notifier=notifier,
    )

    # ── Run Agent Pipeline ───────────────────────────────
    await orchestrator.run_cycle()

    logger.info("=" * 60)
    logger.info("✅ JobHunter AI — Cycle Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
