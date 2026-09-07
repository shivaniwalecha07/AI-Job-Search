"""LinkedIn discovery — browser-assisted, SUPERVISED only (see ARCHITECTURE.md 8.1).

Hard rules baked in:
  * requires_supervision = True  -> excluded from the unattended cron.
  * Reads only what your normal logged-in session shows; no credential handling.
  * Human-paced (page_delay_seconds); respects rate limits.
  * On ANY CAPTCHA / security challenge / interstitial: STOP and hand back to the human.
    Never attempt to solve or evade it (constraint #23-#5).

STATUS: stub. Implement fetch() in Phase 3 using the browser-automation layer while the
user is present and logged in.
"""
from __future__ import annotations

from datetime import datetime

from job_agent.connectors.base import BaseConnector, register
from job_agent.schemas.core import RawJobRecord, SourceHealth


class SupervisionRequiredError(RuntimeError):
    """Raised if a supervised connector is invoked in the unattended lane."""


@register("linkedin_supervised")
class LinkedInSupervisedConnector(BaseConnector):
    requires_supervision = True

    def fetch(self, since: datetime | None = None) -> list[RawJobRecord]:
        raise NotImplementedError(
            "LinkedInSupervisedConnector.fetch — Phase 3. Browser-assisted, human-present. "
            "Halt on any challenge; never bypass. See ARCHITECTURE.md 8.1."
        )

    def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id, ok=True, detail="supervised; run only when present + logged in"
        )
