from __future__ import annotations

from app.services.ai.client import ai_client
from app.schemas.skills import DetectedResumeInformation


class ResumeSkillExtractor:
    def extract(self, resume_text: str) -> DetectedResumeInformation:
        return ai_client.structured_completion(
            prompt_name="resume_skill_extractor",
            schema=DetectedResumeInformation,
            payload={"resume_text": resume_text},
        )


resume_skill_extractor = ResumeSkillExtractor()
