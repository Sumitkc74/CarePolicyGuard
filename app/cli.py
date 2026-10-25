import sys
import argparse
import json
import asyncio
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import MedicarePolicy, AdjudicationLog
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.benchmark_engine import BenchmarkRunner
from app.core.cache import policy_cache

def format_banner():
    return (
        "==================================================================\n"
        "           CarePolicyGuard: Clinical CLI Adjudicator              \n"
        "   Policy-Aware Multi-Agent Evidence & Prior-Auth Audit Engine     \n"
        "=================================================================="
    )

def handle_adjudicate(args):
    """Executes the 4-agent clinical verification pipeline from the terminal."""
    narrative = ""
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                narrative = f.read()
        except Exception as e:
            print(f"[-] Error reading clinical note file '{args.file}': {e}")
            sys.exit(1)
    elif args.text:
        narrative = args.text
    else:
        print("[-] Error: You must supply a clinical note via --file or --text.")
        sys.exit(1)

    db = SessionLocal()
    try:
        pipeline = MultiAgentVerificationPipeline(db=db)
        save_to_db = not args.no_save

        async def run_pipeline():
            return await pipeline.adjudicate(
                patient_id=args.patient_id,
                policy_id=args.policy,
                ehr_narrative=narrative,
                custom_tau=args.tau,
                save_record=save_to_db
            )

        result = asyncio.run(run_pipeline())

        if args.json:
            print(json.dumps(result.model_dump(), default=str, indent=2))
            return

        print(format_banner())
        print(f"Case Identifier:       {result.case_id}")
        print(f"Patient (Masked):      {result.patient_id_masked} (HIPAA Safe Harbor)")
        print(f"Governing Policy:      {result.policy_id} - {result.policy_title}")
        print(f"Final Determination:   {result.adjudication_decision.value}")
        print(f"Calibrated Confidence: {result.calibrated_aggregate_confidence * 100:.1f}%")
        print(f"Safety Gate (tau):     {result.abstention_threshold:.2f} (Abstained: {result.abstention_status})")
        print(f"Execution Latency:     {result.execution_time_ms} ms")
        print(f"SHA-256 Audit Seal:    {result.audit_hash}")
        print("-" * 66)
        print("STATUTORY CRITERIA EVALUATION:")
        for idx, crit in enumerate(result.criterion_assessments, 1):
            stat = crit.status.value
            print(f"  [{idx}] {crit.criterion_code}: {crit.name} -> {stat} (raw conf: {crit.raw_confidence:.2f})")
            for sp in crit.verified_spans:
                print(f"      Grounded Quote: \"{sp.source_text}\" [chars {sp.start_char}:{sp.end_char}] ({sp.clinical_section})")

        if result.required_clinician_action_notes:
            print("-" * 66)
            print("CLINICAL ACTION NOTES:")
            print(f"  {result.required_clinician_action_notes}")

        print("=" * 66)
    finally:
        db.close()


def handle_benchmark(args):
    """Executes the 4-configuration empirical benchmark and prints calibration metrics."""
    runner = BenchmarkRunner()
    results = runner.run_benchmark()

    if args.json:
        print(json.dumps(results.model_dump(), default=str, indent=2))
        return

    print(format_banner())
    print(f"Research Benchmark Lab: {results.dataset_size} CMS Vignettes (40 Adjudication Runs)")
    print(f"Calibrated Abstention Safety Threshold: tau = {results.abstention_threshold}")
    print("-" * 66)
    print(f"{'Configuration':<32} | {'Accuracy':<8} | {'Faithful':<8} | {'ECE':<8} | {'Safety'}")
    print("-" * 66)
    for c in results.configs:
        print(f"{c.label:<32} | {c.accuracy * 100:>6.1f}% | {c.evidence_faithfulness * 100:>6.1f}% | {c.expected_calibration_error:>8.4f} | {c.clinical_safety_score:>6.3f}")
    print("-" * 66)
    print("Comparative Analysis:")
    print(f"  {results.comparative_analysis}")
    print("=" * 66)


def handle_export_audit(args):
    """Exports the tamper-evident audit ledger to an RFC 4180 CSV file."""
    output_path = args.output
    db = SessionLocal()
    try:
        logs = db.query(AdjudicationLog).order_by(AdjudicationLog.created_at.desc()).all()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("Event ID,Timestamp (UTC),Case ID,Patient Masked,Policy ID,Decision,Calibrated Confidence,Audit Hash (SHA-256)\n")
            for l in logs:
                ts = l.created_at.isoformat() if l.created_at else "N/A"
                f.write(f'"AUD-{l.id:05d}","{ts}","{l.case_id}","{l.patient_id_masked}","{l.policy_id}","{l.decision}",{l.calibrated_confidence:.4f},"{l.audit_hash}"\n')
        print(f"[+] Successfully exported {len(logs)} audit records to '{output_path}'.")
    finally:
        db.close()


def handle_cache_stats(args):
    """Displays telemetry metrics from the Policy Cache-Aside manager."""
    stats = policy_cache.get_metrics()
    print(format_banner())
    print("IN-MEMORY POLICY CACHE TELEMETRY:")
    print(f"  Total Requests:      {stats.get('total_requests', 0)}")
    print(f"  Cache Hits:          {stats.get('hits', 0)}")
    print(f"  Cache Misses:        {stats.get('misses', 0)}")
    print(f"  Hit Ratio:           {stats.get('hit_ratio', 0.0) * 100:.1f}%")
    print(f"  Active Cached Keys:  {stats.get('active_cached_keys', 0)}")
    print(f"  Default TTL:         {stats.get('default_ttl_seconds', 3600)} seconds")
    print("=" * 66)


def handle_policies(args):
    """Lists all active CMS coverage policies and their criteria counts."""
    db = SessionLocal()
    try:
        policies = db.query(MedicarePolicy).all()
        print(format_banner())
        print(f"LOADED CMS COVERAGE POLICIES ({len(policies)} policies):")
        print("-" * 66)
        for p in policies:
            print(f"  {p.policy_id:<12} | {p.category:<16} | Criteria: {len(p.criteria):<3} | {p.title[:35]}")
        print("=" * 66)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="CarePolicyGuard: Multi-Agent Clinical Evidence & Coverage Verification Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: adjudicate
    adj_parser = subparsers.add_parser("adjudicate", help="Adjudicate a clinical note against CMS policies")
    adj_parser.add_argument("--file", "-f", help="Path to clinical note text file")
    adj_parser.add_argument("--text", "-t", help="Raw inline clinical note text")
    adj_parser.add_argument("--patient-id", "-p", default="PT-CLI-001", help="Patient context identifier")
    adj_parser.add_argument("--policy", "-pol", default="NCD-20.4", help="CMS Policy ID (e.g. NCD-20.4, NCD-20.7, NCD-20.33, LCD-L33829)")
    adj_parser.add_argument("--tau", type=float, default=0.85, help="Abstention threshold tau (default: 0.85)")
    adj_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    adj_parser.add_argument("--no-save", action="store_true", help="Do not persist adjudication record to DB (Zero-Retention Mode)")

    # Command: benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Run 4-configuration clinical benchmark")
    bench_parser.add_argument("--json", action="store_true", help="Output raw JSON results")

    # Command: export-audit
    audit_parser = subparsers.add_parser("export-audit", help="Export compliance audit ledger as CSV")
    audit_parser.add_argument("--output", "-o", default="carepolicyguard_audit_trail.csv", help="Target CSV output path")

    # Command: cache-stats
    subparsers.add_parser("cache-stats", help="Display Policy Cache-Aside metrics")

    # Command: policies
    subparsers.add_parser("policies", help="List loaded CMS Medicare coverage policies")

    args = parser.parse_args()

    if args.command == "adjudicate":
        handle_adjudicate(args)
    elif args.command == "benchmark":
        handle_benchmark(args)
    elif args.command == "export-audit":
        handle_export_audit(args)
    elif args.command == "cache-stats":
        handle_cache_stats(args)
    elif args.command == "policies":
        handle_policies(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
