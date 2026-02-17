"""Configuration loader for JobHunter AI."""

import os
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent


def load_config() -> dict:
    """Load and merge all configuration sources."""

    # Load profile
    profile_path = CONFIG_DIR / "profile.yaml"
    with open(profile_path, "r") as f:
        profile_data = yaml.safe_load(f)

    # Load startups list
    startups_path = CONFIG_DIR / "startups.yaml"
    startups = []
    if startups_path.exists():
        with open(startups_path, "r") as f:
            startups_data = yaml.safe_load(f)
            startups = startups_data.get("startups", [])

    # Environment variable overrides (for GitHub Actions secrets)
    config = {
        "profile": {
            "name": os.getenv("JH_NAME", profile_data.get("name", "")),
            "email": os.getenv("JH_EMAIL", profile_data.get("email", "rithviksit@gmail.com")),
            "phone": os.getenv("JH_PHONE", profile_data.get("phone", "")),
            "location": os.getenv("JH_LOCATION", profile_data.get("location", "")),
            "target_roles": profile_data.get("target_roles", []),
            "target_keywords": profile_data.get("target_keywords", []),
            "experience_years": profile_data.get("experience_years", 0),
            "skills": profile_data.get("skills", []),
            "education": profile_data.get("education", []),
            "work_experience": profile_data.get("work_experience", []),
            "projects": profile_data.get("projects", []),
            "resume_url": profile_data.get("resume_url", ""),
            "linkedin_url": profile_data.get("linkedin_url", ""),
            "github_url": profile_data.get("github_url", ""),
            "portfolio_url": profile_data.get("portfolio_url", ""),
            "preferred_locations": profile_data.get("preferred_locations", []),
            "remote_ok": profile_data.get("remote_ok", True),
            "min_salary": profile_data.get("min_salary", 0),
            "visa_required": profile_data.get("visa_required", False),
        },
        "startups": startups,
        "search": profile_data.get("search", {}),
        "api_keys": {
            "gemini": os.getenv("GEMINI_API_KEY", ""),
            "serper": os.getenv("SERPER_API_KEY", ""),  # Google search API
            "smtp_password": os.getenv("SMTP_PASSWORD", ""),
            "smtp_email": os.getenv("SMTP_EMAIL", ""),
        },
        "data_dir": str(PROJECT_ROOT / "data"),
    }

    return config
