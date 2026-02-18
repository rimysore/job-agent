"""
Email Draft Agent — Creates personalized outreach emails for recruiters.

Generates tailored template emails that:
  - Reference the specific job applied to
  - Mention relevant projects from the candidate's profile
  - Include personal details about the recruiter when available
  - Request referral in a professional, non-pushy way

No AI API needed — uses smart templates.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("EmailDrafter")


class EmailDraftAgent:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.data_dir = Path(config["data_dir"])
        self.drafts_path = self.data_dir / "recruiter_drafts.json"

    def _load_drafts(self) -> list:
        if self.drafts_path.exists():
            with open(self.drafts_path) as f:
                return json.load(f)
        return []

    def _save_drafts(self, drafts: list):
        with open(self.drafts_path, "w") as f:
            json.dump(drafts, f, indent=2)

    async def draft_outreach(self, recruiter_data: list[dict],
                             jobs: list[dict]) -> list[dict]:
        """Generate personalized outreach email drafts using templates."""
        existing_drafts = self._load_drafts()
        new_drafts = []

        for rd in recruiter_data:
            # Pick top priority people (max 3 per company)
            people = sorted(
                rd.get("people", []),
                key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(
                    p.get("outreach_priority", "medium"), 1
                ),
            )[:3]

            for person in people:
                draft = self._template_draft(person, rd)
                new_drafts.append(draft)

        existing_drafts.extend(new_drafts)
        self._save_drafts(existing_drafts[-500:])
        return new_drafts

    def _template_draft(self, person: dict, recruiter_data: dict) -> dict:
        """Generate a personalized template email based on person type."""
        first_name = person["name"].split()[0]
        company = person["company"]
        job_title = recruiter_data["job_title"]
        person_type = person.get("person_type", "other")

        # Pick best project to mention
        projects = self.profile.get("projects", [])
        project_mention = ""
        if projects:
            p = projects[0]
            project_mention = (
                f"I recently built {p['name']} — {p['description']}. "
                f"I'd love to bring this kind of initiative to {company}."
            )

        skills_highlight = ", ".join(self.profile.get("skills", [])[:5])
        experience = self.profile.get("experience_years", "several")

        # Different templates based on who we're emailing
        if person_type == "recruiter":
            subject = f"Interested in {job_title} at {company}"
            body = (
                f"Hi {first_name},\n\n"
                f"I recently came across the {job_title} role at {company} and "
                f"wanted to reach out directly. With {experience} years of experience "
                f"in {skills_highlight}, I believe I'd be a strong fit.\n\n"
                f"{project_mention}\n\n"
                f"Would you be open to a brief chat about the role? I'd love to learn "
                f"more about what the team is working on.\n\n"
                f"Best regards,\n"
                f"{self.profile['name']}\n"
                f"{self.profile.get('linkedin_url', '')}"
            )
        elif person_type == "hiring_manager":
            subject = f"Passionate about the {job_title} opportunity at {company}"
            body = (
                f"Hi {first_name},\n\n"
                f"I'm writing to express my strong interest in the {job_title} role "
                f"on your team at {company}. Your work caught my attention and I'd "
                f"love to contribute.\n\n"
                f"I bring {experience} years of hands-on experience with "
                f"{skills_highlight}. {project_mention}\n\n"
                f"I'd welcome any opportunity to discuss how I can add value to your "
                f"team. Would a brief 15-minute call work for you?\n\n"
                f"Best regards,\n"
                f"{self.profile['name']}\n"
                f"{self.profile.get('linkedin_url', '')}\n"
                f"{self.profile.get('github_url', '')}"
            )
        elif person_type == "leadership":
            subject = f"Excited about {company}'s mission — {job_title} role"
            body = (
                f"Hi {first_name},\n\n"
                f"I've been following {company}'s work and I'm genuinely excited "
                f"about where you're headed. I noticed the {job_title} opening and "
                f"believe my background aligns well.\n\n"
                f"With {experience} years building production systems using "
                f"{skills_highlight}, I'm passionate about solving real-world "
                f"problems. {project_mention}\n\n"
                f"I'd love to chat about how I could contribute to your vision. "
                f"Happy to connect at your convenience.\n\n"
                f"Best regards,\n"
                f"{self.profile['name']}\n"
                f"{self.profile.get('linkedin_url', '')}"
            )
        else:
            subject = f"Re: {job_title} at {company}"
            body = (
                f"Hi {first_name},\n\n"
                f"I recently applied for the {job_title} role at {company} and "
                f"wanted to reach out. I'm a {skills_highlight} engineer with "
                f"{experience} years of experience.\n\n"
                f"{project_mention}\n\n"
                f"Would love any chance to discuss the role or learn more about "
                f"the team. Happy to chat at your convenience.\n\n"
                f"Best regards,\n"
                f"{self.profile['name']}\n"
                f"{self.profile.get('linkedin_url', '')}"
            )

        return {
            "id": f"{company}_{person['name']}".replace(" ", "_").lower(),
            "recipient_name": person["name"],
            "recipient_role": person["role"],
            "recipient_linkedin": person.get("linkedin_url", ""),
            "recipient_email": person.get("email", ""),
            "email_guessed": person.get("email_guessed", False),
            "company": company,
            "job_title": job_title,
            "job_url": recruiter_data.get("job_url", ""),
            "subject": subject,
            "body": body,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "outreach_priority": person.get("outreach_priority", "medium"),
        }
