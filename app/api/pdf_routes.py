import logging

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.release import require_releasable_determination
from app.db.models import User
from app.db.session import get_db
from app.services.appeal_generator import PeerToPeerAppealService
from app.services.pdf_generator import PDFPacketGeneratorService

logger = logging.getLogger(__name__)


def register_pdf_routes(api_router, get_coverage_packet_fn):
    @api_router.get("/packet/{case_id}/pdf", response_class=Response, summary="Download Signed CMS Coverage Packet as PDF")
    def download_coverage_packet_pdf(
        case_id: str,
        require_final: bool = False,
        run_id: str | None = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Synthesizes an official, print-ready CMS Prior Authorization Packet in standard PDF format.
        Compliant with CMS-0057-F statutory documentation standards.
        Strictly requires authentication and case record access authorization.
        """
        try:
            from app.db.models import EvaluationRun
            from app.schemas.contracts import CMSCoveragePacket
            packet = None
            if run_id:
                run_rec = db.query(EvaluationRun).filter(EvaluationRun.case_id == case_id, EvaluationRun.run_id == run_id).first()
                if run_rec and run_rec.full_packet_json:
                    try:
                        packet = CMSCoveragePacket.model_validate_json(run_rec.full_packet_json)
                    except (ValueError, KeyError, TypeError):
                        pass
            if packet is None:
                packet = get_coverage_packet_fn(case_id, current_user, db)

            # If packet does not have human_assessment, look up HumanAssessmentRecord
            if not getattr(packet, "human_assessment", None):
                from app.db.models import HumanAssessmentRecord
                query = db.query(HumanAssessmentRecord).filter(HumanAssessmentRecord.case_id == case_id)
                if run_id:
                    query = query.filter(HumanAssessmentRecord.run_id == run_id)
                ha_rec = query.order_by(HumanAssessmentRecord.created_at.desc()).first()
                if ha_rec:
                    packet.human_assessment = {
                        "reviewer_name": ha_rec.reviewer_name or ha_rec.reviewer_username,
                        "reviewer_username": ha_rec.reviewer_username,
                        "reviewer_role": ha_rec.reviewer_role,
                        "overall_agreement": ha_rec.overall_agreement,
                        "clinical_rationale": ha_rec.clinical_rationale,
                        "created_at": ha_rec.created_at.isoformat() if hasattr(ha_rec.created_at, "isoformat") else str(ha_rec.created_at)
                    }
            if require_final:
                require_releasable_determination(packet)
            pdf_bytes = PDFPacketGeneratorService.generate_coverage_packet_pdf(packet)

            headers = {
                "Content-Disposition": f'attachment; filename="CMS_Coverage_Packet_{case_id}.pdf"'
            }
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate coverage packet PDF: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate coverage packet PDF: {e!s}"
            ) from e

    @api_router.get("/packet/{case_id}/appeal-letter/pdf", response_class=Response, summary="Download Peer-to-Peer Appeal Letter as PDF")
    def download_appeal_letter_pdf(
        case_id: str,
        require_final: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Synthesizes an expedited Peer-to-Peer Appeal Letter and talking points brief in standard PDF format.
        Strictly requires authentication and case record access authorization.
        """
        try:
            packet = get_coverage_packet_fn(case_id, current_user, db)
            if require_final:
                require_releasable_determination(packet)
            appeal = PeerToPeerAppealService.generate_appeal(packet)
            pdf_bytes = PDFPacketGeneratorService.generate_appeal_letter_pdf(appeal)

            headers = {
                "Content-Disposition": f'attachment; filename="Appeal_Letter_{case_id}.pdf"'
            }
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate appeal letter PDF: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate appeal letter PDF: {e!s}"
            ) from e
