from app.services.webhook_service import WebhookService
import uuid
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import csv
import json
import io
import re
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
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
    @api_router.post("/adjudicate/batch/upload-parse", summary="Parse Uploaded Batch Roster Files (CSV, JSON, Multi-Page PDFs, or Scanned Images)")
    async def parse_batch_upload(
        files: List[UploadFile] = File(...),
        db: Session = Depends(get_db)
    ):
        """
        Ingests multi-patient files for batch verification:
        - .csv: Ingests spreadsheets with patient_id, policy_id, procedure_code, clinical_narrative columns.
        - .json: Ingests cohort JSON arrays.
        - .pdf, images (.png/.jpg/.tiff), .docx: Extracts multi-page text and applies OCR on scanned pages, auto-generating cohort cases.
        """
        from app.api.routes import extract_text_from_upload, validate_and_sanitize_upload
        from app.agents.policy_retriever import PolicyRetrievalAgent

        if not files:
            raise HTTPException(status_code=400, detail="No files provided for batch roster ingestion.")

        retriever = PolicyRetrievalAgent(db=db)
        items = []

        for f_idx, f in enumerate(files, 1):
            content = await f.read()
            fn = f.filename.lower()

            if fn.endswith(".csv"):
                text_content = content.decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(text_content))
                for row_idx, row in enumerate(reader, 1):
                    row_lower = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                    patient_id = (
                        row_lower.get("patient_id") or
                        row_lower.get("patient") or
                        row_lower.get("mrn") or
                        f"PT-CSV-{row_idx:03d}"
                    )
                    policy_id = (
                        row_lower.get("policy_id") or
                        row_lower.get("policy") or
                        row_lower.get("ncd") or
                        row_lower.get("lcd") or
                        "NCD-20.4"
                    )
                    cpt = (
                        row_lower.get("requested_procedure_code") or
                        row_lower.get("procedure_code") or
                        row_lower.get("cpt") or
                        row_lower.get("cpt_code") or
                        "33249"
                    )
                    narrative = (
                        row_lower.get("clinical_narrative") or
                        row_lower.get("narrative") or
                        row_lower.get("notes") or
                        row_lower.get("chart") or
                        row_lower.get("text") or
                        ""
                    )
                    if narrative:
                        items.append({
                            "patient_id": patient_id,
                            "policy_id": policy_id,
                            "requested_procedure_code": cpt,
                            "clinical_narrative": narrative
                        })

            elif fn.endswith(".json"):
                try:
                    data = json.loads(content.decode("utf-8", errors="replace"))
                    raw_items = data if isinstance(data, list) else data.get("items", [])
                    for r_idx, item in enumerate(raw_items, 1):
                        items.append({
                            "patient_id": item.get("patient_id") or f"PT-JSON-{r_idx:03d}",
                            "policy_id": item.get("policy_id") or "NCD-20.4",
                            "requested_procedure_code": item.get("requested_procedure_code") or "33249",
                            "clinical_narrative": item.get("clinical_narrative") or item.get("notes") or ""
                        })
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON format in {f.filename}: {str(e)}")

            else:
                # PDF, image, DOCX, or text file
                safe_name = validate_and_sanitize_upload(f.filename, content)
                extracted_text = extract_text_from_upload(safe_name, content)
                if not extracted_text or len(extracted_text.strip()) < 10:
                    continue

                candidates = retriever.search_policies_by_narrative(extracted_text)
                policy_id = candidates[0]["policy_id"] if candidates and candidates[0]["relevance_score"] > 0.05 else "NCD-20.4"

                pt_match = re.search(r'\b(PT-[\w-]+|Patient ID:\s*[\w-]+|MRN:\s*[\w-]+)\b', extracted_text, re.IGNORECASE)
                if pt_match:
                    raw_id = pt_match.group(0).split(":")[-1].strip()
                    patient_id = raw_id if raw_id.startswith("PT-") else f"PT-{raw_id}"
                else:
                    clean_fn = re.sub(r'[^a-zA-Z0-9]', '', f.filename.split('.')[0])[:8].upper()
                    patient_id = f"PT-{clean_fn or f'{f_idx:03d}'}"

                cpt_match = re.search(r'\b(33249|33206|33207|33208|33289|93580|E0601|G0277)\b', extracted_text)
                cpt_code = cpt_match.group(0) if cpt_match else "33249"

                items.append({
                    "patient_id": patient_id,
                    "policy_id": policy_id,
                    "requested_procedure_code": cpt_code,
                    "clinical_narrative": extracted_text
                })

        if not items:
            raise HTTPException(status_code=400, detail="No valid clinical patient records could be extracted from the uploaded files.")

        return {
            "batch_name": f"Uploaded Cohort ({len(items)} Patients)",
            "total_patients": len(items),
            "items": items
        }

