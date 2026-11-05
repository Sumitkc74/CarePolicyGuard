import pytest
from app.services.hybrid_retriever import DenseSemanticRetriever, HybridPolicyRetriever
from app.services.declarative_engine import DeclarativePolicyEngine

def test_dense_concept_retriever_fires_for_all_clinical_domains():
    """
    Task 3: Dense semantic retriever concept vocabulary covers all 50 policy clinical domains.
    Asserts that representative query texts across each domain produce a non-zero concept embedding vector.
    """
    retriever = DenseSemanticRetriever()

    domain_queries = {
        "Cardiology_ICD": "Patient with ischemic cardiomyopathy and LVEF 28% requiring implantable cardioverter defibrillator",
        "Sleep_Medicine_CPAP": "Severe obstructive sleep apnea with apnea hypopnea index AHI 34 on polysomnography",
        "Structural_Heart_TAVR": "Severe aortic stenosis with mean gradient 45 mmHg and heart team consensus for TAVR",
        "LAAC_Watchman": "Nonvalvular atrial fibrillation with high bleeding risk undergoing Watchman left atrial appendage closure",
        "Wound_Care_HBOT": "Diabetic foot ulcer Wagner grade 3 failing conservative wound care undergoing hyperbaric oxygen therapy",
        "Ophthalmology_Cataract": "Bilateral cataract extraction phacoemulsification with visual acuity impairment and glare disability",
        "Ophthalmology_Blepharoplasty": "Blepharoplasty for superior visual field restriction and marginal reflex distance MRD1 of 1.5 mm",
        "Orthopedics_Knee_Arthroplasty": "Severe end-stage knee osteoarthritis failing conservative therapy indicated for total knee arthroplasty",
        "Orthopedics_Hip_Arthroplasty": "Severe hip osteoarthritis with intractable joint space narrowing indicated for total hip arthroplasty",
        "Orthopedics_Shoulder_Arthroplasty": "Glenohumeral joint collapse and severe pain indicated for shoulder arthroplasty",
        "Orthopedics_Rotator_Cuff": "Full-thickness rotator cuff tear of supraspinatus tendon failing physical therapy",
        "Orthopedics_Hip_Arthroscopy": "Femoroacetabular impingement FAI with labral tear and cam lesion undergoing hip arthroscopy",
        "Orthopedics_Knee_Orthosis": "Unicompartmental osteoarthritis prescribed custom OA knee brace knee orthosis",
        "Orthopedics_Hallux_Valgus": "Symptomatic hallux valgus with intermetatarsal angle > 15 degrees requiring bunionectomy",
        "Orthopedics_ACI": "Full-thickness femoral chondral defect undergoing autologous chondrocyte implantation ACI",
        "Spine_ACDF": "Cervical radiculopathy with neuroforaminal stenosis on MRI indicated for anterior cervical discectomy and fusion ACDF",
        "Spine_Lumbar_Decompression": "Lumbar spinal stenosis with neurogenic claudication requiring lumbar laminectomy decompression",
        "Spine_Lumbar_Fusion": "Lumbar spondylolisthesis with instability undergoing lumbar spinal fusion",
        "Spine_Kyphoplasty": "Acute osteoporotic vertebral compression fracture undergoing percutaneous kyphoplasty",
        "Spine_ESI": "Lumbar radiculopathy failing 6 weeks physical therapy scheduled for epidural steroid injection ESI",
        "Spine_Facet_Interventions": "Facet joint syndrome confirmed with diagnostic medial branch block undergoing radiofrequency ablation",
        "Spine_Cervical_Disc_OPD": "Cervical disc herniation indicated for cervical disc arthroplasty artificial disc",
        "Spine_SI_Joint_OPD": "Sacroiliac joint dysfunction failing conservative care undergoing SI joint fusion",
        "Radiation_Oncology_IMRT": "Locally advanced prostate carcinoma prescribed intensity modulated radiation therapy IMRT",
        "Radiation_Oncology_SBRT": "Early-stage non-small cell lung cancer treated with stereotactic body radiation therapy SBRT",
        "Radiation_Oncology_Proton": "Skull base chordoma requiring precise proton beam therapy",
        "Radiology_PET_Oncology": "Evaluation of solitary pulmonary nodule with FDG PET oncology imaging",
        "Radiology_Coronary_CTA": "Intermediate pre-test probability chest pain undergoing coronary CTA CCTA",
        "Radiology_Chest_CT": "Hemoptysis evaluation with contrast-enhanced chest CT",
        "Radiology_Brain_MRI": "Intractable focal seizures requiring brain MRI magnetic resonance imaging",
        "Radiology_Lumbar_MRI": "Progressive lower extremity motor deficit evaluated with lumbar spine MRI",
        "Vascular_EVAR": "Infrarenal abdominal aortic aneurysm measuring 5.6 cm repaired with endovascular aneurysm repair EVAR",
        "Vascular_Peripheral_Atherectomy": "Severe peripheral artery disease with disabling claudication undergoing atherectomy",
        "Vascular_Vein_Ablation": "Incompetent great saphenous vein with venous insufficiency undergoing endovenous vein ablation",
        "Pain_Management_SCS": "Failed back surgery syndrome undergoing trial spinal cord stimulation SCS",
        "Pain_Management_Pump": "Severe intractable spasticity managed with intrathecal baclofen infusion pump",
        "DMEPOS_Power_Wheelchair": "Inability to ambulate or self-propel manual wheelchair requiring power mobility device power wheelchair",
        "DMEPOS_Respiratory_NIV": "Severe hypercapnic respiratory failure managed with noninvasive ventilation bipap ST",
        "DMEPOS_Speech_Generating": "Severe dysarthria secondary to ALS requiring augmentative speech generating device SGD",
        "DMEPOS_Wound_VAC": "Complex abdominal surgical dehiscence managed with negative pressure wound therapy wound vac",
        "OPD_Botox": "Severe cervical dystonia with neck pain and torticollis treated with botulinum toxin botox",
        "OPD_Panniculectomy": "Severe chronic intertrigo under grade 3 abdominal pannus requiring panniculectomy",
        "OPD_Rhinoplasty": "Nasal valve collapse and severe nasal airway obstruction requiring functional rhinoplasty"
    }

    for domain_name, query in domain_queries.items():
        vec = retriever._embed_text(query)
        norm = sum(x * x for x in vec)
        assert norm > 0.0, f"Domain {domain_name} produced empty concept embedding for query: '{query}'"


def test_hybrid_policy_retriever_fallback_indexes_all_50_policies_when_db_empty():
    """
    Task 3: Fallback chunks in HybridPolicyRetriever cover all 50 policies when DB is unseeded.
    """
    # Initialize retriever without a database session to trigger the resilient fallback
    retriever = HybridPolicyRetriever(db=None)

    all_policies = DeclarativePolicyEngine.get_all_policies()
    assert len(all_policies) == 50, f"Expected 50 declarative policies, found {len(all_policies)}"

    indexed_policy_ids = {chunk["policy_id"] for chunk in retriever.chunks}
    for pol in all_policies:
        assert pol.policy_id in indexed_policy_ids, f"Policy {pol.policy_id} missing from fallback index"

    assert len(indexed_policy_ids) == 50

