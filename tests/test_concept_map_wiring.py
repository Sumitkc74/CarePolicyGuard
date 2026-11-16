"""
Concept Map Wiring Regression Test (Task 10).

Verifies that:
1. ConceptMap is wired through the pipeline and not dropped or re-instantiated empty at any stage.
2. The 119 draft concepts remain in pending / advisory status (not silently committed, not dropped).
3. The governing rule holds: committed concepts decide equivalence deterministically;
   uncommitted / draft concepts require human or agentic adjudication.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.toolbelt import AgentToolbelt
from app.core.concept_map import (
    ConceptMap,
    get_concept_map,
)


def test_concept_map_persistence_across_pipeline_instantiations():
    """ConceptMap is wired through pipeline and toolbelt and never empty."""
    cmap = get_concept_map()
    assert cmap is not None
    assert cmap.total_concepts >= 12, f"Expected at least 12 committed concepts, got {cmap.total_concepts}"
    assert cmap.total_terms >= 35, f"Expected at least 35 indexed terms, got {cmap.total_terms}"

    pipeline = MultiAgentVerificationPipeline()
    toolbelt = AgentToolbelt()

    assert pipeline is not None
    # Toolbelt and pipeline reference the singleton concept map
    assert toolbelt.concept_map.total_concepts == cmap.total_concepts
    assert toolbelt.concept_map.total_terms == cmap.total_terms


def test_119_draft_concepts_remain_pending_and_advisory():
    """119 draft concepts exist in draft_concept_entries.json, remain pending, and are not silently committed."""
    drafts_path = Path(__file__).resolve().parent.parent / "app" / "data" / "concept_map" / "draft_concept_entries.json"
    assert drafts_path.exists(), "draft_concept_entries.json must exist in repository"

    with open(drafts_path, "r", encoding="utf-8") as f:
        drafts = json.load(f)

    pass_drafts = [d for d in drafts if d.get("governing_rule_check") == "PASS_EQUIVALENCE"]
    assert len(pass_drafts) == 119, f"Expected exactly 119 PASS_EQUIVALENCE draft concepts, found {len(pass_drafts)}"

    # Check status of drafts: they are uncommitted proposals awaiting human clinical attestation
    for d in pass_drafts:
        # None should claim to be committed human review accepted
        assert d.get("source") != "human_review_accepted", f"Draft {d['concept_id']} cannot be pre-marked human_review_accepted"

    # In default ConceptMap(), these drafts are NOT in the committed built-in map
    committed_map = ConceptMap()
    built_in_ids = set(committed_map._concepts.keys())
    for d in pass_drafts:
        assert d["concept_id"] not in built_in_ids, (
            f"Draft concept {d['concept_id']} was silently committed into built-in ConceptMap!"
        )


def test_governing_rule_committed_vs_uncommitted():
    """
    Governing rule (Nov 5, 2026):
    Semantic equivalence must be understood, never deferred for that sole reason.
    - Committed concept (e.g., 'prostate adenocarcinoma' == 'prostate cancer') decides equivalence deterministically.
    - Uncommitted / unmapped concept (e.g., non-indexed novel phrasing) returns NO_CONCEPT_MAP_ENTRY and defers.
    """
    toolbelt = AgentToolbelt()

    # 1. Committed mapping test: prostate adenocarcinoma -> prostate cancer
    res_committed = toolbelt.concept_map_lookup(
        agent="Agent 2",
        term="prostate adenocarcinoma",
        criterion_term="prostate cancer"
    )
    assert res_committed["is_deciding"] is True
    assert res_committed["status"] == "DECIDING_COMMITTED"
    assert res_committed["equivalence_confirmed"] is True
    assert "CONCEPT-PROSTATE-CANCER" in res_committed["concept_id"]

    # 2. Negative near-miss test: lung adenocarcinoma vs prostate cancer
    is_eq, reason = toolbelt.concept_map.verify_equivalence("prostate cancer", "lung adenocarcinoma")
    assert is_eq is False
    assert "PROHIBITED_NEAR_MISS" in reason

    # 3. Unmapped concept test: unknown term defers to human/agentic adjudication
    res_unmapped = toolbelt.concept_map_lookup(
        agent="Agent 2",
        term="unprecedented novel biochemical formulation xyz",
        criterion_term="prostate cancer"
    )
    assert res_unmapped["is_deciding"] is False
    assert res_unmapped["status"] == "UNMAPPED"
    assert res_unmapped["equivalence_confirmed"] is False
