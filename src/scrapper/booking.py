"""Save → LockTerm flow. Cienki orchestrator nad LuxmedClient."""

from __future__ import annotations

import logging

from .client import LuxmedClient
from .models import LockResult, SearchContext, Term

logger = logging.getLogger(__name__)


def lock(client: LuxmedClient, term: Term, ctx: SearchContext) -> LockResult:
    logger.info("Save preflight (correlationId=%s)", ctx.correlation_id)
    client.save_availability_log(ctx)
    logger.info("LockTerm: %s, %s, %s",
                term.date_time_from.isoformat(),
                term.doctor.full_name(),
                term.facility_name)
    return client.lock_term(term, ctx)
