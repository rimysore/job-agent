"""
Email Notifier — Sends digest emails with new job findings.

Sends a beautifully formatted HTML email with:
  - New jobs found this cycle
  - Queued applications for review
  - Recruiter outreach drafts ready to send
  - Application pipeline stats
"""

import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("Notifier")


class EmailNotifier:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.recipient_email = config["profile"]["email"]
        self.smtp_email = config["api_keys"].get("smtp_email", "")
        self.smtp_password = config["api_keys"].get("smtp_password", "")
        self.data_dir = Path(config["data_dir"])

    async def send_digest(self, new_jobs: list[dict], queued_apps: list[dict],
                          recruiter_drafts: list[dict], cycle_start: datetime):
        """Send a digest email with all findings from this cycle."""
        if not self.smtp_email or not self.smtp_password:
            logger.warning("   ⚠️  SMTP not configured — saving digest to file instead")
            self._save_digest_to_file(new_jobs, queued_apps, recruiter_drafts, cycle_start)
            return

        subject = self._build_subject(new_jobs)
        html_body = self._build_html(new_jobs, queued_apps, recruiter_drafts, cycle_start)

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_email
            msg["To"] = self.recipient_email

            # Plain text fallback
            plain = self._build_plain_text(new_jobs, queued_apps, recruiter_drafts)
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)

            logger.info(f"   📧 Digest sent to {self.recipient_email}")

        except Exception as e:
            logger.error(f"   ❌ Email failed: {e}")
            self._save_digest_to_file(new_jobs, queued_apps, recruiter_drafts, cycle_start)

    def _build_subject(self, jobs: list[dict]) -> str:
        """Build email subject line."""
        count = len(jobs)
        if count == 0:
            return "🤖 JobHunter AI — No new matches this cycle"
        top = jobs[0] if jobs else {}
        return (
            f"🔥 JobHunter AI — {count} new job{'s' if count > 1 else ''} found! "
            f"Top: {top.get('title', 'N/A')} at {top.get('company', 'N/A')}"
        )

    def _build_html(self, jobs: list[dict], apps: list[dict],
                    drafts: list[dict], cycle_start: datetime) -> str:
        """Build beautiful HTML email."""

        # ── Job Cards ────────────────────────────────────────
        job_cards = ""
        for job in sorted(jobs, key=lambda j: j.get("relevance_score", 0), reverse=True)[:20]:
            score = job.get("relevance_score", 0)
            score_color = "#22c55e" if score >= 80 else "#eab308" if score >= 60 else "#ef4444"
            score_emoji = "🔥" if score >= 80 else "⭐" if score >= 60 else "📋"

            job_cards += f"""
            <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:8px 0;background:#fff;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:16px;font-weight:600;color:#111;">
                            {score_emoji} {job.get('title', 'N/A')}
                        </div>
                        <div style="color:#6b7280;font-size:14px;margin-top:2px;">
                            {job.get('company', 'N/A')} • {job.get('location', 'N/A')} • {job.get('source', '')}
                        </div>
                    </div>
                    <div style="background:{score_color};color:#fff;padding:4px 12px;border-radius:20px;font-weight:600;font-size:14px;">
                        {score}%
                    </div>
                </div>
                <p style="color:#374151;font-size:13px;margin:8px 0 12px 0;line-height:1.5;">
                    {job.get('description', '')[:200]}...
                </p>
                <div style="display:flex;gap:8px;">
                    <a href="{job.get('url', '#')}" style="background:#2563eb;color:#fff;padding:6px 16px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:500;">
                        View Job →
                    </a>
                    <span style="color:#9ca3af;font-size:12px;padding:6px 0;">
                        {job.get('relevance_reason', '')}
                    </span>
                </div>
            </div>
            """

        # ── Recruiter Drafts ─────────────────────────────────
        draft_cards = ""
        for draft in drafts[:10]:
            draft_cards += f"""
            <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:8px 0;background:#fff;">
                <div style="font-size:14px;font-weight:600;color:#111;">
                    ✉️ {draft.get('recipient_name', 'N/A')} — {draft.get('recipient_role', '')}
                </div>
                <div style="color:#6b7280;font-size:13px;">{draft.get('company', '')} • {draft.get('job_title', '')}</div>
                <div style="margin-top:8px;padding:12px;background:#f9fafb;border-radius:8px;font-size:13px;">
                    <strong>Subject:</strong> {draft.get('subject', '')}<br><br>
                    {draft.get('body', '')[:300]}...
                </div>
                <div style="margin-top:8px;">
                    <a href="{draft.get('recipient_linkedin', '#')}" style="color:#2563eb;font-size:13px;text-decoration:none;">
                        View LinkedIn Profile →
                    </a>
                </div>
            </div>
            """

        # ── Stats ────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        duration = (now - cycle_start).total_seconds()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f3f4f6;margin:0;padding:20px;">
            <div style="max-width:640px;margin:0 auto;">

                <!-- Header -->
                <div style="background:linear-gradient(135deg,#1e40af,#7c3aed);border-radius:16px;padding:24px;color:#fff;text-align:center;">
                    <div style="font-size:28px;font-weight:700;">🤖 JobHunter AI</div>
                    <div style="font-size:14px;opacity:0.9;margin-top:4px;">
                        Cycle completed in {duration:.0f}s • {now.strftime('%B %d, %Y %H:%M UTC')}
                    </div>
                </div>

                <!-- Stats Bar -->
                <div style="display:flex;gap:12px;margin:16px 0;">
                    <div style="flex:1;background:#fff;border-radius:12px;padding:16px;text-align:center;">
                        <div style="font-size:24px;font-weight:700;color:#2563eb;">{len(jobs)}</div>
                        <div style="color:#6b7280;font-size:12px;">Jobs Found</div>
                    </div>
                    <div style="flex:1;background:#fff;border-radius:12px;padding:16px;text-align:center;">
                        <div style="font-size:24px;font-weight:700;color:#16a34a;">{len(apps)}</div>
                        <div style="color:#6b7280;font-size:12px;">Apps Queued</div>
                    </div>
                    <div style="flex:1;background:#fff;border-radius:12px;padding:16px;text-align:center;">
                        <div style="font-size:24px;font-weight:700;color:#9333ea;">{len(drafts)}</div>
                        <div style="color:#6b7280;font-size:12px;">Outreach Drafts</div>
                    </div>
                </div>

                <!-- Jobs Section -->
                <div style="margin-top:24px;">
                    <h2 style="font-size:18px;color:#111;margin-bottom:12px;">🎯 New Job Matches</h2>
                    {job_cards if job_cards else '<p style="color:#6b7280;">No new matches this cycle.</p>'}
                </div>

                <!-- Outreach Drafts -->
                {"<div style='margin-top:24px;'><h2 style='font-size:18px;color:#111;margin-bottom:12px;'>✉️ Recruiter Outreach Drafts</h2>" + draft_cards + "</div>" if draft_cards else ""}

                <!-- Footer -->
                <div style="text-align:center;padding:24px;color:#9ca3af;font-size:12px;">
                    <p>JobHunter AI is running autonomously on your behalf.</p>
                    <p>Review your application queue and outreach drafts in the dashboard.</p>
                    <p style="margin-top:8px;">🔄 Next cycle runs automatically.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def _build_plain_text(self, jobs, apps, drafts) -> str:
        """Plain text fallback."""
        lines = ["🤖 JobHunter AI — Cycle Report\n"]
        lines.append(f"Jobs found: {len(jobs)} | Apps queued: {len(apps)} | Drafts: {len(drafts)}\n")

        lines.append("\n── NEW JOBS ──")
        for job in sorted(jobs, key=lambda j: j.get("relevance_score", 0), reverse=True)[:15]:
            lines.append(
                f"\n[{job.get('relevance_score', 0)}%] {job.get('title')} at {job.get('company')}"
                f"\n   {job.get('url', 'N/A')}"
                f"\n   {job.get('location', '')} | {job.get('source', '')}"
            )

        if drafts:
            lines.append("\n\n── OUTREACH DRAFTS ──")
            for d in drafts[:5]:
                lines.append(
                    f"\n→ {d.get('recipient_name')} ({d.get('recipient_role')}) at {d.get('company')}"
                    f"\n  Subject: {d.get('subject')}"
                    f"\n  LinkedIn: {d.get('recipient_linkedin', 'N/A')}"
                )

        return "\n".join(lines)

    def _save_digest_to_file(self, jobs, apps, drafts, cycle_start):
        """Save digest to file when SMTP is not configured."""
        digest = {
            "cycle_start": cycle_start.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "jobs_count": len(jobs),
            "apps_count": len(apps),
            "drafts_count": len(drafts),
            "jobs": jobs[:20],
            "drafts": drafts[:10],
        }
        digest_path = self.data_dir / "last_digest.json"
        with open(digest_path, "w") as f:
            json.dump(digest, f, indent=2)
        logger.info(f"   💾 Digest saved to {digest_path}")
