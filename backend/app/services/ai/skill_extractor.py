from __future__ import annotations

from app.services.ai.client import ai_client
from app.schemas.skills import DetectedSkills


class ResumeSkillExtractor:
    def extract(self, resume_text: str) -> DetectedSkills:
        return ai_client.structured_completion(
            prompt_name="resume_skill_extractor",
            schema=DetectedSkills,
            payload={"resume_text": resume_text},
        )


resume_skill_extractor = ResumeSkillExtractor()
