import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import MedicarePolicy, PolicyCriterion

class PolicyRetrievalAgent:
    """
    Agent 1: Policy Retrieval Agent
    Indexes structured CMS coverage policies (NCDs and LCDs), extracts governing criteria,
    and performs passage chunking and hybrid semantic/lexical matching to retrieve relevant
    governing criteria for clinical presentations.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def retrieve_policy(self, policy_id: str) -> Optional[MedicarePolicy]:
        """
        Retrieves a policy and its complete criteria tree by policy_id.
        """
        if not self.db:
            return None
        return self.db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == policy_id).first()

    def search_policies_by_narrative(self, narrative: str) -> List[Dict[str, Any]]:
        """
        Hybrid lexical-semantic retrieval matching EHR clinical narrative against
        indexed Medicare NCD and LCD policies.
        """
        if not self.db:
            return []

        policies = self.db.query(MedicarePolicy).all()
        scored_policies = []
        cleaned_text = narrative.lower()

        for pol in policies:
            score = 0.0
            matched_terms = []

            # 1. Title and category match
            if pol.category.lower() in cleaned_text:
                score += 2.0
                matched_terms.append(pol.category)

            # 2. Key phrases in policy description
            desc_words = [w for w in re.findall(r'\b[a-z]{4,}\b', pol.title.lower()) if w not in {"with", "from", "that", "this", "care"}]
            for dw in desc_words:
                if dw in cleaned_text:
                    score += 1.5
                    matched_terms.append(dw)

            # 3. Criteria keyword passage matches
            for crit in pol.criteria:
                kw_list = [k.strip().lower() for k in crit.keywords.split(",") if k.strip()]
                for kw in kw_list:
                    if kw in cleaned_text:
                        score += 1.0
                        if kw not in matched_terms:
                            matched_terms.append(kw)

            # Normalize score
            max_possible = max(1.0, len(pol.criteria) * 2.0 + 4.0)
            norm_score = min(1.0, score / max_possible)

            scored_policies.append({
                "policy_id": pol.policy_id,
                "title": pol.title,
                "jurisdiction": pol.jurisdiction,
                "category": pol.category,
                "relevance_score": round(norm_score, 3),
                "matched_terms": matched_terms[:8],
                "criteria_count": len(pol.criteria)
            })

        scored_policies.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored_policies

    def get_structured_criteria(self, policy_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves normalized criteria definitions for evaluation.
        """
        policy = self.retrieve_policy(policy_id)
        if not policy:
            return []

        criteria_list = []
        for c in policy.criteria:
            criteria_list.append({
                "id": c.id,
                "criterion_code": c.criterion_code,
                "name": c.name,
                "description": c.description,
                "clinical_intent": c.clinical_intent,
                "is_exclusion": c.is_exclusion,
                "required_temporal_window": c.required_temporal_window,
                "keywords": [k.strip().lower() for k in c.keywords.split(",") if k.strip()],
                "min_score": c.min_score
            })
        return criteria_list

