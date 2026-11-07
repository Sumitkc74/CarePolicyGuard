"""
CLI script to onboard a CMS coverage policy using Agent 5 (PolicyOnboardingAgent).
Usage:
    python scripts/onboard_policy.py --cms-id L36920 --subject "Epidural Steroid Injections"
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.policy_onboarding import PolicyOnboardingAgent


def main():
    parser = argparse.ArgumentParser(description="CarePolicyGuard: Agent 5 Policy Onboarding CLI")
    parser.add_argument("--cms-id", required=True, help="CMS MCD Identifier (e.g. L36920, L33318, NCD-20.8)")
    parser.add_argument("--subject", required=True, help="Clinical subject or procedure title")
    parser.add_argument("--vignettes", default=None, help="Optional path to frozen test vignettes JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not save DRAFT policy JSON to disk")

    args = parser.parse_args()

    vignettes = None
    if args.vignettes:
        v_path = Path(args.vignettes)
        if v_path.exists():
            with open(v_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                vignettes = data if isinstance(data, list) else data.get("cases", [])

    agent = PolicyOnboardingAgent()
    print(f"[*] Onboarding CMS policy '{args.cms_id}' ({args.subject})...")
    result = agent.onboard_policy(
        cms_id=args.cms_id,
        clinical_subject=args.subject,
        test_vignettes=vignettes,
        save_draft=not args.no_save
    )

    print(f"[*] Result Status: {result.status}")
    print(f"[*] Message: {result.message}")

    if result.report:
        print(f"[*] Verbatim Checks: {result.report.verbatim_checks_passed} passed, {result.report.verbatim_checks_failed} failed")
        print(f"[*] Flagged Ambiguities: {len(result.report.flagged_ambiguities)}")
        for amb in result.report.flagged_ambiguities:
            print(f"    - [{amb.criterion_code}] {amb.question_for_human}")
        if result.report.evaluation_rounds:
            for er in result.report.evaluation_rounds:
                print(f"    - Round {er.round_number}: {er.decision_matches}/{er.vignettes_count} ({er.accuracy_percent}%)")

    if result.status == "SOURCE_NOT_FOUND":
        sys.exit(2)
    elif result.status == "REJECTED_VERBATIM_FAILURE":
        sys.exit(3)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

