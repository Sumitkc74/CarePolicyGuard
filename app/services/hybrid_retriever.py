import math
import re
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models import MedicarePolicy, PolicyCriterion

class BM25Retriever:
    """
    In-memory BM25 Okapi lexical retriever for Medicare policy documents.
    Formula: IDF(q) * ((f(q, D) * (k1 + 1)) / (f(q, D) + k1 * (1 - b + b * (|D| / avgdl))))
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: List[Dict[str, Any]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

    def _tokenize(self, text: str) -> List[str]:
        return [w for w in re.findall(r'\b[a-z0-9_]{2,}\b', text.lower()) if not w.isdigit()]

    def index_documents(self, documents: List[Dict[str, Any]]):
        self.corpus = documents
        self.doc_lengths = []
        self.doc_freqs = {}
        n_docs = len(documents)

        for doc in documents:
            tokens = self._tokenize(doc["content"])
            self.doc_lengths.append(len(tokens))
            unique_tokens = set(tokens)
            for t in unique_tokens:
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1

        self.avg_doc_len = (sum(self.doc_lengths) / n_docs) if n_docs > 0 else 0.0

        # Calculate BM25 IDF
        for token, df in self.doc_freqs.items():
            self.idf[token] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        query_tokens = self._tokenize(query)
        if not query_tokens or not self.corpus:
            return []

        scores: List[float] = [0.0] * len(self.corpus)

        for q in query_tokens:
            idf_val = self.idf.get(q, 0.0)
            if idf_val <= 0:
                continue

            for idx, doc in enumerate(self.corpus):
                tokens = self._tokenize(doc["content"])
                tf = tokens.count(q)
                if tf == 0:
                    continue
                d_len = self.doc_lengths[idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (d_len / self.avg_doc_len))
                term_score = idf_val * ((tf * (self.k1 + 1.0)) / denom)
                scores[idx] += term_score

        ranked = sorted(zip(self.corpus, scores), key=lambda x: x[1], reverse=True)
        return [(doc, score) for doc, score in ranked[:top_k] if score > 0]


class DenseSemanticRetriever:
    """
    Semantic dense retriever with medical ontology concept projection.
    Provides cosine-similarity ranking over clinical embedding representations.
    """
    # Key clinical concept vocabulary vectors covering all 50 CMS policy domains
    CLINICAL_CONCEPT_VOCAB = [
        # 1. Core Cardiology & Sleep
        "lvef", "ejection_fraction", "systolic_heart_failure", "heart_failure", "cardiomyopathy",
        "nyha", "nyha_functional_class", "guideline_directed_medical_therapy", "gdmt",
        "implantable_cardioverter_defibrillator", "icd", "defibrillator",
        "myocardial_infarction", "post_myocardial_infarction", "waiting_period", "cardiogenic_shock",
        "obstructive_sleep_apnea", "sleep_apnea", "apnea_hypopnea_index", "ahi", "cpap", "bipap", "polysomnography",
        "aortic_stenosis", "tavr", "teer", "mitraclip", "heart_team_consensus",
        "atrial_fibrillation", "watchman", "left_atrial_appendage_closure",
        "diabetic_foot_ulcer", "hyperbaric_oxygen_therapy", "wagner_grade_3", "conservative_wound_care",
        # 2. Cardiovascular Interventions & Diagnostics
        "cardiac_rehab", "cardiac_rehabilitation", "coronary_artery_disease", "coronary_cta", "ccta",
        "myocardial_perfusion", "myocardial_perfusion_imaging", "pet_myocardial", "pacemaker", "cardiac_pacemaker",
        "bradycardia", "atrioventricular_block", "percutaneous_coronary_intervention", "pci", "stent", "angioplasty",
        "endovascular_aneurysm_repair", "evar", "abdominal_aortic_aneurysm", "peripheral_artery_disease", "atherectomy",
        "vein_ablation", "endovenous_radiofrequency", "great_saphenous_vein", "venous_insufficiency",
        # 3. Ophthalmology & Oculoplastic
        "cataract", "cataract_extraction", "phacoemulsification", "visual_acuity", "snellen", "glare_disability",
        "posterior_capsular_opacification", "blepharoplasty", "blepharoptosis", "mrd1", "marginal_reflex_distance",
        "superior_visual_field_restriction", "pseudoptosis", "brow_lift",
        # 4. Orthopedics (Joint & Extremity)
        "total_knee_arthroplasty", "knee_arthroplasty", "knee_osteoarthritis", "total_hip_arthroplasty", "hip_arthroplasty",
        "hip_osteoarthritis", "shoulder_arthroplasty", "reverse_shoulder_arthroplasty", "rotator_cuff", "rotator_cuff_tear",
        "supraspinatus_tear", "hip_arthroscopy", "femoroacetabular_impingement", "fai", "labral_tear", "cam_lesion",
        "knee_orthosis", "oa_knee_brace", "knee_brace", "hallux_valgus", "bunionectomy", "intermetatarsal_angle", "chondrocyte_implantation", "aci",
        "meniscus", "meniscal", "meniscectomy", "meniscal_tear", "knee_arthroscopy",
        # 5. Spine & Interventional Pain
        "anterior_cervical_discectomy_and_fusion", "acdf", "cervical_radiculopathy", "cervical_myelopathy",
        "lumbar_decompression", "lumbar_laminectomy", "lumbar_spinal_stenosis", "lumbar_fusion", "spondylolisthesis",
        "cervical_artificial_disc", "cervical_disc_arthroplasty", "sacroiliac_joint_fusion", "si_joint_fusion",
        "kyphoplasty", "vertebroplasty", "vertebral_compression_fracture", "epidural_steroid_injection", "esi",
        "lumbar_radiculopathy", "facet_joint_injection", "facet_medial_branch_block", "radiofrequency_ablation",
        # 6. Radiation Oncology & Oncology
        "intensity_modulated_radiation_therapy", "imrt", "stereotactic_body_radiation_therapy", "sbrt", "stereotactic_radiosurgery",
        "proton_beam_therapy", "proton_therapy", "oncology_pet", "fdg_pet", "pet_ct", "metabolic_tumor_volume",
        # 7. Radiology & Diagnostics
        "ct_chest", "chest_computed_tomography", "mri_brain", "brain_magnetic_resonance", "mri_lumbar_spine", "lumbar_mri",
        # 8. Neuromodulation, Pain Pumps & DMEPOS
        "spinal_cord_stimulation", "scs", "dorsal_column_stimulation", "trial_stimulation", "intrathecal_pump",
        "infusion_pump", "intrathecal_baclofen", "power_wheelchair", "power_mobility_device", "respiratory_assist_device",
        "noninvasive_ventilation", "bipap_st", "speech_generating_device", "augmentative_communication", "negative_pressure_wound_therapy",
        "wound_vac", "npwt",
        # 9. OPD Procedures & Plastic/Reconstructive
        "botulinum_toxin", "botox_injection", "cervical_dystonia", "chronic_migraine", "panniculectomy", "abdominal_pannus",
        "intertrigo", "rhinoplasty", "nasal_airway_obstruction", "septoplasty", "nasal_valve_collapse"
    ]

    def _embed_text(self, text: str) -> List[float]:
        """
        Generates normalized concept projection embedding.
        In production with PyTorch/Transformers, this maps to SapBERT or BioLinkBERT embeddings.
        """
        lowered = text.lower()
        vec = []
        for concept in self.CLINICAL_CONCEPT_VOCAB:
            parts = concept.split("_")
            phrase = " ".join(parts)
            hyphenated = "-".join(parts)
            if concept in lowered or phrase in lowered or hyphenated in lowered:
                vec.append(2.0)
            elif len(parts) > 1 and all(p in lowered for p in parts):
                vec.append(1.5)
            else:
                vec.append(0.0)

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        return [0.0] * len(vec)

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        return max(0.0, min(1.0, dot))

    def search(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        q_vec = self._embed_text(query)
        scored = []
        for doc in documents:
            doc_vec = self._embed_text(doc["content"])
            sim = self._cosine_similarity(q_vec, doc_vec)
            if sim > 0:
                scored.append((doc, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class HybridPolicyRetriever:
    """
    Enterprise Hybrid Lexical-Semantic Retriever:
    1. Chunks CMS policies into structured sections (Indications, Limitations, Exclusions, Billing).
    2. Runs BM25 Okapi for precise keyword/code matching.
    3. Runs Dense Semantic Retrieval for clinical intent.
    4. Merges candidate lists using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.bm25 = BM25Retriever()
        self.dense = DenseSemanticRetriever()
        self.chunks: List[Dict[str, Any]] = []
        self._build_index()

    def _build_index(self):
        policies = []
        if self.db:
            try:
                policies = self.db.query(MedicarePolicy).all()
            except Exception:
                policies = []

        if not policies:
            try:
                from app.db.session import SessionLocal
                with SessionLocal() as session:
                    policies = session.query(MedicarePolicy).all()
            except Exception:
                policies = []

        chunks = []
        if policies:
            for p in policies:
                # Chunk 1: Policy Overview & Indications
                chunks.append({
                    "policy_id": p.policy_id,
                    "policy_title": p.title,
                    "section": "Indications & Coverage Summary",
                    "content": f"{p.policy_id} {p.title} {p.category} {p.description or ''}"
                })

                # Chunk 2: Statutory Criteria & Requirements
                for c in p.criteria:
                    chunks.append({
                        "policy_id": p.policy_id,
                        "policy_title": p.title,
                        "section": f"Criterion: {c.criterion_code}",
                        "criterion_code": c.criterion_code,
                        "is_exclusion": c.is_exclusion,
                        "content": f"{c.criterion_code} {c.name} {c.description} Keywords: {c.keywords} Waiting Period: {c.required_temporal_window}"
                    })
        else:
            # Resilient fallback: loads all 50 declarative policies from disk when database is empty
            try:
                from app.services.declarative_engine import DeclarativePolicyEngine
                declarative_policies = DeclarativePolicyEngine.get_all_policies()
                for p in declarative_policies:
                    chunks.append({
                        "policy_id": p.policy_id,
                        "policy_title": p.title,
                        "section": "Indications & Coverage Summary",
                        "content": f"{p.policy_id} {p.title} {p.category} {p.description or ''}"
                    })
                    for c in p.criteria:
                        chunks.append({
                            "policy_id": p.policy_id,
                            "policy_title": p.title,
                            "section": f"Criterion: {c.criterion_code}",
                            "criterion_code": c.criterion_code,
                            "is_exclusion": c.is_exclusion,
                            "content": f"{c.criterion_code} {c.name} {c.description} Keywords: {c.keywords} Waiting Period: {c.required_temporal_window}"
                        })
            except Exception:
                chunks = []

        self.chunks = chunks
        self.bm25.index_documents(chunks)

    def retrieve_hybrid(self, clinical_query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Executes Reciprocal Rank Fusion (RRF) over BM25 and Dense Semantic results.
        RRF Score: sum( 1 / (k + rank) )
        """
        if not self.chunks:
            return []

        bm25_results = self.bm25.search(clinical_query, top_k=top_k * 2)
        dense_results = self.dense.search(clinical_query, self.chunks, top_k=top_k * 2)

        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict[str, Any]] = {}
        c_param = 60.0

        # RRF from BM25
        for rank, (doc, score) in enumerate(bm25_results, 1):
            key = f"{doc['policy_id']}_{doc['section']}"
            chunk_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (c_param + rank))

        # RRF from Dense Semantic
        for rank, (doc, score) in enumerate(dense_results, 1):
            key = f"{doc['policy_id']}_{doc['section']}"
            chunk_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (c_param + rank))

        # Rank aggregate policy candidates
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        results = []
        seen_policies = set()

        for k in sorted_keys:
            doc = chunk_map[k]
            pid = doc["policy_id"]
            if pid not in seen_policies:
                seen_policies.add(pid)
                results.append({
                    "policy_id": pid,
                    "title": doc["policy_title"],
                    "top_matched_section": doc["section"],
                    "rrf_score": round(rrf_scores[k], 4),
                    "hybrid_score": round(rrf_scores[k], 4),
                    "matched_content": doc["content"][:200] + "..."
                })
            if len(results) >= top_k:
                break

        return results

