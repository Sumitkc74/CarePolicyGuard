"""
Clinical Timeline and Longitudinal Waiting-Period Reasoning Engine for CarePolicyGuard.

Evaluates elapsed calendar days between clinical event milestones (e.g., Acute MI,
CABG, PCI, GDMT start) and procedure evaluation dates against CMS statutory waiting periods
(e.g., NCD 20.4 mandates >= 40 days post-MI and >= 90 days post-revascularization).
"""

from typing import Dict, List, Optional
from datetime import datetime, date
import re
from pydantic import BaseModel, Field


class TimelineMilestone(BaseModel):
    event_type: str
    event_label: str
    event_date: str
    evaluation_date: str
    elapsed_days: int
    required_days: int
    deficit_days: int
    status: str  # "SATISFIED", "WAITING_PERIOD_UNMET", "NOT_SPECIFIED"
    citation: str
    advisory: str


class TimelineAnalysisResult(BaseModel):
    policy_id: str
    all_waiting_periods_satisfied: bool
    milestones: List[TimelineMilestone] = Field(default_factory=list)
    overall_timeline_advisory: str


class TimelineAnalyzerService:
    """Parses clinical event dates and validates statutory waiting periods."""

    DATE_PATTERNS = [
        # YYYY-MM-DD
        r'\b(20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b',
        # MM/DD/YYYY
        r'\b((?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:20\d{2}))\b',
        # Month DD, YYYY (e.g. January 10, 2026)
        r'\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+20\d{2})\b',
    ]

    @classmethod
    def _parse_date(cls, date_str: str) -> Optional[date]:
        """Tries parsing multiple standard clinical date formats."""
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y"
        ]
        date_str = date_str.strip()
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def extract_evaluation_date(cls, text: str) -> date:
        """Extracts DOS / Encounter / Note date, falling back to current date."""
        dos_pattern = re.compile(
            r'(?:Date of (?:Service|Evaluation|Encounter|Exam|Note)|DOS|Encounter Date)\s*:?\s*('
            r'20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2}|[A-Za-z]+\s+\d{1,2},\s+20\d{2})',
            re.IGNORECASE
        )
        match = dos_pattern.search(text)
        if match:
            parsed = cls._parse_date(match.group(1))
            if parsed:
                return parsed

        # Search for any standalone date on the first 3 lines
        first_lines = "\n".join(text.splitlines()[:4])
        for p in cls.DATE_PATTERNS:
            found = re.search(p, first_lines, re.IGNORECASE)
            if found:
                parsed = cls._parse_date(found.group(1))
                if parsed:
                    return parsed

        return date.today()

    @classmethod
    def evaluate_timeline(cls, policy_id: str, ehr_narrative: str) -> TimelineAnalysisResult:
        """
        Analyzes longitudinal milestones and verifies compliance with policy waiting periods.
        """
        eval_date = cls.extract_evaluation_date(ehr_narrative)
        milestones: List[TimelineMilestone] = []

        if policy_id == "NCD-20.4":
            # 1. Post-Myocardial Infarction Waiting Period (>= 40 days)
            mi_pattern = re.compile(
                r'(?:post-)?(?:myocardial infarction|acute MI|STEMI|NSTEMI)\s*(?:on|dated|occurred|from|in)?\s*:?\s*('
                r'20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2}|[A-Za-z]+\s+\d{1,2},\s+20\d{2})',
                re.IGNORECASE
            )
            mi_match = mi_pattern.search(ehr_narrative)
            if mi_match:
                mi_date_raw = mi_match.group(1)
                mi_date = cls._parse_date(mi_date_raw)
                if mi_date:
                    elapsed = (eval_date - mi_date).days
                    required = 40
                    is_met = elapsed >= required
                    deficit = max(0, required - elapsed)
                    milestones.append(TimelineMilestone(
                        event_type="POST_MYOCARDIAL_INFARCTION",
                        event_label="Post-Myocardial Infarction Waiting Period",
                        event_date=mi_date.isoformat(),
                        evaluation_date=eval_date.isoformat(),
                        elapsed_days=elapsed,
                        required_days=required,
                        deficit_days=deficit,
                        status="SATISFIED" if is_met else "WAITING_PERIOD_UNMET",
                        citation="CMS NCD 20.4 Section B.1 (>= 40 days post-MI requirement)",
                        advisory=(
                            f"Passed: {elapsed} days elapsed since MI on {mi_date} (Required: >= {required} days)."
                            if is_met else
                            f"Premature Procedure Warning: Only {elapsed} days elapsed since MI on {mi_date}. "
                            f"CMS NCD 20.4 mandates at least {required} days post-MI. Deficit of {deficit} days. "
                            f"Elective implantation prior to {date.fromordinal(mi_date.toordinal() + required)} will trigger non-coverage denial."
                        )
                    ))

            # 2. Post-Revascularization (CABG / PCI) Waiting Period (>= 90 days)
            revasc_pattern = re.compile(
                r'(?:CABG|coronary artery bypass|PCI|percutaneous coronary intervention|stent placement|revascularization)\s*(?:on|performed|dated)?\s*:?\s*('
                r'20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2}|[A-Za-z]+\s+\d{1,2},\s+20\d{2})',
                re.IGNORECASE
            )
            revasc_match = revasc_pattern.search(ehr_narrative)
            if revasc_match:
                revasc_date_raw = revasc_match.group(1)
                revasc_date = cls._parse_date(revasc_date_raw)
                if revasc_date:
                    elapsed = (eval_date - revasc_date).days
                    required = 90
                    is_met = elapsed >= required
                    deficit = max(0, required - elapsed)
                    milestones.append(TimelineMilestone(
                        event_type="POST_REVASCULARIZATION",
                        event_label="Post-Revascularization (CABG/PCI) Waiting Period",
                        event_date=revasc_date.isoformat(),
                        evaluation_date=eval_date.isoformat(),
                        elapsed_days=elapsed,
                        required_days=required,
                        deficit_days=deficit,
                        status="SATISFIED" if is_met else "WAITING_PERIOD_UNMET",
                        citation="CMS NCD 20.4 Section B.2 (>= 90 days post-revascularization)",
                        advisory=(
                            f"Passed: {elapsed} days elapsed since revascularization on {revasc_date} (Required: >= {required} days)."
                            if is_met else
                            f"Premature Revascularization Warning: Only {elapsed} days elapsed since revascularization on {revasc_date}. "
                            f"CMS mandates >= {required} days. Deficit: {deficit} days. Reschedule elective procedure after "
                            f"{date.fromordinal(revasc_date.toordinal() + required)}."
                        )
                    ))

        # Check overall timeline satisfaction
        has_violations = any(m.status == "WAITING_PERIOD_UNMET" for m in milestones)
        all_satisfied = not has_violations

        if has_violations:
            overall_advisory = (
                "Statutory Timeline Deficiency Detected: Patient does not yet meet Medicare post-event waiting periods. "
                "Immediate submission will be rejected by CMS MAC auditors for premature intervention."
            )
        elif milestones:
            overall_advisory = (
                f"Timeline Compliance Verified: All clinical event intervals ({len(milestones)} milestones evaluated) "
                f"fully satisfy Medicare longitudinal waiting periods."
            )
        else:
            overall_advisory = "No longitudinal event restrictions triggered by documented clinical milestones."

        return TimelineAnalysisResult(
            policy_id=policy_id,
            all_waiting_periods_satisfied=all_satisfied,
            milestones=milestones,
            overall_timeline_advisory=overall_advisory
        )

