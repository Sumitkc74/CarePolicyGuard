"""
SapBERT Model Fetch Script (v55-fix).

Downloads and caches the pre-trained biomedical language model
(cambridgeltl/SapBERT-from-PubMedBERT-fulltext) from Hugging Face Hub
for offline execution within CarePolicyGuard.

Usage:
    python scripts/fetch_sapbert_model.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODEL_NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"


def fetch_sapbert_model() -> bool:
    """Fetches and verifies the SapBERT model cache."""
    start_time = time.perf_counter()
    print("=" * 60)
    print(" CarePolicyGuard — SapBERT Model Offline Cache Fetcher")
    print("=" * 60)
    print(f"Target model: {MODEL_NAME}")

    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        print(f"ERROR: Required dependencies missing: {exc}")
        print("Please install requirements first: pip install -r requirements-pinned.txt")
        return False

    print("\n[Step 1/2] Fetching/verifying tokenizer and model from Hugging Face Hub...")
    try:
        # Download with local_files_only=False to ensure local cache is populated
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=False)
        model = AutoModel.from_pretrained(MODEL_NAME, local_files_only=False)
        assert tokenizer is not None
        assert model is not None
        print("Model and tokenizer successfully downloaded/verified in cache.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: Failed to download model: {exc}")
        return False

    print("\n[Step 2/2] Validating offline local loading (local_files_only=True)...")
    try:
        # Test offline reload guarantee
        test_tok = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=True)
        test_mod = AutoModel.from_pretrained(MODEL_NAME, local_files_only=True)
        assert test_tok is not None
        assert test_mod is not None
        print("Verified: SapBERT successfully reloaded with local_files_only=True.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: Offline validation check failed: {exc}")
        return False

    elapsed = time.perf_counter() - start_time
    print(f"\nFetch and cache validation completed in {elapsed:.2f}s.")
    print("Ready for: python scripts/build_dense_vector_store.py")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = fetch_sapbert_model()
    sys.exit(0 if success else 1)
