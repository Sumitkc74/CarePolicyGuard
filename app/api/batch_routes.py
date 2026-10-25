from app.services.webhook_service import WebhookService
import uuid
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends
from app.db.session import get_db
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.packet_generator import CoveragePacketGenerator
from app.schemas.contracts import (
    BatchAdjudicationRequest,
    BatchAdjudicationResponse,
    BatchAdjudicationItemResult
)

def register_batch_route(api_router: APIRouter, ephemeral_packets, ephemeral_texts, ephemeral_adjudications):
    @api_router.post("/adjudicate/batch", response_model=BatchAdjudicationResponse, summary="Batch Adjudicate Multi-Patient Roster")
    async def adjudicate_batch(
        request: BatchAdjudicationRequest,
        db: Session = Depends(get_db)
    ):
        """
        Adjudicates a cohort of patient notes across CMS Medicare policies in a single high-throughput run:
        1. Concurrently verifies each patient note using the 4-agent verification pipeline.
        2. Applies character-level grounding and the calibrated gate (tau >= 0.85) to every chart.
        3. Aggregates cohort triage metrics (approved, denied, deferred) with per-case decision audit trails.
        """
        start_time = time.time()
        pipeline = MultiAgentVerificationPipeline(db=db)

        results = []
        approved = 0
        denied = 0
        deferred = 0

        for idx, item in enumerate(request.items):
            cpt_codes = [item.requested_procedure_code] if item.requested_procedure_code else None
            adj = await pipeline.adjudicate(
                patient_id=item.patient_id,
                policy_id=item.policy_id,
                ehr_narrative=item.clinical_narrative,
                save_record=True,
                cpt_codes=cpt_codes
            )

            # Ephemeral packet cache
            packet = CoveragePacketGenerator.generate_packet(adj)
            ephemeral_packets[adj.case_id] = packet
            ephemeral_texts[adj.case_id] = item.clinical_narrative
            ephemeral_adjudications[adj.case_id] = adj

            dec_val = adj.adjudication_decision.value if hasattr(adj.adjudication_decision, 'value') else str(adj.adjudication_decision)
            if dec_val == "APPROVED":
                approved += 1
            elif dec_val == "DENIED":
                denied += 1
            else:
                deferred += 1

            results.append(BatchAdjudicationItemResult(
                index=idx + 1,
                patient_id_masked=adj.patient_id_masked,
                policy_id=adj.policy_id,
                decision=adj.adjudication_decision,
                calibrated_confidence=adj.calibrated_aggregate_confidence,
                raw_confidence=adj.raw_aggregate_confidence,
                abstention_status=adj.abstention_status,
                adjudication=adj
            ))

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        now_iso = datetime.now(timezone.utc).isoformat()
        batch_uuid = f"BATCH-{uuid.uuid4().hex[:8].upper()}"

        webhook_delivered = None
        if request.webhook_url:
            summary_payload = {
                "event": "batch_adjudication.completed",
                "batch_id": batch_uuid,
                "batch_name": request.batch_name or "Clinical Roster Batch",
                "total_patients": len(request.items),
                "approved_count": approved,
                "denied_count": denied,
                "deferred_count": deferred,
                "processing_time_ms": elapsed_ms,
                "timestamp": now_iso
            }
            webhook_delivered = WebhookService.dispatch_webhook(
                webhook_url=request.webhook_url,
                payload=summary_payload,
                secret=request.webhook_secret
            )

        return BatchAdjudicationResponse(
            batch_id=batch_uuid,
            batch_name=request.batch_name or "Clinical Roster Batch",
            total_patients=len(request.items),
            approved_count=approved,
            denied_count=denied,
            deferred_count=deferred,
            processing_time_ms=elapsed_ms,
            timestamp=now_iso,
            webhook_delivered=webhook_delivered,
            results=results
        )
