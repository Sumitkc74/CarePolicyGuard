"""
Shared Authorization and Release Workflow Controls (v76).
Centralizes the determination release gate and coverage packet synchronization
to guarantee a single source of truth across all export and submission paths.
"""

from typing import Any

from fastapi import HTTPException, status

from app.schemas.contracts import CMSCoveragePacket, FinalAdjudication


def require_releasable_determination(
    target: Any,
    log: Any | None = None,
    adjudication: Any | None = None,
) -> None:
    """
    Enforces the single shared release gate across all release paths:
    determination_stage == 'FINAL' AND is_releasable is True AND human_sign_off_status in ('SIGNED_OFF', 'OVERRIDDEN_FINAL').
    Raises HTTP 412 Precondition Failed naming the missing condition(s) if not satisfied.
    """
    stage = getattr(target, "determination_stage", None)
    is_releasable = getattr(target, "is_releasable", None)
    sign_off_status = getattr(target, "human_sign_off_status", None)

    # Fallback to log or adjudication if attribute not present on target
    if stage is None and log is not None:
        stage = getattr(log, "determination_stage", None)
    if stage is None and adjudication is not None:
        stage = getattr(adjudication, "determination_stage", None)

    if is_releasable is None and log is not None:
        is_releasable = getattr(log, "is_releasable", None)
    if is_releasable is None and adjudication is not None:
        is_releasable = getattr(adjudication, "is_releasable", None)

    if sign_off_status is None and log is not None:
        sign_off_status = getattr(log, "human_sign_off_status", None)
    if sign_off_status is None and adjudication is not None:
        sign_off_status = getattr(adjudication, "human_sign_off_status", None)

    # Check conditions
    missing: list[str] = []
    if stage != "FINAL":
        missing.append(f"determination_stage must be 'FINAL' (found '{stage or 'PROVISIONAL'}')")
    if not is_releasable:
        missing.append("is_releasable must be True")
    if sign_off_status not in ("SIGNED_OFF", "OVERRIDDEN_FINAL"):
        missing.append(f"human_sign_off_status must be 'SIGNED_OFF' or 'OVERRIDDEN_FINAL' (found '{sign_off_status or 'PENDING_SIGN_OFF'}')")

    if missing:
        missing_str = "; ".join(missing)
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=f"Determination is PROVISIONAL and cannot be released or exported as final without recorded human sign-off. Missing release conditions: {missing_str}."
        )


def rebuild_coverage_packet(
    adjudication: FinalAdjudication,
    existing_packet: CMSCoveragePacket | None = None,
) -> CMSCoveragePacket:
    """
    Task 3: Rebuilds the CMSCoveragePacket from the authoritative FinalAdjudication record
    so that decision, lifecycle stage, releasable status, and human sign-off status
    are consistently reflected in the packet cache and persistence.
    """
    from app.agents.packet_generator import CoveragePacketGenerator

    packet = CoveragePacketGenerator.generate_packet(adjudication)

    # If adjudication has an active human override, ensure the decision reflects the override
    if getattr(adjudication, "human_override", None) and isinstance(adjudication.human_override, dict):
        ovr_dec = adjudication.human_override.get("override_decision")
        if ovr_dec:
            packet.adjudication_decision = ovr_dec
        else:
            packet.adjudication_decision = adjudication.adjudication_decision.value
    else:
        packet.adjudication_decision = adjudication.adjudication_decision.value

    packet.determination_stage = adjudication.determination_stage
    packet.is_releasable = adjudication.is_releasable
    packet.human_sign_off_status = adjudication.human_sign_off_status
    packet.signed_by = adjudication.signed_off_by
    packet.signed_at = adjudication.signed_off_at
    if adjudication.required_clinician_action_notes:
        packet.clinician_action_notes = adjudication.required_clinician_action_notes

    if existing_packet:
        if getattr(existing_packet, "submission_status", None):
            packet.submission_status = existing_packet.submission_status
        if getattr(existing_packet, "payer_transaction_id", None):
            packet.payer_transaction_id = existing_packet.payer_transaction_id

    return packet
