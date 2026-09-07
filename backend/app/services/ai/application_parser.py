from __future__ import annotations

import re

from app.schemas.ai import ParsedApplicationEmail
from app.utils.normalization import canonical_status


class ApplicationParser:
    def parse_preview(self, text: str) -> ParsedApplicationEmail:
        lowered = text.lower()
        status = "saved"
        if any(word in lowered for word in ["interview", "面试"]):
            status = "interview"
        elif any(word in lowered for word in ["online assessment", "oa", "测评", "笔试"]):
            status = "oa"
        elif any(word in lowered for word in ["offer", "录用"]):
            status = "offer"
        elif any(word in lowered for word in ["reject", "unfortunately", "拒"]):
            status = "rejected"

        date_match = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", text)
        company_match = re.search(r"(?:from|来自|公司)[:： ]+([A-Za-z0-9\u4e00-\u9fff .,&-]{2,40})", text, re.I)
        return ParsedApplicationEmail(
            company=company_match.group(1).strip() if company_match else None,
            status=canonical_status(status),
            interview_date=date_match.group(1).replace("/", "-").replace(".", "-") if status == "interview" and date_match else None,
            deadline=date_match.group(1).replace("/", "-").replace(".", "-") if status != "interview" and date_match else None,
            confidence=0.55 if company_match else 0.35,
        )


application_parser = ApplicationParser()
