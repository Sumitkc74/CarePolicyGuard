"""
Structured Message Board for Autonomous Multi-Agent Case Adjudication (Task 1).
Provides a shared, chronological, auditable communication ledger where Agent 1,
Agent 2, Agent 3, and Agent 4 publish and consume all decision-relevant actions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.contracts import ClinicalEvidenceSpan


class BoardMessageType(str, Enum):
    """Recognized message types on the shared case message board."""
    POLICY_SHORTLIST = "POLICY_SHORTLIST"
    POLICY_CHOSEN = "POLICY_CHOSEN"
    POLICY_SELECTED = "POLICY_SELECTED"
    PLAN = "PLAN"
    ASSESSMENT_PROPOSED = "ASSESSMENT_PROPOSED"
    JUDGMENT = "JUDGMENT"
    CHALLENGE = "CHALLENGE"
    DEFENSE = "DEFENSE"
    CONCEDE = "CONCEDE"
    VERDICT = "VERDICT"
    HALT = "HALT"
    DECISION = "DECISION"


class BoardMessage(BaseModel):
    """
    An individual immutable entry on the shared case message board.
    Every message records who sent it, its semantic type, the affected criterion,
    grounded evidence references, and a human-readable explanation.
    """
    sequence_number: int = Field(..., description="Monotonically increasing 1-based sequence index")
    message_id: str = Field(default_factory=lambda: f"MSG-{uuid.uuid4().hex[:10].upper()}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str = Field(..., description="Identity of sending agent (e.g., 'Agent 1: Policy Retrieval')")
    message_type: BoardMessageType = Field(..., description="Operational message type")
    criterion_code: str | None = Field(default=None, description="Affected criterion code if applicable")
    evidence: dict[str, Any] | None = Field(default=None, description="Grounded evidence span or slice reference")
    content: str = Field(..., description="Decision-relevant narrative explaining this action")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Operational flags, scores, or gate telemetry")


class CaseMessageBoard(BaseModel):
    """
    Per-case shared message board.
    Persisted alongside FinalAdjudication so that clinicians or auditors
    can replay and read the exact inter-agent deliberation sequence.
    """
    case_id: str = Field(..., description="Case identifier")
    messages: list[BoardMessage] = Field(default_factory=list, description="Chronological board messages")
    next_seq: int = Field(default=1, description="Next sequence number")

    @property
    def total_messages(self) -> int:
        """Returns the total number of messages on the board."""
        return len(self.messages)

    def post(
        self,
        agent: str,
        message_type: BoardMessageType | str,
        content: str,
        criterion_code: str | None = None,
        evidence: dict[str, Any] | ClinicalEvidenceSpan | None = None,
        metadata: dict[str, Any] | None = None
    ) -> BoardMessage:
        """Publishes a new message to the shared board."""
        if isinstance(message_type, str):
            message_type = BoardMessageType(message_type)

        ev_dict = None
        if evidence is not None:
            if hasattr(evidence, "model_dump"):
                ev_dict = evidence.model_dump()
            elif isinstance(evidence, dict):
                ev_dict = evidence
            else:
                ev_dict = {"source_text": str(evidence)}

        msg = BoardMessage(
            sequence_number=self.next_seq,
            agent=agent,
            message_type=message_type,
            criterion_code=criterion_code,
            evidence=ev_dict,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(msg)
        self.next_seq += 1
        return msg

    def get_messages(
        self,
        criterion_code: str | None = None,
        message_type: BoardMessageType | None = None,
        agent: str | None = None
    ) -> list[BoardMessage]:
        """Filters board messages by criterion, message type, or agent."""
        res = self.messages
        if criterion_code:
            res = [m for m in res if m.criterion_code == criterion_code]
        if message_type:
            res = [m for m in res if m.message_type == message_type]
        if agent:
            res = [m for m in res if m.agent == agent]
        return res

    def render_transcript(self) -> str:
        """
        Renders an auditable human-readable chronological transcript of the board.
        A human reading this transcript can follow the whole conversation
        without opening the underlying source code.
        """
        lines = [
            "=" * 80,
            f"SHARED CASE MESSAGE BOARD TRANSCRIPT [Case ID: {self.case_id}]",
            "=" * 80
        ]
        for m in self.messages:
            crit_clause = f" | Criterion: {m.criterion_code}" if m.criterion_code else ""
            lines.append(f"\n[#{m.sequence_number:02d}] [{m.agent}] -> {m.message_type.value}{crit_clause}")
            lines.append(f"     Content:  {m.content}")
            if m.evidence:
                src = m.evidence.get("source_text") or m.evidence.get("text")
                start = m.evidence.get("start_char")
                end = m.evidence.get("end_char")
                offsets = f" [{start}:{end}]" if start is not None and end is not None else ""
                lines.append(f"     Evidence: \"{src}\"{offsets}")
            if m.metadata:
                items_str = ", ".join(f"{k}={v}" for k, v in m.metadata.items() if k != "full_audit")
                if items_str:
                    lines.append(f"     Metadata: {items_str}")
        lines.append("\n" + "=" * 80)
        return "\n".join(lines)

    def to_records(self) -> list[dict[str, Any]]:
        """Serializes board messages for JSON persistence in FinalAdjudication."""
        return [m.model_dump(mode="json") for m in self.messages]
