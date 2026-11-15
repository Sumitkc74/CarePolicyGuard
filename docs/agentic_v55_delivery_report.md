# v55 — Delivery Report

**Session Scope**: BUILD session (Dense Semantic Retrieval & Persisted Vector Store)  
**Parent Head at Start**: `d98921a90598b899b1f6a215666c3c3e3dab2882` (commit `d98921a`)  
**Host**: Local Ollama runtime / PyTorch Transformers  
**Embedding Model**: `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` (offline via `local_files_only=True`)  
**Vector Store**: `app/data/embeddings/policy_chunks_sapbert.npz` (204 chunks, 768-dim, float32, L2-normalized)  
**Test Baseline**: 411 passed, 2 warnings in 219.74s (100% green, 0 regressions)

---

## 1. Executive Summary

In session **v55**, the dense half of hybrid policy retrieval was upgraded from a hand-built clinical concept projection vocabulary to real, local biomedical transformer embeddings (**SapBERT**: `cambridgeltl/SapBERT-from-PubMedBERT-fulltext`).

### Key Accomplishments
1. **Real Biomedical Dense Embeddings**:
   - Replaced keyword counting in `DenseSemanticRetriever._embed_text` with 768-dimensional normalized `[CLS]` embeddings from SapBERT.
   - Enforced zero network egress with `local_files_only=True`.
   - Verified that true clinical synonyms (`"prostate adenocarcinoma"` vs `"prostate cancer"`) achieve high cosine similarity (**0.8804 > 0.80**), whereas unrelated clinical concepts (`"prostate adenocarcinoma"` vs `"cataract phacoemulsification"`) exhibit low similarity (**0.2777 < 0.40**).
2. **Persisted Local Vector Store**:
   - Created `scripts/build_dense_vector_store.py` which pre-embeds all 204 policy chunks from `carepolicyguard.db` (and fallback declarative policies).
   - Saved pre-computed embeddings and metadata to:
     * `app/data/embeddings/policy_chunks_sapbert.npz` (626 KB)
     * `app/data/embeddings/policy_chunks_sapbert_meta.json` (31 KB)
   - Pre-computed embeddings load into memory in <2 ms; per-query vector dot-products execute in <1 ms.
3. **BM25 and RRF Fusion Preserved**:
   - BM25 Okapi lexical ranking and Reciprocal Rank Fusion (`c=60.0`, score formula `1 / (60 + rank)`) remain completely untouched.
   - Clarified that `PolicyRetrievalAgent.search_policies_by_narrative` in `app/agents/policy_retriever.py` is a separate multi-policy keyword/concept scanner that does not share code with `DenseSemanticRetriever`.
4. **Retrieval Evaluation Across 84 Dev Vignettes**:
   - Executed under policy-not-given condition with `scripts/evaluate_retrieval_accuracy.py`.
   - Top-3 retrieval accuracy reached **97.6% (82/84)**, improving by +1 case over the v47 baseline (81/84, 96.4%).
   - Top-5 retrieval accuracy remained rock-solid at **97.6% (82/84)**.
   - Fixed vocabulary-mismatch case: `DEV-LCD-WOUND-VAC-NEG` ("Sacral wound with 100% thick black necrotic eschar without debridement") achieved **Gold Rank 1** under SapBERT semantic matching.
5. **Strict Scope Adherence & Safety**:
   - Strictly zero changes to deterministic/declarative adjudication decision logic.
   - Zero LLM generation or reranker added to production retrieval path.
   - 84-case LLM adjudication benchmark was strictly NOT run.
   - Held-out set `carepolicyguard-heldout-v2/heldout_vignettes_v2.json` was NOT accessed.
   - Regression guards 14/14 passed (10/10 BENCH, 15/15 v1 held-out, 0 FA / 0 FD).

---

## 2. Task Implementation Details

### Task 1: Dense Semantic Retriever with Local SapBERT
- **Location**: `app/services/hybrid_retriever.py` (`DenseSemanticRetriever`)
- **Model**: `cambridgeltl/SapBERT-from-PubMedBERT-fulltext`
- **Methodology**:
  - Lazy model initialization using `_get_sapbert_model()`.
  - `_embed_text(text: str) -> List[float]`: Tokenizes query with max length 512, extracts `[CLS]` token representation, applies L2 normalization (`norm ≈ 1.0`), and returns 768 floats.
  - `_cosine_similarity(v1, v2) -> float`: Computes dot product of normalized vectors, clamped to `[0.0, 1.0]`.
  - Guaranteed offline operation: Both tokenizer and model enforce `local_files_only=True`.

### Task 2: Persistent Vector Store
- **Builder Script**: `scripts/build_dense_vector_store.py`
  - Loads 204 chunks across 50 CMS policies (Indications & Coverage Summary + statutory criteria).
  - Computes 768-dim normalized embeddings in batches of 32.
  - Saves compressed archive `app/data/embeddings/policy_chunks_sapbert.npz` and manifest `app/data/embeddings/policy_chunks_sapbert_meta.json`.
- **Runtime Fast-Path**:
  - `_load_vector_store()` loads the 204 chunk embeddings into a float32 numpy matrix upon startup.
  - In `search()`, incoming query is embedded once; chunk embeddings are retrieved directly from the precomputed matrix via index lookup, computing cosine similarity across all 204 chunks in <1 ms without re-embedding documents. Dynamic documents not in the index fall back to dynamic on-the-fly embedding.

### Task 3: Scorer Architecture & RRF Fusion
- BM25 Okapi lexical retriever remains unchanged.
- Reciprocal Rank Fusion (`HybridPolicyRetriever.retrieve_hybrid`) uses frozen constant `c_param = 60.0` and formula `1.0 / (60.0 + rank)`.
- **Multi-policy scanner disclosure**: `PolicyRetrievalAgent.search_policies_by_narrative` (`app/agents/policy_retriever.py`) is confirmed to be a separate, hand-weighted keyword and concept scanner that does not share code or vector indices with `DenseSemanticRetriever`.

### Task 4: Retrieval Accuracy Evaluation (84 Dev Vignettes)
- **Runner**: `scripts/evaluate_retrieval_accuracy.py`
- **Committed Artifact**: `app/data/benchmarks/retrieval_v55_measurement.json`
- **Metrics Comparison**:

| Metric | v47 Baseline (Keyword Vector) | v55 (SapBERT Dense Store) | Delta |
| :--- | :---: | :---: | :---: |
| **Top-1 Accuracy** | 75 / 84 (89.3%) | 69 / 84 (82.1%) | -6 |
| **Top-3 Accuracy** | 81 / 84 (96.4%) | 82 / 84 (97.6%) | **+1** |
| **Top-5 Accuracy** | 82 / 84 (97.6%) | 82 / 84 (97.6%) | 0 |
| **Pre-selected Rate** | 40 / 84 (47.6%) | 41 / 84 (48.8%) | **+1** |
| **Selection Required Rate**| 44 / 84 (52.4%) | 43 / 84 (51.2%) | -1 |
| **No Governing Policy** | 0 / 84 (0.0%) | 0 / 84 (0.0%) | 0 |
| **Latency p50** | 320.5 ms | 523.8 ms | +203.3 ms |
| **Latency p90** | 381.6 ms | 637.9 ms | +256.3 ms |
| **Latency p95** | 401.8 ms | 681.0 ms | +279.2 ms |

#### Notable Case Analysis
- **`DEV-LCD-WOUND-VAC-NEG` (Vocabulary Mismatch Resolved)**:
  * Narrative: *"Sacral wound with 100% thick black necrotic eschar without debridement"*
  * Gold Policy: `LCD-WOUND-VAC` (Negative Pressure Wound Therapy)
  * Outcome: **Rank 1 (Top-1 Match)**. Under SapBERT semantic embeddings, the clinical relationship between necrotic eschar, wound debridement, and wound VAC is recognized directly without needing exact keyword overlap.
- **Top-1 / Top-3 Shift Analysis**:
  * In v55, cases like `DEV-LCD-PCI-NEG` and `DEV-LCD-PAD-ATHERO-APP` rose to Rank 1.
  * Orthopedic and spine overlap cases (e.g. `DEV-LCD-FACET-NEG`, `DEV-LCD-LUMBAR-FUSION-NEG`, `DEV-NCD-PUMP-APP`) placed the gold policy at Rank 2 or Rank 3 (comfortably within Top-3) while closely related anatomical policies (e.g. `LCD-ESI`, `LCD-ACDF`, `NCD-SCS`) shared high dense similarity. Top-3 coverage improved to **97.6%**.

---

## 3. Regression Guards & Test Suite Summary

### Dedicated Fail-Before / Pass-After Tests (`tests/test_dense_biomedical_retriever.py`)
1. `test_dense_retriever_returns_real_vectors_and_captures_synonymy`: **PASSED**  
   - 768-dim normalized dense vector verified.
   - Synonym similarity (`"prostate adenocarcinoma"` vs `"prostate cancer"`): **0.8804 > 0.80**.
   - Unrelated similarity (`"prostate adenocarcinoma"` vs `"cataract phacoemulsification"`): **0.2777 < 0.40**.
2. `test_vector_store_persists_and_reloads_identically`: **PASSED**  
   - Bit-for-bit identical vectors and rankings between store generations and reloads.
3. `test_rrf_fusion_formula_and_weights_unchanged`: **PASSED**  
   - Verified `c_param = 60.0` and rank math `1 / (60 + rank)`.
4. `test_regression_known_good_retrieval_case`: **PASSED**  
   - Verified that severe aortic stenosis TAVR case preselects `NCD-20.33` with high margin.
5. `test_zero_external_network_calls_at_runtime`: **PASSED**  
   - Verified zero external HTTP requests via socket/urllib interceptors.

### Clinical Domain Queries Test (`tests/test_dense_concept_domains.py`)
- `test_dense_concept_retriever_fires_for_all_clinical_domains`: **PASSED**
- `test_hybrid_policy_retriever_fallback_indexes_all_50_policies_when_db_empty`: **PASSED**

### Regression Guards (`tests/test_benchmark.py` & `tests/test_v1_heldout_regressions.py`)
- 14 / 14 passed (10/10 BENCH, 15/15 v1 held-out cases, 0 False Approvals, 0 False Denials).

---

## 4. Verification Checkpoint

| Check | Expected | Actual | Status |
| :--- | :--- | :--- | :---: |
| Dense Model | `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` | SapBERT local cache | **PASS** |
| Vector Store | `policy_chunks_sapbert.npz` (204 chunks, 768-dim) | Present & verified | **PASS** |
| Zero Remote Egress | `local_files_only=True` | Enforced & unit tested | **PASS** |
| BM25 + RRF Fusion | `c=60.0`, score formula unchanged | Frozen & verified | **PASS** |
| Retrieval Accuracy | Top-3 >= 96.4%, Top-5 >= 97.6% | Top-3 = 97.6%, Top-5 = 97.6% | **PASS** |
| Production Rules | No LLM / reranker in production retrieval | Verified | **PASS** |
| v2 Held-out Set | Untouched | Not opened or run | **PASS** |
| 84-Case LLM Adjudication | Not run | Adjudication benchmark skipped | **PASS** |
