"""
Email Draft Agent — Creates personalized outreach emails for recruiters.

Generates tailored emails that:
  - Reference the specific job applied to
  - Mention relevant projects from the candidate's profile
  - Include personal details about the recruiter when available
  - Request referral in a professional, non-pushy way
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("EmailDrafter")


class EmailDraftAgent:
    def __init__(self, config: dict):
        self.config = config
        self.profile = config["profile"]
        self.data_dir = Path(config["data_dir"])
        self.drafts_path = self.data_dir / "recruiter_drafts.json"
        self.gemini_key = config["api_keys"].get("gemini", "")

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
        """Generate personalized outreach email drafts."""
        existing_drafts = self._load_drafts()
        new_drafts = []

        if not self.gemini_key:
            logger.warning("   ⚠️  No Gemini API key — using template emails")
            for rd in recruiter_data:
                for person in rd.get("people", [])[:2]:  # Top 2 per company
                    draft = self._template_draft(person, rd)
                    new_drafts.append(draft)
            existing_drafts.extend(new_drafts)
            self._save_drafts(existing_drafts[-500:])
            return new_drafts

        genai_client = genai.Client(api_key=self.gemini_key)

        for rd in recruiter_data:
            # Pick top priority people
            people = sorted(
                rd.get("people", []),
                key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(
                    p.get("outreach_priority", "medium"), 1
                ),
            )[:3]

            for person in people:
                draft = await self._ai_draft(genai_client, person, rd)
                if draft:
                    new_drafts.append(draft)

        existing_drafts.extend(new_drafts)
        self._save_drafts(existing_drafts[-500:])
        return new_drafts

    async def _ai_draft(self, client, person: dict,
                        recruiter_data: dict) -> dict | None:
        """Generate an AI-powered personalized email draft."""
        # Build context about the candidate's projects
        projects_text = "\n".join([
            f"- {p['name']}: {p['description']} (Tech: {', '.join(p.get('tech', []))})"
            for p in self.profile.get("projects", [])[:3]
        ])

        experience_text = "\n".join([
            f"- {exp['title']} at {exp['company']} ({exp['duration']}): "
            + "; ".join(exp.get("highlights", [])[:2])
            for exp in self.profile.get("work_experience", [])[:2]
        ])

        talking_points = "\n".join([
            f"- {tp}" for tp in person.get("talking_points", [])
        ])

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=(
                    f"Write a professional outreach email to a recruiter/hiring manager.\n\n"
                    f"CONTEXT:\n"
                    f"- I ({self.profile['name']}) have applied to: {recruiter_data['job_title']} "
                    f"at {recruiter_data['company']}\n"
                    f"- Job URL: {recruiter_data.get('job_url', 'N/A')}\n"
                    f"- Recipient: {person['name']}, {person['role']} at {person['company']}\n"
                    f"- Recipient type: {person.get('person_type', 'unknown')}\n"
                    f"- Outreach angle: {person.get('outreach_angle', 'N/A')}\n"
                    f"- Talking points: {talking_points}\n\n"
                    f"MY BACKGROUND:\n"
                    f"- Skills: {', '.join(self.profile['skills'][:15])}\n"
                    f"- Experience: {experience_text}\n"
                    f"- Exciting projects:\n{projects_text}\n"
                    f"- LinkedIn: {self.profile.get('linkedin_url', 'N/A')}\n"
                    f"- GitHub: {self.profile.get('github_url', 'N/A')}\n"
                    f"- Portfolio: {self.profile.get('portfolio_url', 'N/A')}\n\n"
                    f"REQUIREMENTS:\n"
                    f"- Subject line + email body\n"
                    f"- Professional but warm tone, NOT generic/spammy\n"
                    f"- Mention 1-2 specific projects that are relevant to the company\n"
                    f"- If the person is a recruiter, ask for consideration/referral\n"
                    f"- If the person is a hiring manager/engineer, express genuine interest "
                    f"in the team's work and ask to chat\n"
                    f"- Keep it under 200 words\n"
                    f"- End with a clear, low-pressure call to action\n\n"
                    f"Return as JSON with 'subject' and 'body' keys only. No markdown."
                ),
                config=genai_types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1000,
                    response_mime_type="application/json",
                ),
            )

            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            email_data = json.loads(text)

            return {
                "id": f"{person['company']}_{person['name']}".replace(" ", "_").lower(),
                "recipient_name": person["name"],
                "recipient_role": person["role"],
                "recipient_linkedin": person.get("linkedin_url", ""),
                "recipient_email": person.get("email", ""),
                "email_guessed": person.get("email_guessed", False),
                "company": person["company"],
                "job_title": recruiter_data["job_title"],
                "job_url": recruiter_data.get("job_url", ""),
                "subject": email_data.get("subject", ""),
                "body": email_data.get("body", ""),
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "outreach_priority": person.get("outreach_priority", "medium"),
            }

        except Exception as e:
            logger.warning(f"   AI draft failed for {person['name']}: {e}")
            return self._template_draft(person, recruiter_data)

    def _template_draft(self, person: dict, recruiter_data: dict) -> dict:
        """Fallback template-based email draft."""
        projects = self.profile.get("projects", [])
        project_mentions = ""
        if projects:
            p = projects[0]
            project_mentions = (
                f"I recently built {p['name']} — {p['description']}. "
                f"I'd love to bring this kind of initiative to {person['company']}."
            )

        subject = f"Re: {recruiter_data['job_title']} at {recruiter_data['company']}"
        body = (
            f"Hi {person['name'].split()[0]},\n\n"
            f"I recently applied for the {recruiter_data['job_title']} role at "
            f"{recruiter_data['company']} and wanted to reach out directly.\n\n"
            f"I'm a {self.profile.get('skills', ['software'])[0]} engineer with "
            f"{self.profile.get('experience_years', 'several')} years of experience "
            f"building production AI/ML systems. {project_mentions}\n\n"
            f"I'd welcome any chance to discuss how I can contribute to your team. "
            f"Happy to share more about my background or chat briefly at your convenience.\n\n"
            f"Best regards,\n"
            f"{self.profile['name']}\n"
            f"{self.profile.get('linkedin_url', '')}\n"
            f"{self.profile.get('github_url', '')}"
        )

        return {
            "id": f"{person['company']}_{person['name']}".replace(" ", "_").lower(),
            "recipient_name": person["name"],
            "recipient_role": person["role"],
            "recipient_linkedin": person.get("linkedin_url", ""),
            "recipient_email": person.get("email", ""),
            "email_guessed": person.get("email_guessed", False),
            "company": person["company"],
            "job_title": recruiter_data["job_title"],
            "job_url": recruiter_data.get("job_url", ""),
            "subject": subject,
            "body": body,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "outreach_priority": person.get("outreach_priority", "medium"),
        }