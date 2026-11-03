from typing import List, Dict, Any, Optional
from app.schemas.contracts import CriterionAssessment, DeterminationStatus


class MissingEvidenceAgent:
    """
    Missing Evidence Agent.
    Sub-task: Inspects deferred or incomplete cases and formulates targeted, actionable
    clinical questions and documentation checklist items that a human reviewer must answer.

    Eliminates vague deferrals by turning missing or ambiguous criteria into exact
    clinical inquiries (e.g. asking for specific diagnostic modality, duration dates,
    or quantitative thresholds).
    """

    def __init__(self):
        pass

    def formulate_questions(
        self,
        criteria_assessments: List[CriterionAssessment],
        policy_title: str
    ) -> List[str]:
        """
        Formulates precise clinical questions for all missing or insufficient criteria.
        """
        questions: List[str] = []

        for assess in criteria_assessments:
            code = assess.criterion_code
            name = assess.name or code
            desc = assess.description
            status = assess.status

            if status in [DeterminationStatus.INSUFFICIENT_EVIDENCE, DeterminationStatus.NOT_MET] and not assess.is_exclusion:
                c_lower = f"{code} {name} {desc}".lower()

                if "lvef" in c_lower or "ejection fraction" in c_lower:
                    questions.append(
                        f"[{code}] Quantitative LVEF Documentation: Please provide formal echocardiography, CMR, or MUGA report confirming whether resting LVEF is <= 35%."
                    )
                elif "nyha" in c_lower or "functional class" in c_lower:
                    questions.append(
                        f"[{code}] NYHA Functional Assessment: What specific NYHA functional class (II, III, or IV) was documented during the most recent clinical evaluation?"
                    )
                elif "gdmt" in c_lower or "medical therapy" in c_lower:
                    questions.append(
                        f"[{code}] GDMT Duration & Optimization: Has the patient been maintained on tolerated guideline-directed medical therapy (beta-blocker, ACEi/ARB/ARNI, MRA) for >= 90 days? If truncated, please document clinical intolerance."
                    )
                elif "mi" in c_lower or "revascularization" in c_lower or "waiting period" in c_lower:
                    questions.append(
                        f"[{code}] Statutory Timeline Verification: What was the exact calendar date of the patient's qualifying MI (>=40 days required) or CABG/PCI (>=90 days required)?"
                    )
                elif "ahi" in c_lower or "sleep" in c_lower or "polysomnography" in c_lower:
                    questions.append(
                        f"[{code}] Polysomnography Data: What is the formal Apnea-Hypopnea Index (AHI) or Respiratory Disturbance Index (RDI) from the diagnostic sleep study, and are documented comorbidities present?"
                    )
                elif "aortic stenosis" in c_lower or "tavr" in c_lower or "valve" in c_lower:
                    questions.append(
                        f"[{code}] Hemodynamic AS Quantification: Please provide Doppler echocardiogram showing aortic valve area (AVA <= 1.0 cm2), mean gradient (>= 40 mmHg), or peak velocity (>= 4.0 m/s)."
                    )
                elif "hbot" in c_lower or "wagner" in c_lower or "hyperbaric" in c_lower:
                    questions.append(
                        f"[{code}] Wound Staging & Standard Care Duration: Has the diabetic lower extremity wound failed at least 30 continuous days of standard wound care, and is Wagner Grade III or higher documented?"
                    )
                else:
                    questions.append(
                        f"[{code}] Clinical Evidence Gap: Patient chart lacks verified documentation satisfying statutory requirement '{name}'. Please provide supporting clinical notes."
                    )

        return questions

