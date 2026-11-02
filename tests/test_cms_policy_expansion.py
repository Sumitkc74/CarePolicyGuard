import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision

@pytest.fixture
def pipeline():
    return MultiAgentVerificationPipeline(db=None)

# =============================================================================
# NCD-240.2 (Home Use of Oxygen): Expanded Secondary Criteria Tests
# =============================================================================

def test_crit_o2_02_clinical_stability_meeting(pipeline):
    """Meeting case: Documented severe hypoxemia AND confirmed clinical stability -> APPROVED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "67-year-old male with severe chronic obstructive pulmonary disease.\n"
        "Patient is in a chronic, clinically stable state at this outpatient visit with no acute complaints.\n"
        "Resting room air pulse oximetry confirms SpO2 of 85% at rest.\n"
        "Plan: Long-term home oxygen therapy prescribed under CMS NCD 240.2."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-01", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    assert not res.abstention_status

def test_crit_o2_02_clinical_stability_failing(pipeline):
    """Failing case: Patient is explicitly not clinically stable, presenting with acute exacerbation -> DENIED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "67-year-old male with severe chronic obstructive pulmonary disease.\n"
        "Patient is not clinically stable, presenting with acute exacerbation of COPD with acute respiratory failure in the emergency department.\n"
        "Resting room air pulse oximetry SpO2 84% on room air.\n"
        "Order: Home oxygen delivery."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-02", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    assert not res.abstention_status

def test_crit_o2_02_clinical_stability_omission_defers(pipeline):
    """Omission case: Documented hypoxemia, but clinical stability is omitted from the chart -> DEFERRED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "67-year-old male with chronic respiratory symptoms.\n"
        "Resting room air pulse oximetry SpO2 85%.\n"
        "Plan: Home oxygen therapy requested."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-03", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status

def test_crit_o2_excl_01_reversible_etiology_meeting_exclusion(pipeline):
    """Meeting case (triggered exclusion): Hypoxemia caused by acute untreated pneumonia -> DENIED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "72-year-old female evaluated for hypoxemia.\n"
        "Patient is clinically stable.\n"
        "Chest radiograph reveals acute pneumonia with productive cough and fever.\n"
        "Resting room air SpO2 86%.\n"
        "Assessment: Hypoxemia secondary to acute pneumonia (reversible etiology).\n"
        "Plan: Request for home oxygen."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-04", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    assert not res.abstention_status

def test_crit_o2_excl_01_reversible_etiology_failing_exclusion(pipeline):
    """Failing case (exclusion not met / passes): Hypoxemia with explicitly no reversible cause -> APPROVED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "72-year-old female with idiopathic pulmonary fibrosis.\n"
        "Patient is clinically stable in clinic.\n"
        "Chest imaging and clinical exam show no acute pneumonia, no bronchospasm, and no acute pulmonary edema.\n"
        "Room air arterial blood gas confirms PaO2 51 mmHg and SpO2 85%.\n"
        "Plan: Home oxygen therapy prescribed."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-05", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    assert not res.abstention_status

def test_crit_o2_excl_01_reversible_etiology_omission_defers(pipeline):
    """Omission case: Ambiguous reversible etiology with missing quantified blood gas / oximetry -> DEFERRED."""
    note = (
        "PULMONOLOGY PROGRESS NOTE\n"
        "72-year-old female with shortness of breath.\n"
        "Clinically stable outpatient baseline.\n"
        "Reversible bronchospasm suspected but not fully resolved.\n"
        "Oxygen saturation not recorded on room air in this note.\n"
        "Plan: Home oxygen evaluation."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-O2-06", "NCD-240.2", note)
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status

# =============================================================================
# NCD-20.33 (TAVR): Expanded Futility and Prohibitive Risk Exclusions
# =============================================================================

def test_crit_tavr_excl_01_futility_meeting_exclusion(pipeline):
    """Meeting case (triggered exclusion): Severe AS with Heart Team, but metastatic malignancy in hospice -> DENIED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "82-year-old male with severe calcific aortic stenosis.\n"
        "Echocardiogram: Aortic valve area 0.72 cm2, mean transvalvular gradient 46 mmHg, peak velocity 4.2 m/s.\n"
        "Heart Team: Multidisciplinary Heart Team consultation completed with interventional cardiologist and cardiac surgeon.\n"
        "COMORBIDITIES: Patient has stage IV metastatic cancer, currently enrolled in hospice care with estimated life expectancy < 1 year.\n"
        "Plan: TAVR evaluation."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-01", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    assert not res.abstention_status

def test_crit_tavr_excl_01_futility_failing_exclusion(pipeline):
    """Failing case (exclusion not met / passes): Severe AS with Heart Team and absence of futility -> APPROVED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "82-year-old male with severe symptomatic calcific aortic stenosis.\n"
        "Echocardiogram: Aortic valve area 0.75 cm2, mean transvalvular gradient 44 mmHg, peak velocity 4.3 m/s.\n"
        "Heart Team: Multidisciplinary Heart Team consultation completed with interventional cardiologist and cardiac surgeon.\n"
        "Negative for active infective endocarditis. No terminal illness; expected longevity > 5 years.\n"
        "Plan: TAVR recommended under CMS NCD 20.33."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-02", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    assert not res.abstention_status

def test_crit_tavr_excl_01_futility_omission_defers(pipeline):
    """Omission case: Qualitative AS only without quantified AVA or mean gradient -> DEFERRED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "82-year-old male with severe aortic stenosis in qualitative description only.\n"
        "Heart Team: Multidisciplinary Heart Team consultation completed with interventional cardiologist and cardiac surgeon.\n"
        "No active endocarditis.\n"
        "Plan: TAVR pending quantified echocardiography."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-03", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status

def test_crit_tavr_excl_02_prohibitive_anatomy_meeting_exclusion(pipeline):
    """Meeting case (triggered exclusion): Severe AS with Heart Team, but prohibitive aortic root anatomy -> DENIED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "78-year-old female with severe symptomatic aortic stenosis.\n"
        "Echocardiogram: Aortic valve area 0.65 cm2, mean transvalvular gradient 50 mmHg, peak velocity 4.6 m/s.\n"
        "Heart Team: Multidisciplinary Heart Team consultation completed with cardiac surgeon and interventional cardiologist.\n"
        "CTA Imaging: Patient exhibits prohibitive aortic root anatomy and severe annular calcification precluding transcatheter deployment.\n"
        "Plan: TAVR consideration."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-04", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    assert not res.abstention_status

def test_crit_tavr_excl_02_prohibitive_anatomy_failing_exclusion(pipeline):
    """Failing case (exclusion not met / passes): Severe AS with suitable anatomy -> APPROVED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "78-year-old female with severe symptomatic aortic stenosis.\n"
        "Echocardiogram: Aortic valve area 0.69 cm2, mean transvalvular gradient 48 mmHg, peak velocity 4.4 m/s.\n"
        "Heart Team: Multidisciplinary Heart Team consultation completed with cardiac surgeon and interventional cardiologist.\n"
        "CTA confirms suitable transfemoral access and favorable annular dimensions; no prohibitive anatomy or active bacteremia.\n"
        "Plan: Proceed with TAVR under CMS NCD 20.33."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-05", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    assert not res.abstention_status

def test_crit_tavr_excl_02_prohibitive_anatomy_omission_defers(pipeline):
    """Omission case: Severe AS quantified, but Heart Team consultation omitted -> DEFERRED."""
    note = (
        "STRUCTURAL HEART CLINIC NOTE\n"
        "78-year-old female with severe symptomatic aortic stenosis.\n"
        "Echocardiogram: Aortic valve area 0.69 cm2, mean transvalvular gradient 48 mmHg, peak velocity 4.4 m/s.\n"
        "CTA confirms suitable transfemoral anatomy.\n"
        "Plan: TAVR referral; evaluation by cardiothoracic surgery not yet scheduled."
    )
    res = pipeline.adjudicate_sync("PT-SYNTH-TAVR-06", "NCD-20.33", note)
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status
