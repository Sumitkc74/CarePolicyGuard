import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import MedicarePolicy, PolicyCriterion
from app.core.cache import policy_cache


CLINICAL_TAXONOMY_MAP = {
    "NCD-20.33": ["mitraclip", "teer", "transcatheter edge-to-edge repair", "transcatheter mitral valve", "mitral regurgitation", "clip"],
    "NCD-20.7": ["carotid artery stenting", "cas", "carotid endarterectomy", "cea", "carotid stenosis", "carotid angioplasty"],
    "NCD-20.4": ["implantable cardioverter defibrillator", "icd", "crt-d", "biventricular defibrillator", "defibrillator", "lvef"],
    "NCD-240.1": ["continuous positive airway pressure", "cpap", "bipap", "polysomnography", "apnea hypopnea index", "ahi", "sleep apnea"],
    "LCD-L33829": ["sacral nerve stimulation", "sns", "interstim", "urinary incontinence", "fecal incontinence", "bladder neuromodulation"]
}

class PolicyRetrievalAgent:
    """
    Agent 1: Policy Retrieval Agent
    Indexes structured CMS coverage policies (NCDs and LCDs), extracts governing criteria,
    and performs passage chunking and hybrid semantic/lexical matching to retrieve relevant
    governing criteria for clinical presentations.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def retrieve_policy(self, policy_id: str) -> Optional[Any]:
        """
        Retrieves a policy and its complete criteria tree by policy_id.
        Falls back to DeclarativePolicyEngine (Policy-as-Data JSON) if DB is unseeded.
        """
        if self.db:
            res = self.db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == policy_id).first()
            if res:
                return res

        from app.services.declarative_engine import DeclarativePolicyEngine
        decl = DeclarativePolicyEngine.load_policy(policy_id)
        if decl:
            class MockPolicyObj:
                def __init__(self, p):
                    self.policy_id = p.policy_id
                    self.title = p.title
                    self.jurisdiction = p.jurisdiction
                    self.effective_date = p.effective_date
                    self.category = p.category
                    self.description = p.description
                    self.criteria = []
            return MockPolicyObj(decl)
        return None

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

            # 4. Clinical Taxonomy Acronym and Synonym Cross-Referencing
            tax_terms = CLINICAL_TAXONOMY_MAP.get(pol.policy_id, [])
            for tt in tax_terms:
                if tt in cleaned_text:
                    score += 3.0
                    if tt not in matched_terms:
                        matched_terms.append(tt)

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
        Utilizes policy_cache for high-throughput sub-millisecond retrieval.
        """
        cache_key = f"criteria:{policy_id}"
        cached = policy_cache.get(cache_key)
        if cached is not None:
            return cached

        policy = self.retrieve_policy(policy_id)
        if not policy:
            from app.services.declarative_engine import DeclarativePolicyEngine
            decl = DeclarativePolicyEngine.load_policy(policy_id)
            if decl:
                crit_list = [c.model_dump() for c in decl.criteria]
                policy_cache.set(cache_key, crit_list, ttl_seconds=3600)
                return crit_list
            return []

        criteria_list = []
        if hasattr(policy, "criteria") and policy.criteria:
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
        else:
            from app.services.declarative_engine import DeclarativePolicyEngine
            decl = DeclarativePolicyEngine.load_policy(policy_id)
            if decl:
                criteria_list = [c.model_dump() for c in decl.criteria]

        policy_cache.set(cache_key, criteria_list, ttl_seconds=3600)
        return criteria_list
