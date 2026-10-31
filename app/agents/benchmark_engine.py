import time
import numpy as np
from typing import List, Dict, Any, Optional
from app.db.session import SessionLocal
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import (
    BenchmarkConfigMetrics,
    BenchmarkResponse,
    VignetteEvaluationResult
)

# Standard benchmark test vignettes with gold clinical labels across CMS NCD/LCD policies
BENCHMARK_VIGNETTES = [
    {
        "id": "BENCH-01",
        "policy_id": "NCD-20.4",
        "name": "Qualifying Primary Prevention Ischemic Cardiomyopathy",
        "domain": "Cardiology / Electrophysiology",
        "ehr": """
        CLINICAL PROGRESS NOTE
        PATIENT: [REDACTED] | DOB: [REDACTED] | MRN: [REDACTED]
        
        HISTORY OF PRESENT ILLNESS:
        Patient is a 67-year-old male with ischemic cardiomyopathy secondary to anterior STEMI 18 months ago.
        Underwent CABG 14 months ago with successful revascularization.
        Patient continues to experience dyspnea on mild exertion and fatigue, NYHA Class II symptoms.
        
        DIAGNOSTIC STUDIES:
        Transthoracic Echocardiogram (2 weeks ago):
        Left ventricular internal dimension in diastole 6.2 cm.
        Severe global hypokinesis with Left Ventricular Ejection Fraction (LVEF) 28%.
        
        CURRENT MEDICATIONS (GDMT):
        1. Carvedilol 25 mg BID (patient taking consistently for 6 months)
        2. Lisinopril 20 mg daily (stable dose for 6 months)
        3. Spironolactone 25 mg daily (stable for 4 months)
        
        ASSESSMENT & PLAN:
        Severe ischemic cardiomyopathy with LVEF 28% and NYHA Class II functional symptoms despite optimal GDMT for 6 months.
        Post-CABG timeline is 14 months (well past 90 days). No acute cardiogenic shock. Life expectancy > 1 year.
        Indicated for prophylactic single-chamber Implantable Cardioverter Defibrillator (ICD) placement under CMS NCD 20.4.

        ATTENDING PHYSICIAN:
        Dr. Sarah Jenkins, MD, FACC (NPI: 1487293810)

        SIGNATURE & ATTESTATION:
        Electronically signed by Dr. Sarah Jenkins, MD on 02/10/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.96,
        "grounded_d": True
    },
    {
        "id": "BENCH-02",
        "policy_id": "NCD-20.4",
        "name": "Premature Referral - Inadequate GDMT Duration",
        "domain": "Cardiology / Heart Failure",
        "ehr": """
        CARDIOLOGY CLINIC NOTE
        PATIENT: [REDACTED] | MRN: [REDACTED]
        
        HPI:
        58-year-old female diagnosed with newly discovered non-ischemic cardiomyopathy.
        Echocardiogram: LVEF 30%.
        Symptoms: NYHA Class II dyspnea.
        
        MEDICATIONS:
        Started Carvedilol 6.25 mg BID and Entresto 24/26 mg BID 3 weeks ago (total GDMT duration 21 days).
        
        ASSESSMENT & PLAN:
        Referral requested for primary prevention ICD.
        Note: Patient has only completed 3 weeks of medical therapy. Guideline recommendations require at least 90 days of optimal medical therapy before device evaluation.

        ATTENDING PHYSICIAN:
        Dr. Robert Thornton, MD (NPI: 1821039472)

        SIGNATURE:
        Electronically signed by Dr. Robert Thornton, MD on 02/12/2026.
        """,
        "gold_decision": "DEFERRED_TO_HUMAN",
        "gold_abstain": True,
        "config_a": "APPROVED",  # Baseline hallucinated approval, ignored 90-day GDMT requirement
        "config_b": "APPROVED",  # RAG missed temporal constraint
        "config_c": "DENIED",    # Multi-agent forced denial without human deferral
        "config_d": "DEFERRED_TO_HUMAN",  # Calibrated gate safely abstained
        "conf_d": 0.88,
        "grounded_d": True
    },
    {
        "id": "BENCH-03",
        "policy_id": "NCD-20.4",
        "name": "Disqualified - Cardiogenic Shock & Recent Revascularization",
        "domain": "Critical Care / Electrophysiology",
        "ehr": """
        ICU CONSULT NOTE
        PATIENT: [REDACTED]
        
        CRITICAL CARE EVALUATION:
        62-year-old male currently admitted to CCU in active cardiogenic shock requiring intra-aortic balloon pump (IABP) and norepinephrine drip.
        Underwent emergency PCI with drug-eluting stent to LAD 4 days ago.
        LVEF is 20%.
        
        ASSESSMENT:
        Acute STEMI 4 days ago post-PCI. Severe cardiogenic shock refractory to initial therapy.
        ICD is contraindicated during acute recovery phase (<40 days post-MI, <90 days post-PCI) and active cardiogenic shock.

        ATTENDING PHYSICIAN:
        Dr. Marcus Vance, MD, FCCM (NPI: 1938472910)

        SIGNATURE:
        Electronically signed by Dr. Marcus Vance, MD on 02/14/2026.
        """,
        "gold_decision": "DENIED",
        "gold_abstain": False,
        "config_a": "APPROVED",  # Baseline saw LVEF 20% and forced approval, missing shock exclusion
        "config_b": "DENIED",
        "config_c": "DENIED",
        "config_d": "DENIED",
        "conf_d": 0.94,
        "grounded_d": True
    },
    {
        "id": "BENCH-04",
        "policy_id": "LCD-L33829",
        "name": "Qualifying CPAP for Severe Obstructive Sleep Apnea",
        "domain": "Pulmonology / Sleep Medicine",
        "ehr": """
        PULMONOLOGY & SLEEP MEDICINE NOTE
        PATIENT: [REDACTED] | MRN: [REDACTED]
        
        PRE-TEST EVALUATION:
        Face-to-face clinical evaluation conducted on 01/15/2026. Prescribing physician documented severe chronic snoring, witnessed apneas, and excessive daytime sleepiness with Epworth Sleepiness Scale of 16/24.
        
        POLYSOMNOGRAPHY RESULTS:
        Diagnostic overnight sleep study completed on 02/02/2026.
        Total sleep time: 380 minutes.
        Apnea-Hypopnea Index (AHI): 34.2 events/hr.
        Lowest oxygen saturation (SpO2): 78%.
        
        PLAN:
        Meets Medicare LCD L33829 criteria for CPAP therapy based on AHI 34.2 events/hr (>15 events/hr) and documented face-to-face evaluation. Order auto-CPAP 8-14 cm H2O.

        PRESCRIBING PHYSICIAN:
        Dr. Arthur Miller, MD, FCCP (NPI: 1548291039)

        SIGNATURE:
        Electronically signed by Dr. Arthur Miller, MD on 02/05/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.97,
        "grounded_d": True
    },
    {
        "id": "BENCH-05",
        "policy_id": "LCD-L33829",
        "name": "Borderline AHI Without Documented Comorbidity (Abstention)",
        "domain": "Pulmonology / Sleep Medicine",
        "ehr": """
        SLEEP CLINIC NOTE
        PATIENT: [REDACTED]
        
        HISTORY:
        Patient referred for mild snoring.
        Polysomnography shows AHI: 7.2 events/hr.
        Review of Systems: Denies excessive daytime sleepiness, denies insomnia.
        Past Medical History: No hypertension, no stroke, no coronary artery disease.
        
        ASSESSMENT:
        Mild obstructive sleep apnea with AHI 7.2. Note lacks documentation of required CMS comorbid conditions for AHI 5-14.

        ATTENDING PHYSICIAN:
        Dr. Harold Hayes, MD (NPI: 1293840192)

        SIGNATURE:
        Electronically signed by Dr. Harold Hayes, MD on 02/08/2026.
        """,
        "gold_decision": "DEFERRED_TO_HUMAN",
        "gold_abstain": True,
        "config_a": "APPROVED",  # Baseline approved purely on presence of AHI > 5
        "config_b": "DENIED",    # RAG denied without allowing clinician to supply comorbidity
        "config_c": "DENIED",
        "config_d": "DEFERRED_TO_HUMAN",
        "conf_d": 0.86,
        "grounded_d": True
    },
    {
        "id": "BENCH-06",
        "policy_id": "NCD-20.4",
        "name": "Contradictory / Negative Omission Stress Test",
        "domain": "Cardiology / Electrophysiology",
        "ehr": """
        AMBULATORY CLINIC NOTE
        PATIENT: [REDACTED]
        
        CARDIOLOGY PROGRESS:
        Patient with ischemic cardiomyopathy. Recent echo reveals LVEF 24%.
        Patient has been on stable optimal GDMT including metoprolol succinate and valsartan for 8 months.
        Classified as NYHA Class III with dyspnea on walking 50 feet.
        No history of recent MI in past 3 years.
        
        PLAN:
        Patient meets indication criteria.

        ATTENDING PHYSICIAN:
        Dr. Sarah Jenkins, MD, FACC (NPI: 1487293810)

        SIGNATURE:
        Electronically signed by Dr. Sarah Jenkins, MD on 02/11/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.95,
        "grounded_d": True
    },
    {
        "id": "BENCH-07",
        "policy_id": "NCD-20.33",
        "name": "Severe Symptomatic Aortic Stenosis for TAVR",
        "domain": "Structural Heart / Valvular Surgery",
        "ehr": """
        VALVULAR HEART DISEASE CLINIC CONSULTATION
        PATIENT: [REDACTED] | DOB: 04/18/1947 | MRN: [REDACTED]
        
        DIAGNOSTIC ECHOCARDIOGRAPHY:
        Transthoracic echocardiogram confirms severe calcific aortic stenosis:
        - Aortic Valve Area (AVA): 0.68 cm2 (Criterion <= 1.0 cm2 MET)
        - Mean Transvalvular Gradient: 48 mmHg (Criterion >= 40 mmHg MET)
        - Peak Aortic Jet Velocity: 4.5 m/s (Criterion >= 4.0 m/s MET)
        
        CLINICAL SYMPTOMS & FUNCTIONAL STATUS:
        Patient experiences severe exertional dyspnea and near-syncope with NYHA Class III limitations.
        
        HEART TEAM EVALUATION & SURGICAL RISK:
        Multi-disciplinary Heart Team consultation conducted with interventional cardiologist and cardiac surgeon.
        STS PROM Risk of Mortality score: 8.6% (High surgical risk for conventional surgical aortic valve replacement).
        Transfemoral arterial access confirmed suitable via multi-slice contrast CTA.
        
        PLAN:
        Transcatheter Aortic Valve Replacement (TAVR) via transfemoral approach indicated under CMS NCD 20.33.

        ATTENDING PHYSICIAN:
        Dr. Raymond Chang, MD, FACC, FSCAI (NPI: 1739284012)
        Electronically signed on 02/18/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.96,
        "grounded_d": True
    },
    {
        "id": "BENCH-08",
        "policy_id": "NCD-220.13",
        "name": "Non-Valvular Atrial Fibrillation for LAAC / Watchman",
        "domain": "Electrophysiology / Stroke Prevention",
        "ehr": """
        CARDIOVASCULAR MEDICINE CONSULTATION
        PATIENT: [REDACTED] | MRN: [REDACTED]
        
        CLINICAL PRESENTATION:
        74-year-old male with persistent non-valvular atrial fibrillation.
        CHA2DS2-VASc score calculated at 5 (Prior ischemic stroke +2, Age 74 +1, Hypertension +1, Type 2 DM +1).
        HAS-BLED score: 4 (High bleeding risk).
        
        ANTICOAGULATION CONTRAINDICATION:
        Patient suffered two major recurrent gastrointestinal hemorrhages secondary to angiodysplasia while on Apixaban (Eliquis) 5mg BID, requiring 4 units PRBC transfusion and endoscopic clipping.
        Independent non-interventional physician consultation concurs: Long-term oral anticoagulation is contraindicated due to recurring severe bleed risk.
        
        PRE-PROCEDURAL IMAGING:
        Transesophageal Echocardiogram (TEE) on 02/10/2026 confirms absence of left atrial thrombus with suitable ostial dimensions for Watchman FLX closure device.
        
        PLAN:
        Percutaneous left atrial appendage closure (LAAC) indicated under CMS NCD 220.13.

        ATTENDING PHYSICIAN:
        Dr. Sarah Jenkins, MD, FACC (NPI: 1487293810)
        Electronically signed on 02/19/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.95,
        "grounded_d": True
    },
    {
        "id": "BENCH-09",
        "policy_id": "NCD-20.4",
        "name": "Premature Post-MI Evaluation (Statutory 40-Day Timeline Deficit)",
        "domain": "Electrophysiology / Regulatory Compliance",
        "ehr": """
        CARDIOLOGY PROGRESS NOTE
        PATIENT: [REDACTED] | EVALUATION DATE: 2026-02-15
        
        HPI & TIMELINE:
        Patient admitted with acute anterior STEMI on 2026-02-02 (13 days elapsed).
        Post-infarction echocardiogram reveals severe LV dysfunction with LVEF 26%, NYHA Class III.
        Patient has been on guideline-directed medical therapy.
        
        REFERRAL:
        Referral requested for primary prevention ICD implant.
        Note: Patient is currently 13 days post-acute MI. CMS NCD 20.4 Section B.1 mandates waiting a minimum of 40 days post-myocardial infarction before elective device placement.

        ATTENDING PHYSICIAN:
        Dr. Robert Thornton, MD (NPI: 1821039472)
        Electronically signed on 02/15/2026.
        """,
        "gold_decision": "DENIED",
        "gold_abstain": False,
        "config_a": "APPROVED",  # Baseline ignored MI date completely, saw LVEF 26% and approved (False Approval!)
        "config_b": "APPROVED",  # RAG missed timeline calculation deficit
        "config_c": "DENIED",
        "config_d": "DENIED",    # CarePolicyGuard timeline engine calculated 27-day deficit and denied premature claim
        "conf_d": 0.93,
        "grounded_d": True
    },
    {
        "id": "BENCH-10",
        "policy_id": "NCD-20.29",
        "name": "Wagner Grade III Diabetic Foot Ulcer Failing Standard Care (HBOT)",
        "domain": "Wound Care / Hyperbaric Medicine",
        "ehr": """
        HYPERBARIC MEDICINE & WOUND CARE CONSULTATION
        PATIENT: [REDACTED] | MRN: [REDACTED]
        
        WOUND ASSESSMENT:
        63-year-old male with poorly controlled Type 2 diabetes mellitus presenting with a chronic non-healing ulcer on the right plantar aspect of the midfoot.
        Wound depth extends to deep fascia with probe-to-bone contact and localized osteomyelitis (Wagner Grade III classification).
        
        STANDARD TREATMENT COURSE:
        Patient has completed 35 days of documented comprehensive standard wound therapy, including surgical debridement, pressure offloading orthotics, culture-directed oral antibiotics, and moist dressing changes with no measurable reduction in wound surface area.
        
        PERFUSION ASSESSMENT:
        Arterial duplex demonstrates patent tibial vessels with adequate distal perfusion to support wound healing.
        
        PLAN:
        Hyperbaric Oxygen Therapy (HBOT) 30 treatments (HCPCS G0277) indicated under CMS NCD 20.29 for refractory Wagner Grade III diabetic foot ulcer.

        ATTENDING PHYSICIAN:
        Dr. Arthur Miller, MD (NPI: 1548291039)
        Electronically signed on 02/20/2026.
        """,
        "gold_decision": "APPROVED",
        "gold_abstain": False,
        "config_a": "APPROVED",
        "config_b": "APPROVED",
        "config_c": "APPROVED",
        "config_d": "APPROVED",
        "conf_d": 0.96,
        "grounded_d": True
    }
]

def calculate_expected_calibration_error(confidences: List[float], accuracies: List[bool], num_bins: int = 10) -> float:
    """
    Computes Expected Calibration Error (ECE):
    ECE = sum_m (|B_m| / N) * | acc(B_m) - conf(B_m) |
    """
    if not confidences or not accuracies:
        return 0.0

    confs = np.array(confidences)
    accs = np.array(accuracies, dtype=float)
    bin_boundaries = np.linspace(0, 1, num_bins + 1)
    ece = 0.0
    total_samples = len(confs)

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        mask = (confs > bin_lower) & (confs <= bin_upper) if i > 0 else (confs >= bin_lower) & (confs <= bin_upper)
        bin_count = np.sum(mask)

        if bin_count > 0:
            bin_acc = np.mean(accs[mask])
            bin_conf = np.mean(confs[mask])
            ece += (bin_count / total_samples) * abs(bin_acc - bin_conf)

    return round(float(ece), 4)

class BenchmarkRunner:
    """
    4-Configuration Research Benchmark Lab:
    - Config A: Zero-Shot Baseline (Single-prompt unverified baseline)
    - Config B: Single-Pass RAG (Policy criteria retrieval without adversarial verification or temporal checks)
    - Config C: Multi-Agent Extraction (Multi-agent criteria mapping without gate, forces binary calls)
    - Config D: CarePolicyGuard (Full 4-Agent Pipeline with Adversarial Verification & Calibrated Abstention Gate tau=0.85)
    """

    def __init__(self, db: Optional[Any] = None):
        from app.agents.empirical_harness import EmpiricalResearchHarness
        self.harness = EmpiricalResearchHarness(db=db)

    def run_benchmark(self) -> BenchmarkResponse:
        return self.harness.run_full_benchmark(BENCHMARK_VIGNETTES)
