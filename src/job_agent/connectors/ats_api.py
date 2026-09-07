"""ATS public JSON API connector (Phase 1). Greenhouse / Lever / Ashby expose public
job endpoints meant for consumption (no scraping):

  Greenhouse: https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
  Lever:      https://api.lever.co/v0/postings/{company}?mode=json
  Ashby:      https://api.ashbyhq.com/posting-api/job-board/{board}

STATUS: stub. Implement fetch() per platform in Phase 1.
"""
from __future__ import annotations

from datetime import datetime

from job_agent.connectors.base import BaseConnector, register
from job_agent.schemas.core import RawJobRecord, SourceHealth


@register("ats_api")
class AtsApiConnector(BaseConnector):
    requires_supervision = False

    def fetch(self, since: datetime | None = None) -> list[RawJobRecord]:
        raise NotImplementedError(
            "AtsApiConnector.fetch — Phase 1. Call the platform's public jobs endpoint. "
            "See ARCHITECTURE.md 8."
        )

    def health(self) -> SourceHealth:
        platform = self.params.get("platform", "?")
        return SourceHealth(source_id=self.source_id, ok=True, detail=f"platform={platform}")
