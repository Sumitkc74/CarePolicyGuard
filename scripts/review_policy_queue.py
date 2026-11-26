"""
Human Review Mechanism for Policy Criteria Verification (Task 1).

Provides an auditable CLI for human clinicians and designated policy reviewers to:
- Inspect policy criteria in the verification queue.
- View criterion descriptions, statutory excerpts, and live MCD document passages.
- Record APPROVE / REJECT decisions with mandatory reviewer identity and rationale.
- Activate READY policies from DRAFT to ACTIVE once all criteria are accepted.

Governance & Security Rules:
- Automated agent self-approval is strictly prohibited (keyword block).
- APPROVAL is forbidden for criteria failing verbatim citation checks (FAIL / NO_DOCUMENT).
- Review decisions are permanent audit records; overwriting requires --overwrite and notes.
- The 60 existing catalog policies remain grandfathered ACTIVE; new policies start DRAFT.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT_DIR / "app" / "data" / "policy_verification_records.json"
DEFAULT_QUEUE_FILE = QUEUE_FILE

FORBIDDEN_AGENT_KEYWORDS = ["agent", "llm", "antigravity", "bot", "assistant", "system", "auto"]


def is_agent_reviewer(reviewer: str) -> bool:
    """Returns True if the reviewer name indicates an automated agent."""
    if not reviewer:
        return False
    reviewer_clean = reviewer.strip().lower()
    return any(k in reviewer_clean for k in FORBIDDEN_AGENT_KEYWORDS)


def load_queue(queue_path: Path | None = None) -> list[dict[str, Any]]:
    path = queue_path or DEFAULT_QUEUE_FILE
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(items: list[dict[str, Any]], queue_path: Path | None = None) -> None:
    path = queue_path or DEFAULT_QUEUE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def add_or_update_queue_records(records: list[dict[str, Any]], queue_path: Path | None = None) -> int:
    """Adds or updates criterion records in the verification queue."""
    path = queue_path or DEFAULT_QUEUE_FILE
    items = load_queue(path)
    item_map = {(x.get("policy_id"), x.get("criterion_code")): i for i, x in enumerate(items)}
    added = 0
    for r in records:
        key = (r.get("policy_id"), r.get("criterion_code"))
        if key in item_map:
            # Update existing record
            idx = item_map[key]
            items[idx].update(r)
        else:
            items.append(r)
            item_map[key] = len(items) - 1
            added += 1
    save_queue(items, path)
    return added


def list_entries(
    policy_id: str | None = None,
    status_filter: str | None = None,
    queue_path: Path | None = None
) -> None:
    items = load_queue(queue_path)
    filtered = items
    if policy_id:
        filtered = [x for x in filtered if x.get("policy_id") == policy_id]
    if status_filter:
        clean_status = status_filter.strip().upper()
        filtered = [x for x in filtered if str(x.get("status")).upper() == clean_status]

    print("\n" + "=" * 90)
    print(f"POLICY VERIFICATION REVIEW QUEUE: {len(filtered)} matching criteria (Total in Queue: {len(items)})")
    print("=" * 90)

    for item in filtered:
        excl_tag = " [EXCLUSION]" if item.get("is_exclusion") else ""
        print(f"\n[Criterion Code]:   {item.get('criterion_code')}{excl_tag}")
        print(f" Policy ID:         {item.get('policy_id')} | Name: {item.get('criterion_name')}")
        print(f" Verification State: {item.get('status')} | Verbatim Check: {item.get('verbatim_check')}")
        print(f" Description:       {item.get('criterion_description')}")
        excerpt = item.get("source_text_excerpt") or "(None)"
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        print(f" Excerpt:           \"{excerpt}\"")
        if item.get("reviewer_decision"):
            print(f" Review:            {item.get('reviewer_decision')} by {item.get('reviewed_by')} at {item.get('reviewed_at')}")
            print(f" Notes:             {item.get('reviewer_notes')}")
        print("-" * 90)

    # Print summary breakdown
    print_summary(queue_path)


def show_criterion(criterion_code: str, queue_path: Path | None = None) -> None:
    items = load_queue(queue_path)
    clean_code = criterion_code.strip()
    match = next((x for x in items if x.get("criterion_code") == clean_code), None)
    if not match:
        print(f"Error: Criterion '{criterion_code}' not found in verification queue.")
        sys.exit(1)

    print("\n" + "=" * 90)
    print(f"CRITERION VERIFICATION DETAIL: {match.get('criterion_code')}")
    print("=" * 90)
    print(f"Policy ID:           {match.get('policy_id')}")
    print(f"Criterion Name:      {match.get('criterion_name')}")
    print(f"Is Exclusion:        {match.get('is_exclusion')}")
    print(f"Queue Status:        {match.get('status')}")
    print(f"Verbatim Check:      {match.get('verbatim_check')}")
    print("\n--- STATUTORY CRITERION DESCRIPTION ---")
    print(match.get("criterion_description"))
    print("\n--- SOURCE TEXT EXCERPT (POLICY CITATION) ---")
    print(match.get("source_text_excerpt") or "(No excerpt recorded)")
    print("\n--- LIVE MCD DOCUMENT PASSAGE ---")
    print(match.get("mcd_passage") or "(No corresponding MCD document passage stored)")
    print("\n--- HUMAN REVIEW AUDIT TRAIL ---")
    if match.get("reviewer_decision"):
        print(f"Reviewer Decision:   {match.get('reviewer_decision')}")
        print(f"Reviewed By:         {match.get('reviewed_by')}")
        print(f"Reviewed At:         {match.get('reviewed_at')}")
        print(f"Reviewer Notes:      {match.get('reviewer_notes')}")
    else:
        print("Reviewer Decision:   PENDING (No review recorded yet)")
    print("=" * 90 + "\n")


def record_review(
    criterion_code: str,
    decision: str,
    reviewer: str = "",
    notes: str = "",
    overwrite: bool = False,
    queue_path: Path | None = None,
    queue_file: Path | None = None,
    reviewer_name: str | None = None,
    exit_on_error: bool = False,
) -> tuple[bool, str]:
    effective_path = queue_file or queue_path or QUEUE_FILE
    effective_reviewer = (reviewer_name or reviewer).strip()

    def fail(msg: str) -> tuple[bool, str]:
        if exit_on_error:
            print(msg)
            sys.exit(1)
        return False, msg

    clean_code = criterion_code.strip()
    decision_clean = decision.strip().upper()
    if decision_clean in ["ACCEPT", "APPROVE"]:
        normalized_decision = "APPROVE"
        target_status = "ACCEPTED"
    elif decision_clean == "REJECT":
        normalized_decision = "REJECT"
        target_status = "REJECTED"
    else:
        return fail(f"Error: Decision must be 'APPROVE' (or 'ACCEPT') or 'REJECT', got '{decision}'")

    if is_agent_reviewer(effective_reviewer):
        msg = (
            "\n" + "!" * 90 + "\n"
            "SECURITY & GOVERNANCE VIOLATION:\n"
            f"Agent self-approval is strictly prohibited. Reviewer '{effective_reviewer}' appears to be an automated agent.\n"
            "Policy criteria must be verified and approved by a licensed clinician or designated human reviewer.\n"
            + "!" * 90 + "\n"
        )
        return fail(msg)

    if not notes or not notes.strip():
        return fail("Error: Reviewer notes are required; an empty note is refused. Reviewer notes are mandatory.")

    items = load_queue(effective_path)
    match = next((x for x in items if x.get("criterion_code") == clean_code), None)
    if not match:
        return fail(f"Error: Criterion '{criterion_code}' not found in verification queue.")

    # Check overwrite rule
    already_reviewed = match.get("status") in ["ACCEPTED", "REJECTED"] or match.get("reviewer_decision") is not None
    if already_reviewed and not overwrite:
        return fail(
            f"Error: Criterion '{clean_code}' already has review status '{match.get('status')}'. "
            "Overwriting an existing decision requires --overwrite and an explanatory note."
        )

    # Check verbatim check rule on APPROVAL
    if target_status == "ACCEPTED":
        v_check = str(match.get("verbatim_check", "")).strip().upper()
        if v_check != "PASS":
            return fail(
                f"Error: Cannot approve criterion '{clean_code}' with verbatim check status '{v_check}'. "
                "A human may APPROVE only a criterion whose excerpt is verified verbatim against the live document (PASS)."
            )

    match["status"] = target_status
    match["reviewer_decision"] = normalized_decision
    match["reviewed_by"] = effective_reviewer
    match["reviewed_notes"] = notes.strip()
    match["reviewer_notes"] = notes.strip()
    match["reviewed_at"] = datetime.now(UTC).isoformat()

    save_queue(items, effective_path)
    succ_msg = (
        f"[+] Successfully recorded {normalized_decision} (status -> {target_status}) "
        f"for criterion '{clean_code}' by '{effective_reviewer}'."
    )
    if exit_on_error:
        print(f"\n{succ_msg}\n")
    return True, succ_msg


def activate_policy(
    policy_id: str,
    queue_path: Path | None = None,
    queue_file: Path | None = None,
    policies_dir: Path | None = None,
    exit_on_error: bool = False,
) -> tuple[bool, str]:
    """
    Computes per-policy readiness and flips a DRAFT policy to ACTIVE.
    Refuses if policy is already ACTIVE, not DRAFT, or not READY.
    """
    effective_path = queue_file or queue_path or QUEUE_FILE

    def fail(msg: str) -> tuple[bool, str]:
        if exit_on_error:
            print(msg)
            sys.exit(1)
        return False, msg

    clean_id = policy_id.strip()
    items = load_queue(effective_path)
    policy_criteria = [x for x in items if x.get("policy_id") == clean_id]
    if not policy_criteria:
        return fail(f"Error: No criteria found in verification queue for policy '{clean_id}'.")

    # Check policy file
    policy_file = None
    search_dirs = [policies_dir] if policies_dir else [
        ROOT_DIR / "app" / "data" / "policies",
        ROOT_DIR / "app" / "data" / "policies_extended",
    ]
    for p_dir in search_dirs:
        if p_dir:
            candidate = p_dir / f"{clean_id}.json"
            if candidate.exists():
                policy_file = candidate
                break

    if not policy_file:
        return fail(f"Error: Policy file for '{clean_id}' not found in search paths.")

    with open(policy_file, "r", encoding="utf-8") as f:
        p_data = json.load(f)

    current_status = str(p_data.get("status", "ACTIVE")).strip().upper()
    if current_status == "ACTIVE":
        return fail(f"Error: Policy '{clean_id}' is already ACTIVE; activation refused.")

    if current_status != "DRAFT":
        return fail(f"Error: Policy '{clean_id}' has lifecycle status '{current_status}', not DRAFT; activation refused.")

    # Check readiness: every criterion must be ACCEPTED
    unaccepted = [c for c in policy_criteria if c.get("status") != "ACCEPTED"]
    if unaccepted:
        pend_count = len([c for c in unaccepted if c.get("status") == "PENDING_HUMAN_REVIEW"])
        details = ", ".join(f"{u.get('criterion_code')}:{u.get('status')}" for u in unaccepted)
        return fail(
            f"Error: Policy '{clean_id}' cannot be activated because it is not READY. "
            f"PENDING: {pend_count}, unaccepted criteria: [{details}]."
        )

    # Activate
    p_data["status"] = "ACTIVE"
    p_data["policy_version"] = p_data.get("policy_version", "1.0").replace("DRAFT-", "v")
    if "cms_reference" in p_data and isinstance(p_data["cms_reference"], dict):
        p_data["cms_reference"]["lifecycle_status"] = "ACTIVE"
        p_data["cms_reference"]["provenance_status"] = "VERIFIED_FROM_MCD"

    with open(policy_file, "w", encoding="utf-8") as f:
        json.dump(p_data, f, indent=2)

    # Also update policy_status in queue records
    for c in items:
        if c.get("policy_id") == clean_id:
            c["policy_status"] = "ACTIVE"
    save_queue(items, effective_path)

    succ_msg = f"[+] SUCCESS: Policy '{clean_id}' activated (status flipped DRAFT -> ACTIVE)."
    if exit_on_error:
        print(f"\n{succ_msg}\n")
    return True, succ_msg


def print_summary(queue_path: Path | None = None) -> None:
    items = load_queue(queue_path)
    total = len(items)
    pending = sum(1 for x in items if x.get("status") == "PENDING_HUMAN_REVIEW")
    accepted = sum(1 for x in items if x.get("status") == "ACCEPTED")
    rejected = sum(1 for x in items if x.get("status") == "REJECTED")

    pass_v = sum(1 for x in items if x.get("verbatim_check") == "PASS")
    fail_v = sum(1 for x in items if x.get("verbatim_check") == "FAIL")
    no_doc_v = sum(1 for x in items if x.get("verbatim_check") == "NO_DOCUMENT")

    # Policy counts
    policies = {x.get("policy_id") for x in items if x.get("policy_id")}

    print("\n" + "=" * 60)
    print("POLICY CRITERIA VERIFICATION QUEUE SUMMARY")
    print("=" * 60)
    print(f"Total Criteria in Queue:        {total}")
    print(f"Total Policies Represented:     {len(policies)}")
    print("\nHuman Review Status:")
    print(f"  - PENDING_HUMAN_REVIEW:       {pending}")
    print(f"  - ACCEPTED (Human Approved):  {accepted}")
    print(f"  - REJECTED (Human Rejected):  {rejected}")
    print("\nVerbatim Citation Audit Breakdown:")
    print(f"  - PASS (Verbatim Quote Match): {pass_v}")
    print(f"  - FAIL (Citation Mismatch):   {fail_v}")
    print(f"  - NO_DOCUMENT (No Live MCD):   {no_doc_v}")
    print("\nProvenance State:")
    print(f"  - Grandfathered Active Catalog: {total} criteria across {len(policies)} policies")
    print(f"  - Workflow-Verified (Human):    {accepted} criteria")
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Human Review Mechanism for Policy Criteria Verification")
    parser.add_argument("--list", action="store_true", help="List criteria in verification queue")
    parser.add_argument("--summary", action="store_true", help="Print verification queue summary metrics")
    parser.add_argument("--show", type=str, help="Show single criterion detail with source passage and excerpt")
    parser.add_argument("--policy", type=str, help="Filter by Policy ID")
    parser.add_argument("--status", type=str, help="Filter by status (PENDING_HUMAN_REVIEW, ACCEPTED, REJECTED)")
    parser.add_argument("--record", type=str, help="Criterion code to record review decision for")
    parser.add_argument("--decision", type=str, choices=["APPROVE", "REJECT", "ACCEPT", "approve", "reject", "accept"], help="Review decision")
    parser.add_argument("--reviewer", type=str, help="Name or clinician ID of human reviewer (agents prohibited)")
    parser.add_argument("--notes", type=str, default="", help="Auditable clinical review rationale (required)")
    parser.add_argument("--overwrite", action="store_true", help="Allow updating an existing review decision")
    parser.add_argument("--activate-policy", type=str, help="Activate a READY DRAFT policy to ACTIVE")
    parser.add_argument("--queue-file", type=str, help="Optional custom path to queue JSON file")

    args = parser.parse_args()
    q_path = Path(args.queue_file) if args.queue_file else None

    if args.record:
        if not args.decision or not args.reviewer:
            print("Error: --record requires both --decision and --reviewer (and non-empty --notes).")
            sys.exit(1)
        record_review(
            args.record,
            args.decision,
            args.reviewer,
            args.notes,
            overwrite=args.overwrite,
            queue_path=q_path,
            exit_on_error=True,
        )
    elif args.activate_policy:
        activate_policy(args.activate_policy, queue_path=q_path, exit_on_error=True)
    elif args.show:
        show_criterion(args.show, queue_path=q_path)
    elif args.list:
        list_entries(policy_id=args.policy, status_filter=args.status, queue_path=q_path)
    elif args.summary:
        print_summary(queue_path=q_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
