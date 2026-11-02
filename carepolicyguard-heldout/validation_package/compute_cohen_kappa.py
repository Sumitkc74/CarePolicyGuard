#!/usr/bin/env python3
"""
CarePolicyGuard Route B Dual-Annotation Inter-Rater Reliability Calculator.
Calculates Cohen's Kappa, decision agreement, and confusion matrix between two
independent annotation sheets without requiring system outputs or external APIs.

Labelling standard:
Route B evaluations must be reported as:
"Independently dual-annotated, non-clinician validated", never "clinician-validated".
"""

import argparse
import json
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

VALID_DECISIONS = ["APPROVED", "DENIED", "DEFERRED_TO_HUMAN"]

def load_annotations(file_path: Path) -> Dict[str, str]:
    """Loads annotations mapping case_id -> decision from JSON or CSV."""
    if not file_path.exists():
        raise FileNotFoundError(f"Annotation file not found: {file_path}")

    decisions = {}
    if file_path.suffix.lower() == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("annotations", data.get("vignettes", [])) if isinstance(data, dict) else data
        for item in items:
            cid = item.get("case_id") or item.get("id")
            dec = item.get("decision") or item.get("gold_decision") or item.get("expected_determination")
            if cid and dec:
                decisions[str(cid).strip()] = str(dec).strip().upper()
    elif file_path.suffix.lower() == ".csv":
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = row.get("case_id") or row.get("id")
                dec = row.get("decision") or row.get("gold_decision")
                if cid and dec:
                    decisions[str(cid).strip()] = str(dec).strip().upper()
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .json or .csv.")

    return decisions

def compute_cohen_kappa(ann1: Dict[str, str], ann2: Dict[str, str]) -> Dict[str, Any]:
    """Computes Cohen's Kappa, confusion matrix, and lists disagreements."""
    common_cases = sorted(list(set(ann1.keys()) & set(ann2.keys())))
    if not common_cases:
        raise ValueError("No common case IDs found between the two annotation sets.")

    missing_in_2 = set(ann1.keys()) - set(ann2.keys())
    missing_in_1 = set(ann2.keys()) - set(ann1.keys())
    if missing_in_2 or missing_in_1:
        print(f"Warning: Disjoint case IDs detected! Missing in 2: {len(missing_in_2)}, Missing in 1: {len(missing_in_1)}")

    n = len(common_cases)
    categories = VALID_DECISIONS

    # Confusion matrix: rows = Annotator 1, cols = Annotator 2
    matrix = {c1: {c2: 0 for c2 in categories} for c1 in categories}
    disagreements = []

    for cid in common_cases:
        d1 = ann1[cid]
        d2 = ann2[cid]
        if d1 not in categories or d2 not in categories:
            print(f"Warning: Case {cid} contains non-standard decision ({d1} vs {d2}).")
            continue
        matrix[d1][d2] += 1
        if d1 != d2:
            disagreements.append({
                "case_id": cid,
                "annotator_1": d1,
                "annotator_2": d2
            })

    # Observed agreement
    agree_count = sum(matrix[c][c] for c in categories)
    po = agree_count / n if n > 0 else 0.0

    # Chance agreement
    pe = 0.0
    for c in categories:
        row_total = sum(matrix[c][c2] for c2 in categories)
        col_total = sum(matrix[c1][c] for c1 in categories)
        pe += (row_total / n) * (col_total / n)

    # Cohen's Kappa
    if 1.0 - pe == 0:
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1.0 - pe)

    return {
        "total_cases_evaluated": n,
        "agreement_count": agree_count,
        "observed_agreement": round(po, 4),
        "chance_agreement": round(pe, 4),
        "cohen_kappa": round(kappa, 4),
        "target_met": kappa >= 0.85,
        "confusion_matrix": matrix,
        "disagreements": disagreements
    }

def print_reliability_report(results: Dict[str, Any], ann1_name: str, ann2_name: str):
    print("=" * 80)
    print("CAREPOLICYGUARD INTER-RATER RELIABILITY REPORT (ROUTE B)")
    print("Strict Labelling Rule: Independently dual-annotated, non-clinician validated")
    print("=" * 80)
    print(f"Annotator 1: {ann1_name}")
    print(f"Annotator 2: {ann2_name}")
    print(f"Total Overlapping Cases: {results['total_cases_evaluated']}")
    print(f"Observed Agreement (Po): {results['observed_agreement'] * 100:.2f}% ({results['agreement_count']}/{results['total_cases_evaluated']})")
    print(f"Chance Agreement (Pe):   {results['chance_agreement'] * 100:.2f}%")
    print(f"Cohen's Kappa (kappa):   {results['cohen_kappa']:.4f}")

    if results["target_met"]:
        print("\nSTATUS: PASS (Target kappa >= 0.85 satisfied - Near-Perfect Agreement)")
    else:
        print(f"\nSTATUS: ACTION REQUIRED (kappa {results['cohen_kappa']:.4f} < 0.85 threshold)")
        print("Discrepant cases must be adjudicated against verbatim CMS text by a third reviewer.")

    print("\nConfusion Matrix (Rows: Annotator 1, Columns: Annotator 2):")
    header = f"{'':<20}" + "".join(f"{c:<20}" for c in VALID_DECISIONS)
    print(header)
    print("-" * len(header))
    for c1 in VALID_DECISIONS:
        row_str = f"{c1:<20}" + "".join(f"{results['confusion_matrix'][c1][c2]:<20}" for c2 in VALID_DECISIONS)
        print(row_str)

    if results["disagreements"]:
        print(f"\nDiscrepancies Requiring Adjudication ({len(results['disagreements'])} cases):")
        for d in results["disagreements"]:
            print(f"  - [{d['case_id']}]: Annotator 1 = {d['annotator_1']:<18} | Annotator 2 = {d['annotator_2']:<18}")
    else:
        print("\nZero discrepancies observed across all evaluated cases.")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Calculate Cohen's Kappa between two annotation sheets.")
    parser.add_argument("--annotator1", required=True, type=Path, help="Path to primary annotation file (.json or .csv)")
    parser.add_argument("--annotator2", required=True, type=Path, help="Path to second annotator file (.json or .csv)")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional output JSON path for results")
    args = parser.parse_args()

    ann1 = load_annotations(args.annotator1)
    ann2 = load_annotations(args.annotator2)

    results = compute_cohen_kappa(ann1, ann2)
    print_reliability_report(results, args.annotator1.name, args.annotator2.name)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Saved reliability report JSON to: {args.output_json}")

if __name__ == "__main__":
    main()

