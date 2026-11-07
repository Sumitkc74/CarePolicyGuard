"""
Structured Multi-Agent Message Protocol for Agent-to-Agent Communications.
Shared module defining message contracts, conversation bus, and audit ledger.
To be extended by run-time conversations in prompt v22b.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class AgentMessageType(str, Enum):
    """Enumeration of recognized agent-to-agent message types."""
    REGISTER_POLICY = "REGISTER_POLICY"
    RETRIEVAL_SELF_TEST = "RETRIEVAL_SELF_TEST"
    RETRIEVAL_GAP = "RETRIEVAL_GAP"
    REGISTRATION_COMPLETE = "REGISTRATION_COMPLETE"
    REGISTRATION_FAILED = "REGISTRATION_FAILED"
    # General extensible types for v22b
    QUERY = "QUERY"
    INFORM = "INFORM"
    PROPOSE = "PROPOSE"
    CHALLENGE = "CHALLENGE"
    CONCEDE = "CONCEDE"
    DEBATE_ROUND = "DEBATE_ROUND"


class AgentMessage(BaseModel):
    """
    Structured message exchanged between micro-agents in the CarePolicyGuard system.
    Every inter-agent decision, handoff, or challenge is recorded as an AgentMessage.
    """
    message_id: str = Field(default_factory=lambda: f"MSG-{uuid.uuid4().hex[:12].upper()}")
    conversation_id: str = Field(default_factory=lambda: f"CONV-{uuid.uuid4().hex[:8].upper()}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sender: str = Field(..., description="Identity of sending agent, e.g. Agent5_PolicyOnboarding")
    receiver: str = Field(..., description="Identity of receiving agent, e.g. Agent1_PolicyRetrieval")
    message_type: AgentMessageType = Field(..., description="Operational message type")
    payload: dict[str, Any] = Field(default_factory=dict, description="Structured message content")
    question_or_decision: str | None = Field(
        default=None,
        description="Explicit question, decision, or justification carried by this message"
    )
    round_number: int = Field(default=1, description="Round number for bounded iterative conversations")


class AgentConversationAuditBus:
    """
    Audit ledger recording every inter-agent message.
    Ensures zero silent function calls for agentic coordination.
    """
    _LEDGER: ClassVar[list[AgentMessage]] = []

    @classmethod
    def record_message(cls, message: AgentMessage) -> AgentMessage:
        """Appends a validated agent message to the audit ledger."""
        cls._LEDGER.append(message)
        return message

    @classmethod
    def get_conversation(cls, conversation_id: str) -> list[AgentMessage]:
        """Returns all messages belonging to a conversation, ordered chronologically."""
        return [m for m in cls._LEDGER if m.conversation_id == conversation_id]

    @classmethod
    def get_messages_for_policy(cls, policy_id: str) -> list[AgentMessage]:
        """Returns all messages involving a given policy ID."""
        return [
            m for m in cls._LEDGER
            if m.payload.get("policy_id") == policy_id or m.payload.get("policy", {}).get("policy_id") == policy_id
        ]

    @classmethod
    def clear_ledger(cls) -> None:
        """Clears the ledger (for test isolation)."""
        cls._LEDGER.clear()

    @classmethod
    def all_messages(cls) -> list[AgentMessage]:
        """Returns a copy of all recorded messages."""
        return list(cls._LEDGER)

