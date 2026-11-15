"""
Build Script for Dense Biomedical Vector Store (v55).
Extracts policy chunks from CarePolicyGuard, computes 768-dim L2-normalized SapBERT
embeddings, and persists them to app/data/embeddings/policy_chunks_sapbert.npz
along with build metadata.
"""

import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from app.services.hybrid_retriever import HybridPolicyRetriever

MODEL_NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
EMBEDDINGS_DIR = PROJECT_ROOT / "app" / "data" / "embeddings"
NPZ_PATH = EMBEDDINGS_DIR / "policy_chunks_sapbert.npz"
META_PATH = EMBEDDINGS_DIR / "policy_chunks_sapbert_meta.json"
BATCH_SIZE = 32


def build_dense_vector_store():
    start_time = time.perf_counter()
    print(f"[v55-build] Initializing policy chunks from HybridPolicyRetriever...")

    retriever = HybridPolicyRetriever()
    chunks = retriever.chunks
    chunk_count = len(chunks)
    print(f"[v55-build] Found {chunk_count} policy chunks across policies.")
    if chunk_count == 0:
        raise ValueError("No policy chunks found to embed.")

    print(f"[v55-build] Loading local SapBERT model ({MODEL_NAME}) with local_files_only=True...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[v55-build] Inference device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL_NAME, local_files_only=True)
    model.to(device)
    model.eval()

    print(f"[v55-build] Computing SapBERT embeddings in batches of {BATCH_SIZE}...")
    chunk_ids = []
    policy_ids = []
    sections = []
    all_embeddings = []

    for i in range(0, chunk_count, BATCH_SIZE):
        batch_chunks = chunks[i:i + BATCH_SIZE]
        texts = [c["content"] for c in batch_chunks]

        inputs = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            # SapBERT CLS token representation
            cls_rep = outputs.last_hidden_state[:, 0, :]  # Shape: [batch, 768]
            # L2 normalize
            norms = torch.norm(cls_rep, p=2, dim=1, keepdim=True).clamp(min=1e-12)
            normalized_rep = (cls_rep / norms).cpu().numpy()

        all_embeddings.append(normalized_rep)

        for c in batch_chunks:
            chunk_id = f"{c['policy_id']}::{c['section']}"
            chunk_ids.append(chunk_id)
            policy_ids.append(c["policy_id"])
            sections.append(c["section"])

    matrix = np.vstack(all_embeddings).astype(np.float32)
    print(f"[v55-build] Matrix shape: {matrix.shape}, dtype: {matrix.dtype}")

    # Verify L2 norms are approximately 1.0
    row_norms = np.linalg.norm(matrix, axis=1)
    print(f"[v55-build] Row norms: min={row_norms.min():.5f}, max={row_norms.max():.5f}, mean={row_norms.mean():.5f}")

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[v55-build] Saving compressed archive to {NPZ_PATH}...")
    np.savez_compressed(
        NPZ_PATH,
        embeddings=matrix,
        chunk_ids=np.array(chunk_ids),
        policy_ids=np.array(policy_ids),
        sections=np.array(sections)
    )

    meta = {
        "model_name": MODEL_NAME,
        "dimension": int(matrix.shape[1]),
        "normalization": "L2",
        "chunk_count": chunk_count,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_duration_seconds": round(time.perf_counter() - start_time, 2),
        "device_used": str(device),
        "chunks": [
            {
                "chunk_id": chunk_ids[idx],
                "policy_id": chunks[idx]["policy_id"],
                "policy_title": chunks[idx].get("policy_title", ""),
                "section": chunks[idx]["section"],
                "content_preview": chunks[idx]["content"][:120]
            }
            for idx in range(chunk_count)
        ]
    }

    print(f"[v55-build] Saving metadata to {META_PATH}...")
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    total_time = time.perf_counter() - start_time
    print(f"[v55-build] Dense vector store built successfully in {total_time:.2f}s.")
    return NPZ_PATH, META_PATH


if __name__ == "__main__":
    build_dense_vector_store()
