"""
Minimal Review Mechanism for ConceptMap Candidate Entries (Task 2).
Provides an auditable CLI for human clinicians to inspect pending entries,
verify policy grounding and governing-rule flags, and record ACCEPT / REJECT decisions.

Enforces strict separation:
- Agents can draft candidate entries into PENDING status.
- Only human reviewers can record approvals. Automated agents are blocked from self-approving.
"""

import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT_DIR / "app" / "data" / "concept_map" / "draft_concept_entries.json"

FORBIDDEN_AGENT_KEYWORDS = ["agent", "llm", "antigravity", "bot", "assistant", "system", "auto"]

def load_queue():
    if not QUEUE_FILE.exists():
        print(f"Queue file {QUEUE_FILE} does not exist.")
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_queue(items):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

def list_entries(policy_id=None, status_filter=None, show_flag=None):
    items = load_queue()
    filtered = items
    if policy_id:
        filtered = [x for x in filtered if x.get("policy_id") == policy_id]
    if status_filter:
        filtered = [x for x in filtered if x.get("status") == status_filter]
    if show_flag:
        filtered = [x for x in filtered if x.get("governing_rule_check") == show_flag]

    print("\n" + "=" * 80)
    print(f"CONCEPT MAP REVIEW QUEUE: {len(filtered)} matching entries (Total in Queue: {len(items)})")
    print("=" * 80)

    for item in filtered:
        print(f"\n[Entry ID]:         {item.get('entry_id')}")
        print(f" Policy:            {item.get('policy_id')} | Criterion: {item.get('criterion_code')}")
        print(f" Canonical Name:    {item.get('canonical_name')}")
        print(f" Status:            {item.get('status')}")
        print(f" Governing Flag:    {item.get('governing_rule_check')}")
        print(f" Grounding Quote:   \"{item.get('grounding_quote')}\"")
        if item.get("attested_note_phrasing"):
            print(f" Attested Phrasing: \"{item.get('attested_note_phrasing')}\"")
        print(f" Accepted Terms:    {', '.join(item.get('accepted_terms', []))}")
        print(f" Near Misses:       {', '.join(item.get('prohibited_near_misses', []))}")
        print(f" Rule Rationale:    {item.get('governing_rule_rationale')}")
        if item.get("reviewer_decision"):
            print(f" Reviewer Decision: {item.get('reviewer_decision')} by {item.get('reviewed_by')} at {item.get('reviewed_at')}")
            print(f" Reviewer Notes:    {item.get('reviewer_notes')}")
        print("-" * 80)

def record_review(entry_id, decision, reviewer, notes):
    decision_clean = decision.strip().upper()
    if decision_clean not in ["ACCEPT", "REJECT"]:
        print(f"Error: Decision must be 'ACCEPT' or 'REJECT', got '{decision}'")
        sys.exit(1)

    reviewer_clean = reviewer.strip().lower()
    if any(k in reviewer_clean for k in FORBIDDEN_AGENT_KEYWORDS):
        print("\n" + "!" * 80)
        print("SECURITY & GOVERNANCE VIOLATION:")
        print(f"Agent self-approval is strictly prohibited. Reviewer '{reviewer}' appears to be an automated agent.")
        print("ConceptMap entries must be reviewed and approved by a licensed clinician or designated human reviewer.")
        print("!" * 80 + "\n")
        sys.exit(1)

    items = load_queue()
    found = False
    for item in items:
        if item.get("entry_id") == entry_id:
            found = True
            item["status"] = "ACCEPTED" if decision_clean == "ACCEPT" else "REJECTED"
            item["reviewer_decision"] = decision_clean
            item["reviewed_by"] = reviewer.strip()
            item["reviewer_notes"] = notes.strip()
            item["reviewed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"\n[+] Successfully recorded {decision_clean} decision for {entry_id} by {reviewer}.")
            break

    if not found:
        print(f"Error: Entry ID '{entry_id}' not found in queue.")
        sys.exit(1)

    save_queue(items)

def print_summary():
    items = load_queue()
    total = len(items)
    pending = sum(1 for x in items if x.get("status") == "PENDING_HUMAN_REVIEW")
    accepted = sum(1 for x in items if x.get("status") == "ACCEPTED")
    rejected = sum(1 for x in items if x.get("status") == "REJECTED")

    pass_equiv = sum(1 for x in items if x.get("governing_rule_check") == "PASS_EQUIVALENCE")
    needs_human = sum(1 for x in items if x.get("governing_rule_check") == "NEEDS_HUMAN_JUDGMENT")
    no_grounding = sum(1 for x in items if x.get("governing_rule_check") == "REJECTED_NO_GROUNDING")

    print("\n" + "=" * 60)
    print("CONCEPT REVIEW QUEUE SUMMARY")
    print("=" * 60)
    print(f"Total Entries:                  {total}")
    print(f"  - Pending Human Review:       {pending}")
    print(f"  - Human Accepted:             {accepted}")
    print(f"  - Human Rejected:             {rejected}")
    print("\nGoverning Rule Pre-Audit Flags:")
    print(f"  - PASS_EQUIVALENCE:           {pass_equiv}")
    print(f"  - NEEDS_HUMAN_JUDGMENT:       {needs_human}")
    print(f"  - REJECTED_NO_GROUNDING:      {no_grounding}")
    print("=" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Human Review Mechanism for ConceptMap Candidate Entries")
    parser.add_argument("--list", action="store_true", help="List entries in review queue")
    parser.add_argument("--summary", action="store_true", help="Print queue summary metrics")
    parser.add_argument("--policy", type=str, help="Filter by Policy ID")
    parser.add_argument("--status", type=str, help="Filter by status (PENDING_HUMAN_REVIEW, ACCEPTED, REJECTED)")
    parser.add_argument("--flag", type=str, help="Filter by governing rule flag (PASS_EQUIVALENCE, NEEDS_HUMAN_JUDGMENT)")
    parser.add_argument("--review", type=str, help="Entry ID to review")
    parser.add_argument("--decision", type=str, choices=["ACCEPT", "REJECT", "accept", "reject"], help="Decision: ACCEPT or REJECT")
    parser.add_argument("--reviewer", type=str, help="Name or clinician ID of human reviewer (agents forbidden)")
    parser.add_argument("--notes", type=str, default="", help="Auditable clinical rationale for decision")

    args = parser.parse_args()

    if args.review:
        if not args.decision or not args.reviewer:
            print("Error: --review requires both --decision and --reviewer")
            sys.exit(1)
        record_review(args.review, args.decision, args.reviewer, args.notes)
    elif args.list:
        list_entries(policy_id=args.policy, status_filter=args.status, show_flag=args.flag)
    elif args.summary:
        print_summary()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
