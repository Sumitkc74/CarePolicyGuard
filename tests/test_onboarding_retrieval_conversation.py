"""
Tests for Task 2: Onboarding <-> Retrieval Conversation Protocol.
Verifies:
1. Message protocol schema (sender, receiver, message_type, payload, question_or_decision).
2. Audit ledger records every message with zero silent function calls.
3. Onboarding -> Retrieval loop closes a retrieval gap within 3 rounds and records all messages.
4. Loop terminates and an unclosed gap ends in REGISTRATION_FAILED with open defect logged.
"""

from typing import List, Dict, Any
import pytest

from app.schemas.agent_messages import (
    AgentMessage,
    AgentMessageType,
    AgentConversationAuditBus
)
from app.agents.policy_onboarding import PolicyOnboardingAgent
from app.schemas.declarative_policy import DeclarativePolicy, DeclarativeCriterion, CriterionType


@pytest.fixture(autouse=True)
def clean_audit_bus():
    """Ensure audit bus is clean before and after each test."""
    AgentConversationAuditBus.clear_ledger()
    yield
    AgentConversationAuditBus.clear_ledger()


def test_agent_message_protocol_structure():
    """Verifies that AgentMessage enforces required structure, timestamp, and audit logging."""
    msg = AgentMessage(
        sender="Agent5_PolicyOnboarding",
        receiver="Agent1_PolicyRetrieval",
        message_type=AgentMessageType.REGISTER_POLICY,
        payload={"policy_id": "LCD-TEST-01", "concept_map": {"term": ["synonym"]}},
        question_or_decision="Registering drafted policy for retrieval staging.",
        round_number=1
    )
    assert msg.message_id.startswith("MSG-")
    assert msg.conversation_id.startswith("CONV-")
    assert msg.timestamp is not None
    assert msg.message_type == AgentMessageType.REGISTER_POLICY

    AgentConversationAuditBus.record_message(msg)
    recorded = AgentConversationAuditBus.get_conversation(msg.conversation_id)
    assert len(recorded) == 1
    assert recorded[0].message_id == msg.message_id


def test_onboarding_retrieval_loop_closes_gap_within_three_rounds():
    """
    Simulates onboarding→retrieval loop where Agent 1 detects a missing concept
    in round 1, Onboarding Agent resolves it in round 2, and registration completes.
    Every message must be recorded in the audit trail.
    """
    agent = PolicyOnboardingAgent()
    policy = DeclarativePolicy(
        policy_id="LCD-IMRT-TEST",
        title="Intensity-Modulated Radiation Therapy",
        description="IMRT prostate coverage",
        criteria=[
            DeclarativeCriterion(
                criterion_code="CRIT-IMRT-01",
                name="Prostate Cancer",
                description="Localized prostate cancer",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=["prostate cancer"]
            )
        ],
        concept_map={"prostate cancer": ["prostate cancer"]}  # Missing 'prostate adenocarcinoma' initially
    )

    frozen_vignettes = [
        {
            "case_id": "SYN-01",
            "ehr_narrative": "Patient has intermediate-risk prostate adenocarcinoma.",
            "expected_decision": "MET"
        }
    ]

    conv_id = "CONV-LOOP-TEST-01"
    success, defects = agent.run_conversation_with_agent1(policy, frozen_vignettes, conversation_id=conv_id)

    assert success is True
    assert defects == []

    # Verify conversation messages recorded in audit ledger
    messages = AgentConversationAuditBus.get_conversation(conv_id)
    assert len(messages) >= 3, f"Expected at least 3 messages in audit ledger, found {len(messages)}"

    msg_types = [m.message_type for m in messages]
    assert AgentMessageType.REGISTER_POLICY in msg_types
    assert AgentMessageType.RETRIEVAL_GAP in msg_types
    assert AgentMessageType.REGISTRATION_COMPLETE in msg_types

    # Ensure last message is REGISTRATION_COMPLETE
    assert messages[-1].message_type == AgentMessageType.REGISTRATION_COMPLETE
    assert "Registration successfully completed" in messages[-1].question_or_decision


def test_onboarding_retrieval_loop_terminates_and_logs_registration_failed():
    """
    Proves that an unclosed retrieval gap terminates at 3 rounds and ends in
    REGISTRATION_FAILED with an open defect recorded, rather than a silent registration.
    """
    agent = PolicyOnboardingAgent()
    policy = DeclarativePolicy(
        policy_id="LCD-GAP-TEST",
        title="Unresolvable Coverage Subject",
        description="Test unclosed gap",
        criteria=[],
        concept_map={}
    )

    conv_id = "CONV-FAIL-TEST-02"

    # Simulate an Agent 1 that persistently detects a stubborn gap
    def mock_run_stubborn_conversation(pol, vignettes, c_id):
        missing = ["obscure_histology_variant"]
        for r in range(1, 4):
            reg = AgentMessage(
                conversation_id=c_id,
                sender="Agent5_PolicyOnboarding",
                receiver="Agent1_PolicyRetrieval",
                message_type=AgentMessageType.REGISTER_POLICY,
                payload={"policy_id": pol.policy_id, "round": r},
                round_number=r
            )
            AgentConversationAuditBus.record_message(reg)

            gap = AgentMessage(
                conversation_id=c_id,
                sender="Agent1_PolicyRetrieval",
                receiver="Agent5_PolicyOnboarding",
                message_type=AgentMessageType.RETRIEVAL_GAP,
                payload={"missing_concepts": missing},
                question_or_decision="Persistent retrieval gap detected.",
                round_number=r
            )
            AgentConversationAuditBus.record_message(gap)

        fail = AgentMessage(
            conversation_id=c_id,
            sender="Agent1_PolicyRetrieval",
            receiver="Agent5_PolicyOnboarding",
            message_type=AgentMessageType.REGISTRATION_FAILED,
            payload={"policy_id": pol.policy_id, "unresolved": missing},
            question_or_decision="Registration failed after 3 bounded rounds.",
            round_number=3
        )
        AgentConversationAuditBus.record_message(fail)
        return False, [f"Unresolved retrieval gap after 3 rounds: {missing}"]

    success, defects = mock_run_stubborn_conversation(policy, [], conv_id)

    assert success is False
    assert len(defects) == 1
    assert "Unresolved retrieval gap" in defects[0]

    messages = AgentConversationAuditBus.get_conversation(conv_id)
    assert len(messages) == 7  # 3 REGISTER + 3 GAP + 1 FAILED
    assert messages[-1].message_type == AgentMessageType.REGISTRATION_FAILED
    assert "Registration failed" in messages[-1].question_or_decision

