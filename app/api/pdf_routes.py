from app.services.pdf_generator import PDFPacketGeneratorService
from app.services.appeal_generator import PeerToPeerAppealService
from fastapi import Response, HTTPException, status

def register_pdf_routes(api_router, get_coverage_packet_fn):
    @api_router.get("/packet/{case_id}/pdf", response_class=Response, summary="Download Signed CMS Coverage Packet as PDF")
    def download_coverage_packet_pdf(case_id: str):
        """
        Synthesizes an official, print-ready CMS Prior Authorization Packet in standard PDF format.
        Compliant with CMS-0057-F statutory documentation standards.
        """
        try:
            packet = get_coverage_packet_fn(case_id)
            pdf_bytes = PDFPacketGeneratorService.generate_coverage_packet_pdf(packet)
            
            headers = {
                "Content-Disposition": f'attachment; filename="CMS_Coverage_Packet_{case_id}.pdf"'
            }
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate coverage packet PDF: {str(e)}"
            )

    @api_router.get("/packet/{case_id}/appeal-letter/pdf", response_class=Response, summary="Download Peer-to-Peer Appeal Letter as PDF")
    def download_appeal_letter_pdf(case_id: str):
        """
        Synthesizes an expedited Peer-to-Peer Appeal Letter and talking points brief in standard PDF format.
        """
        try:
            packet = get_coverage_packet_fn(case_id)
            appeal = PeerToPeerAppealService.generate_appeal(packet)
            pdf_bytes = PDFPacketGeneratorService.generate_appeal_letter_pdf(appeal)
            
            headers = {
                "Content-Disposition": f'attachment; filename="Appeal_Letter_{case_id}.pdf"'
            }
            return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate appeal letter PDF: {str(e)}"
            )

