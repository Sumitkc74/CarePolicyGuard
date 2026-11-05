#!/usr/bin/env python3
"""
Generates realistic, uncued synthetic clinical progress notes for the 42 extended policies.
Contains zero policy slugs, zero LCD/NCD identifiers, and zero coverage verdict phrases.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"

VIGNETTES = []

def add_vignette(pid, vtype, title, exp_dec, narrative):
    vid = f"DEV-{pid}-{'APP' if exp_dec == 'APPROVED' else 'NEG'}"
    VIGNETTES.append({
        "vignette_id": vid,
        "policy_id": pid,
        "vignette_type": vtype,
        "title": title,
        "expected_decision": exp_dec,
        "ehr_narrative": narrative.strip()
    })

# =========================================================================
# 1. LCD-ACDF: Anterior Cervical Discectomy and Fusion
# Criteria: 
# c1: cervical disc herniation / radiculopathy on MRI
# c2: conservative trial >= 6 weeks (42 days)
# excl: neck pain only without radiculopathy
# =========================================================================
add_vignette(
    "LCD-ACDF", "APPROVED", "Cervical radiculopathy with MRI-proven disc herniation", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Spine Surgery Clinic
SUBJECTIVE: 52-year-old presenting with sharp shooting pain into right shoulder and arm in C6 dermatome. Pain began 4 months ago. Patient has participated in structured cervical physical therapy and oral NSAID treatment for 8 weeks without relief. Denies neck pain only.
OBJECTIVE: Right biceps reflex 1+, sensory deficit in C6 distribution. Cervical spine MRI demonstrates C5-C6 right paracentral cervical disc herniation with severe neuroforaminal stenosis and nerve root impingement.
ASSESSMENT & PLAN: Intractable right C6 cervical radiculopathy refractory to 8 weeks conservative care with correlating MRI disc protrusion. Plan: Anterior cervical discectomy with interbody fusion at C5-C6."""
)
add_vignette(
    "LCD-ACDF", "NEGATIVE_FRAMED", "Axial neck pain without radiculopathy or disc herniation", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Spine Surgery Clinic
SUBJECTIVE: 44-year-old presenting with generalized dull ache across posterior neck. Patient reports neck pain only for 10 days. No radiation into upper extremities. Conservative management tried for only 1 week.
OBJECTIVE: Full motor strength 5/5 bilaterally, reflexes 2+. Cervical MRI shows mild muscular strain without cervical disc herniation or cord compression.
ASSESSMENT & PLAN: Acute uncomplicated axial neck pain without radiculopathy. Surgical intervention is not clinically indicated."""
)

# =========================================================================
# 2. LCD-ACI: Autologous Chondrocyte Implantation (ACI / MACI)
# Criteria:
# c1: cartilage defect area >= 1.5 cm2 (1.5 to 10 cm2)
# c2: prior microfracture / debridement failure
# excl: diffuse osteoarthritis / tricompartmental OA
# =========================================================================
add_vignette(
    "LCD-ACI", "APPROVED", "Focal femoral condyle chondral defect post-microfracture failure", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Sports Medicine
SUBJECTIVE: 31-year-old active runner with persistent medial right knee pain. Underwent knee arthroscopy with microfracture 14 months ago with recurrent focal weight-bearing pain. No generalized diffuse osteoarthritis.
OBJECTIVE: Diagnostic knee arthroscopy and cartilage sizing reveals isolated focal cartilage defect area of 3.2 cm2 on medial femoral condyle. Kellgren-Lawrence grade 0 in lateral and patellofemoral compartments. Prior microfracture failure confirmed.
ASSESSMENT & PLAN: Isolated Outerbridge grade IV chondral defect medial femoral condyle following failed marrow stimulation. Plan: Autologous chondrocyte implantation staged cartilage repair."""
)
add_vignette(
    "LCD-ACI", "NEGATIVE_FRAMED", "Severe tricompartmental osteoarthritis with sub-threshold lesion", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Sports Medicine
SUBJECTIVE: 68-year-old presenting with chronic diffuse bilateral knee stiffness and deep aching pain.
OBJECTIVE: Standing knee series demonstrates severe diffuse osteoarthritis with tricompartmental joint space collapse (Kellgren-Lawrence grade 4). Cartilage defect area measured at 0.6 cm2. No previous microfracture was attempted.
ASSESSMENT & PLAN: Advanced end-stage tricompartmental knee arthrosis. Focal chondrocyte implantation is contraindicated in setting of generalized degenerative joint disease."""
)

# =========================================================================
# 3. LCD-CT-CHEST: Computed Tomography of Chest with Contrast
# Criteria:
# c1: solitary pulmonary nodule > 6mm / abnormal chest radiograph
# c2: unexplained hemoptysis / ILD evaluation
# excl: acute viral bronchitis / uncomplicated URI
# =========================================================================
add_vignette(
    "LCD-CT-CHEST", "APPROVED", "Solitary pulmonary nodule on chest radiograph with hemoptysis", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Pulmonary Medicine Clinic
SUBJECTIVE: 61-year-old former smoker presenting with two weeks of unexplained hemoptysis and chronic cough. No simple acute viral bronchitis.
OBJECTIVE: Chest radiograph reveals a distinct non-calcified solitary pulmonary nodule > 6mm measuring 12 mm in the right upper lobe. Resting oxygen saturation 96% on room air.
ASSESSMENT & PLAN: Radiographically documented solitary pulmonary nodule accompanied by hemoptysis. Plan: Computed tomography of the thorax with intravenous contrast for pulmonary characterization."""
)
add_vignette(
    "LCD-CT-CHEST", "NEGATIVE_FRAMED", "Uncomplicated acute bronchitis without abnormal radiograph", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Pulmonary Medicine Clinic
SUBJECTIVE: 22-year-old presenting with 3 days of productive cough and low-grade fever following household cold.
OBJECTIVE: Normal pulmonary examination without focal crackles. Clear lungs. Absence of chest x-ray abnormality; clinical picture consistent with uncomplicated acute viral bronchitis. No hemoptysis.
ASSESSMENT & PLAN: Acute viral tracheobronchitis. Thoracic computed tomography imaging is not clinically indicated for acute uncomplicated URI."""
)

# =========================================================================
# 4. LCD-ESI: Lumbar Epidural Steroid Injections
# Criteria:
# c1: radicular pain / positive straight leg raise
# c2: conservative treatment >= 28 days (4 weeks)
# excl: non-radicular pain / axial back pain only
# =========================================================================
add_vignette(
    "LCD-ESI", "APPROVED", "L5 radicular nerve root pain refractory to physical therapy", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Spine Clinic
SUBJECTIVE: 56-year-old presenting with severe shooting lumbar radicular pain radiating down left posterior thigh into the lateral calf and great toe. Pain present for 10 weeks. Patient completed structured physical therapy trial and oral gabapentin for 6 weeks without significant benefit.
OBJECTIVE: Positive straight leg raise test on the left at 40 degrees. Lumbar MRI confirms L4-L5 disc protrusion compressing traversing L5 root. Denies non-radicular pain only.
ASSESSMENT & PLAN: Intractable subacute L5 radiculopathy following failed 6-week conservative rehabilitation. Plan: Fluoroscopically guided left lumbar transforaminal epidural steroid injection."""
)
add_vignette(
    "LCD-ESI", "NEGATIVE_FRAMED", "Axial low back pain without radicular symptoms or physical therapy", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Spine Clinic
SUBJECTIVE: 48-year-old presenting with non-radicular pain and muscular tightness localized to lower lumbar midline after moving heavy boxes 5 days ago. No leg radiation. No prior physical therapy.
OBJECTIVE: Negative straight leg raise bilaterally. Normal lower extremity sensation and reflexes. Tenderness over lumbar erector spinae muscles.
ASSESSMENT & PLAN: Acute non-radicular mechanical muscular back strain. Epidural spinal injection is contraindicated for localized axial back pain without radiculopathy."""
)

# =========================================================================
# 5. LCD-EVAR: Endovascular Abdominal Aortic Aneurysm Repair
# Criteria:
# c1: aaa diameter >= 5.0 cm (>= 5.5 men / >= 5.0 women)
# c2: suitable proximal neck landing zone >= 10 mm
# excl: small stable aneurysm (< 5.0 cm)
# =========================================================================
add_vignette(
    "LCD-EVAR", "APPROVED", "Infrarenal AAA diameter 5.8 cm with adequate proximal aortic neck", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Clinic
SUBJECTIVE: 73-year-old male evaluated for enlarging infrarenal abdominal aortic aneurysm identified on surveillance duplex. Patient is asymptomatic.
OBJECTIVE: CTA of the abdominal aorta reveals fusiform infrarenal aneurysm with maximum aaa diameter of 5.8 cm. Proximal infrarenal aortic neck length is 16 mm with minimal angulation (suitable proximal neck landing zone). Iliac access vessels are patent.
ASSESSMENT & PLAN: Expanding infrarenal aortic aneurysm exceeding 5.5 cm threshold with suitable anatomy for endograft fixation. Plan: Elective endovascular abdominal aortic aneurysm repair."""
)
add_vignette(
    "LCD-EVAR", "NEGATIVE_FRAMED", "Small stable infrarenal aneurysm measuring 3.8 cm", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Clinic
SUBJECTIVE: 69-year-old male with history of hypertension presents for follow-up ultrasound evaluation.
OBJECTIVE: Computed tomography angiography demonstrates small stable aneurysm measuring maximum diameter 3.8 cm, unchanged from imaging 12 months ago. Aortic neck anatomy unremarkable.
ASSESSMENT & PLAN: Small infrarenal aneurysm well below interventional threshold. Endovascular stent-graft placement is not clinically indicated; continue ultrasound surveillance in 12 months."""
)

# =========================================================================
# 6. LCD-FACET: Facet Joint Interventions
# Criteria:
# c1: diagnostic mbb relief >= 80%
# c2: chronic axial back pain >= 90 days (3 months)
# excl: primary radiculopathy / acute fracture
# =========================================================================
add_vignette(
    "LCD-FACET", "APPROVED", "Chronic lumbar facet arthropathy with 85% relief on dual MBB", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Pain Management
SUBJECTIVE: 64-year-old presenting with aching axial back pain over the lumbosacral junction for 9 months, exacerbated by lumbar extension. Denies lower extremity radicular numbness. No acute fracture.
OBJECTIVE: Tenderness over bilateral L4-L5 and L5-S1 facet columns. Patient underwent two diagnostic medial branch blocks under fluoroscopy, achieving documented medial branch block relief of 85% for the expected anesthetic duration.
ASSESSMENT & PLAN: Dual-block verified lumbar zygapophysial arthropathy with greater than 80% relief. Plan: Fluoroscopically guided lumbar medial branch radiofrequency neurotomy."""
)
add_vignette(
    "LCD-FACET", "NEGATIVE_FRAMED", "Acute radicular sciatica with negative diagnostic facet block", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Pain Management
SUBJECTIVE: 40-year-old presenting with sharp electric shock pain radiating into right foot after acute disc herniation 2 weeks ago (primary radiculopathy).
OBJECTIVE: Straight leg raise positive on right at 30 degrees. Diagnostic medial branch block produced only 15% pain reduction.
ASSESSMENT & PLAN: Acute radiculopathy secondary to disc pathology. Facet neurotomy is contraindicated given primary radiculopathy and lack of diagnostic facet block response."""
)

# =========================================================================
# 7. LCD-HALLUX: Hallux Valgus Correction (Bunionectomy)
# Criteria:
# c1: hallux valgus angle > 15 degrees
# c2: conservative footwear / orthotics trial >= 90 days (3 months)
# excl: cosmetic bunionectomy / asymptomatic bunion
# =========================================================================
add_vignette(
    "LCD-HALLUX", "APPROVED", "Painful hallux valgus deformity failing 16 weeks orthotics", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Podiatric Surgery Clinic
SUBJECTIVE: 54-year-old woman presenting with severe pain and burning over the medial eminence of the first metatarsophalangeal joint during ambulation. Symptoms present for 2 years. Patient has worn wide toe box footwear and custom functional orthotics consistently for 16 weeks without pain reduction. Denies requesting cosmetic bunionectomy.
OBJECTIVE: Weight-bearing AP foot radiography demonstrates a hallux valgus angle of 26 degrees and intermetatarsal angle of 14 degrees. Erythema over medial bunion prominence.
ASSESSMENT & PLAN: Symptomatic moderate hallux valgus deformity with significant functional impairment refractory to 4 months of conservative orthotics. Plan: First metatarsal osteotomy bunionectomy."""
)
add_vignette(
    "LCD-HALLUX", "NEGATIVE_FRAMED", "Painless cosmetic complaint with minimal 10 degree deviation", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Podiatric Surgery Clinic
SUBJECTIVE: 27-year-old presenting because she dislikes the aesthetic appearance of her left big toe in narrow dress shoes. She reports zero pain with ambulation and no difficulty walking. No conservative shoe modifications attempted.
OBJECTIVE: Weight-bearing radiographs show a normal hallux valgus angle of 10 degrees. No medial bunion bursitis.
ASSESSMENT & PLAN: Asymptomatic mild toe contour; request is for purely cosmetic bunionectomy. Corrective osteotomy surgery is not clinically indicated."""
)

# =========================================================================
# 8. LCD-HIP-ARTHRO: Total Hip Arthroplasty (THA)
# Criteria:
# c1: severe joint space narrowing / advanced radiographic OA
# c2: conservative trial >= 90 days (3 months)
# excl: active systemic infection
# =========================================================================
add_vignette(
    "LCD-HIP-ARTHRO", "APPROVED", "End-stage osteoarthritis of right hip refractory to non-operative care", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Adult Reconstruction Orthopedics
SUBJECTIVE: 67-year-old male with severe groin and anterior thigh pain with weight-bearing for 14 months. Has completed 16 weeks of structured physical therapy, activity modification, and received an intra-articular steroid injection 4 months ago with waning relief. Denies active infection.
OBJECTIVE: Antalgic gait favoring right side. Internal rotation restricted to 5 degrees with groin pain. Weight-bearing pelvic radiographs show severe joint space narrowing, subchondral sclerosis, and large femoral osteophytes (Kellgren-Lawrence grade 4).
ASSESSMENT & PLAN: End-stage primary osteoarthritis of right hip with intractable functional limitation after 4 months conservative therapy. Plan: Elective right total hip arthroplasty."""
)
add_vignette(
    "LCD-HIP-ARTHRO", "NEGATIVE_FRAMED", "Mild hip strain with active superficial wound infection", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Adult Reconstruction Orthopedics
SUBJECTIVE: 50-year-old presenting with 2 weeks of lateral hip discomfort after yard work. Concurrently receiving intravenous antibiotics for active cellulitis of the ipsilateral groin.
OBJECTIVE: AP pelvis and frog-leg views demonstrate preserved joint space with minimal sclerosis. Significant purulent erythema over right thigh indicating active infection.
ASSESSMENT & PLAN: Mild trochanteric bursitis complicated by active soft tissue infection. Joint replacement arthroplasty is strictly contraindicated in the presence of active infection."""
)

# =========================================================================
# 9. LCD-HIP-SCOOP: Hip Arthroscopy for FAI and Labral Tears
# Criteria:
# c1: labral tear on mri / cam or pincer lesion
# c2: conservative trial >= 90 days (3 months)
# excl: advanced osteoarthritis / tonnis grade 2 or 3
# =========================================================================
add_vignette(
    "LCD-HIP-SCOOP", "APPROVED", "Femoroacetabular impingement with acetabular labral tear on MRI", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Sports Medicine
SUBJECTIVE: 28-year-old soccer player with deep anterior groin catching and sharp pain with hip flexion for 6 months. Completed 14 weeks of focused physical therapy and diagnostic intra-articular lidocaine injection. No advanced osteoarthritis.
OBJECTIVE: Positive anterior impingement sign (FADIR test). Hip MR arthrogram demonstrates anterosuperior labral tear on mri with cam deformity (alpha angle 68 degrees). Preserved cartilage space (Tonnis grade 0).
ASSESSMENT & PLAN: Symptomatic cam-type femoroacetabular impingement and labral tear refractory to 14 weeks non-operative management. Plan: Right hip arthroscopy with labral repair and femoroplasty."""
)
add_vignette(
    "LCD-HIP-SCOOP", "NEGATIVE_FRAMED", "Advanced degenerative hip arthritis with joint space obliteration", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Sports Medicine
SUBJECTIVE: 71-year-old presenting with deep groin stiffness and severe limitation in walking for 2 years.
OBJECTIVE: Radiographs reveal advanced osteoarthritis with Tonnis grade 3 joint space obliteration, diffuse bone-on-bone contact, and femoral head flattening.
ASSESSMENT & PLAN: Severe degenerative joint disease of the hip. Arthroscopic joint debridement is ineffective and contraindicated in advanced osteoarthritis."""
)

# =========================================================================
# 10. LCD-IMRT: Intensity Modulated Radiation Therapy
# Criteria:
# c1: prostate / head and neck / cns malignancy adjacent to OAR
# c2: imrt vs 3d-crt plan comparison showing OAR sparing
# excl: palliative treatment of bone metastasis
# =========================================================================
add_vignette(
    "LCD-IMRT", "APPROVED", "Localized prostate adenocarcinoma adjacent to critical rectal wall", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 66-year-old male with intermediate-risk prostate adenocarcinoma (Gleason 3+4=7, PSA 7.8). Initiating definitive radiation planning. No distant metastatic disease.
OBJECTIVE: Dosimetric planning comparison completed: 3D-CRT plan exceeds rectal wall tolerance (rectal V70 > 25%). The inverse imrt plan achieves concave dose escalation to 78 Gy while reducing rectal V70 to 14% and bladder wall dose below mandatory constraints.
ASSESSMENT & PLAN: Clinically localized prostate malignancy requiring steep dose gradient adjacent to critical organs at risk. Plan: Inverse intensity-modulated radiation therapy with daily image guidance."""
)
add_vignette(
    "LCD-IMRT", "NEGATIVE_FRAMED", "Palliative treatment of painful diffuse bone metastasis", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 78-year-old with metastatic lung cancer presenting with focal thoracic vertebral body metastasis causing localized aching pain.
OBJECTIVE: Solitary mid-thoracic spinous process lesion without spinal cord compromise. Goal of therapy is simple pain palliation.
ASSESSMENT & PLAN: Widespread metastatic disease requiring short-course pain relief. Complex inverse intensity-modulated delivery is not indicated; simple palliative treatment of bone metastasis with standard 3D field is appropriate."""
)

# =========================================================================
# 11. LCD-KNEE-ARTHRO: Knee Arthroscopy and Meniscectomy
# Criteria:
# c1: unstable meniscal tear on mri with mechanical locking
# c2: conservative therapy trial >= 42 days (6 weeks)
# excl: advanced osteoarthritis / kellgren-lawrence grade 4
# =========================================================================
add_vignette(
    "LCD-KNEE-ARTHRO", "APPROVED", "Mechanical bucket-handle meniscal tear with persistent knee locking", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Surgery
SUBJECTIVE: 39-year-old with sudden onset of acute knee catching and true joint locking episodes after twisting injury 8 weeks ago. Patient has participated in 7 weeks of supervised physical therapy and rest without resolution of mechanical symptoms.
OBJECTIVE: Joint line tenderness over medial meniscus, positive McMurray test with audible click, inability to fully extend terminal 10 degrees. Knee MRI confirms unstable meniscal tear on mri (displaced medial bucket-handle fragment). Normal cartilage contours.
ASSESSMENT & PLAN: Mechanically unstable medial meniscal tear with persistent locking refractory to 7 weeks conservative therapy. Plan: Right knee arthroscopy with partial meniscectomy."""
)
add_vignette(
    "LCD-KNEE-ARTHRO", "NEGATIVE_FRAMED", "Bone-on-bone knee osteoarthritis without discrete mechanical tear", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Surgery
SUBJECTIVE: 74-year-old with chronic bilateral knee aching and stiffness for 5 years. No mechanical locking or acute injury.
OBJECTIVE: Weight-bearing knee films demonstrate diffuse bone-on-bone medial and patellofemoral joint space obliteration consistent with advanced osteoarthritis (kellgren-lawrence grade 4).
ASSESSMENT & PLAN: End-stage degenerative knee arthrosis. Arthroscopic meniscectomy or joint lavage is ineffective and contraindicated for primary advanced osteoarthritic debridement."""
)

# =========================================================================
# 12. LCD-KNEE-ORTHOSIS: Custom-Fabricated Functional Knee Orthoses
# Criteria:
# c1: knee joint laxity / ligamentous instability on exam
# c2: failed prefabricated brace
# excl: temporary postoperative bracing
# =========================================================================
add_vignette(
    "LCD-KNEE-ORTHOSIS", "APPROVED", "Severe chronic ACL/PCL laxity failing prefabricated bracing", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Physical Medicine and Rehabilitation
SUBJECTIVE: 42-year-old with recurrent knee instability and giving-way episodes secondary to combined cruciate ligament insufficiency. Patient tried an off-the-shelf prefabricated brace for 4 months, which repeatedly migrated and failed to control rotational subluxation.
OBJECTIVE: Physical exam reveals 3+ anterior drawer, grade III Lachman, and pivot shift demonstrating severe knee joint laxity. Atypical lower extremity anthropometry (conical thigh geometry).
ASSESSMENT & PLAN: Severe chronic ligamentous instability of the knee failing standard prefabricated supports. Plan: Custom-fabricated functional knee orthosis with rigid dynamic frame."""
)
add_vignette(
    "LCD-KNEE-ORTHOSIS", "NEGATIVE_FRAMED", "Temporary postoperative rehabilitation following routine arthroscopy", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Surgery
SUBJECTIVE: 29-year-old 3 days status post uncomplicated diagnostic knee arthroscopy. Minimal pain, full weight bearing.
OBJECTIVE: Stable knee examination with negative Lachman and firm end-point. Zero ligamentous laxity.
ASSESSMENT & PLAN: Normal postoperative status. Rigid custom-molded knee bracing is not indicated for simple temporary postoperative bracing; standard elastic sleeve is sufficient."""
)

# =========================================================================
# 13. LCD-KYPHO: Percutaneous Vertebral Augmentation
# Criteria:
# c1: acute osteoporotic vcf <= 6 weeks on mri / bone edema
# c2: severe pain vas >= 7 / failed conservative analgesic trial
# excl: infectious spondylodiscitis / osteomyelitis
# =========================================================================
add_vignette(
    "LCD-KYPHO", "APPROVED", "Acute painful osteoporotic vertebral compression fracture with bone edema", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Neuroradiology
SUBJECTIVE: 79-year-old female presenting with sudden severe midline mid-back pain after lifting groceries 18 days ago. Pain rating is 8/10 on visual analog scale. Patient has tried scheduled oral analgesics, bed rest, and calcitonin for 2 weeks with persistent inability to ambulate. Denies fever.
OBJECTIVE: Severe focal spinous process percussion tenderness at T12. Thoracic spine MRI shows 35% height loss of T12 with intense hyperintensity on STIR imaging demonstrating acute osteoporotic vcf with bone edema. Intact posterior vertebral wall. No signs of spinal infection.
ASSESSMENT & PLAN: Painful acute osteoporotic vertebral compression fracture of T12 with marrow edema failing conservative analgesic therapy. Plan: Percutaneous vertebral augmentation kyphoplasty."""
)
add_vignette(
    "LCD-KYPHO", "NEGATIVE_FRAMED", "Vertebral collapse in the setting of active infectious osteomyelitis", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Neuroradiology
SUBJECTIVE: 68-year-old diabetic presenting with unremitting back pain and recurrent spiking fevers.
OBJECTIVE: Elevated ESR and CRP. Contrast MRI reveals T8-T9 vertebral endplate destruction with disc space fluid collection and epidural phlegmon consistent with infectious spondylodiscitis and osteomyelitis.
ASSESSMENT & PLAN: Pyogenic vertebral osteomyelitis with secondary compression. Percutaneous cement augmentation is strictly contraindicated in the presence of active spinal infection."""
)

# =========================================================================
# 14. LCD-LUMBAR-DECOMP: Lumbar Laminectomy and Decompression
# Criteria:
# c1: lumbar neurogenic claudication / severe spinal stenosis on mri
# c2: conservative trial >= 42 days (6 weeks)
# excl: axial back pain without stenosis
# =========================================================================
add_vignette(
    "LCD-LUMBAR-DECOMP", "APPROVED", "Severe lumbar canal stenosis with neurogenic claudication", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Neurosurgery Clinic
SUBJECTIVE: 69-year-old presenting with bilateral lower extremity cramping, heaviness, and numbness upon walking more than 50 meters, relieved by forward flexion (lumbar neurogenic claudication). Symptoms present for 9 months. Patient has completed 10 weeks of physical therapy, epidural injections, and oral pharmacotherapy without sustained relief.
OBJECTIVE: Diminished ankle jerks bilaterally. Lumbar spine MRI demonstrates severe lumbar spinal stenosis at L4-L5 with thecal sac cross-sectional area < 60 mm2 secondary to facet hypertrophy and ligamentum flavum buckling.
ASSESSMENT & PLAN: Progressive lumbar neurogenic claudication refractory to 10 weeks conservative management with correlating critical central stenosis. Plan: Lumbar laminectomy and decompression at L4-L5."""
)
add_vignette(
    "LCD-LUMBAR-DECOMP", "NEGATIVE_FRAMED", "Postural low back pain with widely patent spinal canal", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Neurosurgery Clinic
SUBJECTIVE: 38-year-old presenting with aching axial lower back pain after sitting for long periods. Walks 3 miles daily without leg discomfort.
OBJECTIVE: Intact motor strength and reflexes. Lumbar MRI confirms a widely patent central canal with no spinal canal stenosis or neural impingement.
ASSESSMENT & PLAN: Myofascial axial back pain only without neurogenic claudication. Lumbar decompressive laminectomy is not clinically indicated."""
)

# =========================================================================
# 15. LCD-LUMBAR-FUSION: Lumbar Spinal Fusion
# Criteria:
# c1: lumbar spondylolisthesis / dynamic instability >= 3mm on flexion-extension
# c2: conservative trial >= 90 days (3 months)
# excl: uncomplicated disc herniation without instability
# =========================================================================
add_vignette(
    "LCD-LUMBAR-FUSION", "APPROVED", "Grade II degenerative spondylolisthesis with dynamic instability", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Spine Surgery
SUBJECTIVE: 62-year-old presenting with chronic mechanical low back and radicular leg pain for 1 year. Patient has completed 16 weeks of structured physical therapy, core stabilization, and multiple epidural injections with progressive deterioration in standing tolerance.
OBJECTIVE: Standing lumbar flexion-extension radiographs demonstrate dynamic instability with 5 mm translation at L4-L5 (lumbar spondylolisthesis). MRI confirms correlating severe central and lateral recess stenosis at the level of translation.
ASSESSMENT & PLAN: Symptomatic degenerative spondylolisthesis with verified dynamic instability refractory to 4 months of non-operative care. Plan: Lumbar spinal fusion with instrumentation and decompression at L4-L5."""
)
add_vignette(
    "LCD-LUMBAR-FUSION", "NEGATIVE_FRAMED", "Isolated disc herniation without mechanical instability", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Spine Surgery
SUBJECTIVE: 35-year-old presenting with acute right sciatica for 3 weeks following heavy lifting.
OBJECTIVE: Flexion-extension dynamic views demonstrate zero translation and normal alignment. MRI shows acute paracentral soft disc protrusion without spondylolisthesis or structural instability.
ASSESSMENT & PLAN: Acute disc herniation without segmental instability. Segmental spinal arthrodesis fusion is contraindicated for uncomplicated disc protrusion lacking instability."""
)

# =========================================================================
# 16. LCD-MRI-BRAIN: Magnetic Resonance Imaging of Brain
# Criteria:
# c1: acute focal neurological deficit / suspected stroke / tia
# c2: progressive severe headache / red flag signs
# excl: uncomplicated tension headache
# =========================================================================
add_vignette(
    "LCD-MRI-BRAIN", "APPROVED", "Subacute progressive right facial droop and unilateral weakness", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Neurology Outpatient Clinic
SUBJECTIVE: 58-year-old presenting with four days of progressive right upper extremity clumsiness, mild expressive word-finding difficulty, and new asymmetric right facial numbness.
OBJECTIVE: Cranial nerve exam reveals right central facial droop. Pronator drift present in right arm. Motor strength 4+/5 in right hand intrinsics. No history of uncomplicated tension headache.
ASSESSMENT & PLAN: Subacute focal neurological deficit concerning for intracranial mass lesion or subacute cerebrovascular ischemia. Plan: Magnetic resonance imaging of the brain with and without gadolinium contrast."""
)
add_vignette(
    "LCD-MRI-BRAIN", "NEGATIVE_FRAMED", "Chronic recurrent tension headache with normal neurological exam", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Neurology Outpatient Clinic
SUBJECTIVE: 26-year-old presenting with intermittent band-like forehead tightness related to computer work. Headaches have occurred for 3 years without visual changes, vomiting, or focal weakness.
OBJECTIVE: Cranial nerves II-XII completely intact. Normal fundoscopic examination without papilledema. Sensation, coordination, and gait completely normal.
ASSESSMENT & PLAN: Classic uncomplicated tension headache with entirely normal neurological examination. Diagnostic brain MRI neuroimaging is not indicated in the absence of red flags."""
)

# =========================================================================
# 17. LCD-MRI-LUMBAR: Magnetic Resonance Imaging of Lumbar Spine
# Criteria:
# c1: lumbar radiculopathy with objective neurological deficit
# c2: conservative therapy trial >= 28 days (4 weeks)
# excl: uncomplicated acute low back strain (< 4 weeks)
# =========================================================================
add_vignette(
    "LCD-MRI-LUMBAR", "APPROVED", "Progressive foot drop and severe S1 radiculopathy after 6 weeks therapy", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Physical Medicine and Rehabilitation
SUBJECTIVE: 49-year-old presenting with persistent shooting pain down left posterolateral leg into the heel and plantar aspect of the foot. Symptoms began 7 weeks ago. Patient has performed 6 weeks of dedicated physical therapy without relief.
OBJECTIVE: Absent left Achilles deep tendon reflex. Left gastrocnemius motor strength 4/5. Positive straight leg raise test on the left at 35 degrees. Clinical findings demonstrate objective lumbar radiculopathy.
ASSESSMENT & PLAN: Persistent lumbosacral nerve root compression with objective motor deficit following failed 6-week conservative trial. Plan: Magnetic resonance imaging of the lumbar spine without contrast."""
)
add_vignette(
    "LCD-MRI-LUMBAR", "NEGATIVE_FRAMED", "Acute muscular lumbar strain of 4 days duration", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Physical Medicine and Rehabilitation
SUBJECTIVE: 34-year-old presenting with localized lower back stiffness that started 4 days ago while gardening. No pain radiating into the buttocks or legs.
OBJECTIVE: Normal motor strength 5/5 across all lower extremity muscle groups. Normal sensation and symmetric reflexes. Negative straight leg raise bilaterally.
ASSESSMENT & PLAN: Acute uncomplicated low back strain of less than one week duration. Advanced lumbar MRI imaging is not indicated during the initial acute conservative phase."""
)

# =========================================================================
# 18. LCD-PAD-ATHERO: Peripheral Atherectomy and Angioplasty
# Criteria:
# c1: lifestyle-limiting claudication / rutherford class 3 to 6
# c2: documented hemodynamically significant stenosis (abi <= 0.70 / >= 70% stenosis)
# excl: asymptomatic mild pad
# =========================================================================
add_vignette(
    "LCD-PAD-ATHERO", "APPROVED", "Severe lifestyle-limiting calf claudication with SFA occlusion", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Clinic
SUBJECTIVE: 68-year-old diabetic smoker with severe lifestyle-limiting claudication occurring after walking less than 50 paces on level ground (Rutherford class 3). Supervised exercise therapy and cilostazol for 4 months failed to improve functional walking distance.
OBJECTIVE: Right lower extremity pulses absent at popliteal and pedal levels. Resting right ankle-brachial index is 0.48. Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery.
ASSESSMENT & PLAN: Advanced symptomatic peripheral artery disease failing medical and exercise therapy with severe arterial stenosis. Plan: Right superficial femoral artery atherectomy and balloon angioplasty."""
)
add_vignette(
    "LCD-PAD-ATHERO", "NEGATIVE_FRAMED", "Asymptomatic mild peripheral arterial disease with ABI 0.88", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Clinic
SUBJECTIVE: 71-year-old presenting for routine annual cardiovascular evaluation. Patient walks 2 miles daily with zero calf cramping or exertional leg pain.
OBJECTIVE: Pedal pulses palpable bilaterally. Resting ankle-brachial index is 0.88 bilaterally, indicating mild subclinical disease.
ASSESSMENT & PLAN: Asymptomatic mild peripheral artery disease. Invasive percutaneous peripheral atherectomy or revascularization is contraindicated for asymptomatic patients."""
)

# =========================================================================
# 19. LCD-PCI: Percutaneous Coronary Intervention with Stents
# Criteria:
# c1: severe coronary artery stenosis >= 70% on angiography
# c2: objective myocardial ischemia on stress testing / refractory angina
# excl: non-hemodynamic mild stenosis (< 50%)
# =========================================================================
add_vignette(
    "LCD-PCI", "APPROVED", "Refractory Canadian Class III angina with 85% proximal LAD stenosis", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Cardiology
SUBJECTIVE: 63-year-old presenting with recurrent exertional substernal chest pressure (CCS Class III angina) triggered by minimal exertion, refractory to dual anti-anginal medications including metoprolol and isosorbide mononitrate.
OBJECTIVE: Nuclear SPECT perfusion scan shows reversible anterior wall ischemia. Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow.
ASSESSMENT & PLAN: Medically refractory symptomatic ischemic heart disease with high-grade proximal LAD stenosis. Plan: Percutaneous coronary intervention with placement of drug-eluting stent."""
)
add_vignette(
    "LCD-PCI", "NEGATIVE_FRAMED", "Non-hemodynamic mild 30% coronary plaque with negative stress test", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Cardiology
SUBJECTIVE: 54-year-old evaluated following atypical non-exertional chest twinges.
OBJECTIVE: Exercise treadmill stress test was completely negative for ischemic ST-segment shifts or symptoms at 11 METs. Angiography reveals smooth 30% non-hemodynamic mild stenosis in the mid circumflex artery.
ASSESSMENT & PLAN: Non-obstructive coronary artery disease without demonstrable myocardial ischemia. Stenting is not clinically indicated for non-flow-limiting sub-threshold plaque."""
)

# =========================================================================
# 20. LCD-POWER-WC: Complex Rehabilitative Power Wheelchairs (Group 3)
# Criteria:
# c1: severe neurological mobility limitation (als / sci / ms)
# c2: formal specialty evaluation by licensed PT/OT and ATP
# excl: ability to ambulate or self-propel manual wheelchair
# =========================================================================
add_vignette(
    "LCD-POWER-WC", "APPROVED", "Non-ambulatory ALS with quadriplegia requiring power positioning", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Assistive Technology Clinic
SUBJECTIVE: 57-year-old diagnosed with amyotrophic lateral sclerosis experiencing progressive quadriparesis. Patient is completely non-ambulatory and unable to perform MRADLs in the home. Unable to safely operate a manual wheelchair or power scooter due to severe bilateral upper extremity weakness.
OBJECTIVE: Comprehensive seated mobility evaluation completed by licensed physical therapist and certified ATP. Upper extremity strength 1/5 bilaterally, poor trunk stability. Specialty drive controls and power tilt/recline required for postural management and pressure relief.
ASSESSMENT & PLAN: Severe progressive neurological condition with total inability to self-propel manual mobility devices. Plan: Group 3 complex rehabilitative power wheelchair with multi-function power seating."""
)
add_vignette(
    "LCD-POWER-WC", "NEGATIVE_FRAMED", "Mild mobility deficit with preserved ability to propel manual chair", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Assistive Technology Clinic
SUBJECTIVE: 70-year-old presenting with mild exertional fatigue after knee arthrosis.
OBJECTIVE: Patient ambulates independently with a single-point cane for household distances. Upper extremity strength is 5/5 bilaterally; patient easily propels a standard manual wheelchair without fatigue.
ASSESSMENT & PLAN: Mild mobility deficit. Complex Group 3 power mobility equipment is not indicated given preserved ability to ambulate and operate standard manual mobility aids."""
)

# =========================================================================
# 21. LCD-PROTON: Proton Beam Radiotherapy
# Criteria:
# c1: ocular melanoma / chordoma / chondrosarcoma / pediatric malignancy
# c2: comparative proton vs photon plan showing sparing of adjacent OAR
# excl: widespread metastatic disease
# =========================================================================
add_vignette(
    "LCD-PROTON", "APPROVED", "Base of skull chordoma adjacent to brainstem and optic chiasm", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 44-year-old presenting with diplopia secondary to biopsy-proven clival chordoma following subtotal transsphenoidal surgical resection.
OBJECTIVE: Lesion abuts the anterior brainstem and optic chiasm. Comparative planning demonstrates that conventional photon VMAT delivers unacceptable toxic doses (brainstem max dose 62 Gy). The proton beam radiotherapy plan exploits the Bragg peak to deliver 74 Gy to gross tumor while constraining brainstem dose to 48 Gy. No metastatic disease.
ASSESSMENT & PLAN: Radioresistant skull base chordoma requiring high-dose escalation adjacent to critical neurovascular structures. Plan: Definitive proton beam radiotherapy with pencil beam scanning."""
)
add_vignette(
    "LCD-PROTON", "NEGATIVE_FRAMED", "Widespread metastatic disease with multiple hepatic and bone deposits", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 67-year-old with metastatic gastrointestinal carcinoma presenting with general fatigue and right upper quadrant discomfort.
OBJECTIVE: Staging PET-CT confirms widespread metastatic disease with over ten active hepatic lesions and diffuse skeletal metastases.
ASSESSMENT & PLAN: Widely disseminated metastatic cancer. Specialized proton beam therapy is not clinically indicated for widespread metastatic disease where systemic therapy and conventional palliation are standard."""
)

# =========================================================================
# 22. LCD-RAD-NIV: Respiratory Assist Devices (BiPAP with Backup)
# Criteria:
# c1: severe copd / neuromuscular disease with daytime hypercapnia (paco2 >= 52 mmHg)
# c2: failed standard nocturnal cpap / bipap without backup
# excl: uncomplicated obstructive sleep apnea
# =========================================================================
add_vignette(
    "LCD-RAD-NIV", "APPROVED", "Severe COPD with chronic hypercapnia failing standard PAP", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Pulmonary Sleep Medicine
SUBJECTIVE: 69-year-old with end-stage COPD and recurrent acute hypercapnic respiratory failures requiring repeated hospital admissions. Patient has used standard nocturnal CPAP and bilevel therapy without backup for 90 days with worsening morning lethargy.
OBJECTIVE: Daytime arterial blood gas on room air shows PaCO2 of 56 mmHg and PaO2 of 58 mmHg. Nocturnal capnography demonstrates persistent sleep-induced hypoventilation with prolonged desaturations.
ASSESSMENT & PLAN: Chronic hypercapnic respiratory failure secondary to severe COPD failing standard bilevel therapy. Plan: Respiratory assist device with backup rate (BiPAP S/T) for home non-invasive ventilation."""
)
add_vignette(
    "LCD-RAD-NIV", "NEGATIVE_FRAMED", "Uncomplicated obstructive sleep apnea with normal daytime carbon dioxide", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Pulmonary Sleep Medicine
SUBJECTIVE: 46-year-old with daytime somnolence and heavy snoring.
OBJECTIVE: Polysomnography reveals uncomplicated obstructive sleep apnea with AHI 22 events/hr. Daytime arterial blood gas shows completely normal PaCO2 of 38 mmHg without hypoventilation.
ASSESSMENT & PLAN: Moderate obstructive sleep apnea without respiratory failure. Advanced non-invasive ventilator with backup rate is contraindicated for uncomplicated sleep apnea; standard CPAP is indicated."""
)

# =========================================================================
# 23. LCD-ROTATOR-CUFF: Rotator Cuff Repair
# Criteria:
# c1: full-thickness rotator cuff tear on mri
# c2: conservative therapy trial >= 90 days (3 months)
# excl: rotator cuff arthropathy with severe glenohumeral arthritis
# =========================================================================
add_vignette(
    "LCD-ROTATOR-CUFF", "APPROVED", "Full-thickness supraspinatus tear failing 16 weeks physical therapy", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Shoulder and Elbow Orthopedic Surgery
SUBJECTIVE: 55-year-old male presenting with severe lateral shoulder weakness and night pain for 5 months. Has completed 16 weeks of structured rotator cuff physical therapy and an ultrasound-guided subacromial corticosteroid injection without functional improvement.
OBJECTIVE: Significant weakness on empty-can testing (3/5) and positive drop arm sign. Shoulder MRI reveals complete full-thickness rotator cuff tear of the supraspinatus tendon with 1.8 cm retraction. Plain films confirm well-preserved glenohumeral joint space without arthropathy.
ASSESSMENT & PLAN: Symptomatic full-thickness supraspinatus tendon tear refractory to 4 months of conservative management. Plan: Right arthroscopic rotator cuff repair with subacromial decompression."""
)
add_vignette(
    "LCD-ROTATOR-CUFF", "NEGATIVE_FRAMED", "Severe cuff tear arthropathy with bone-on-bone glenohumeral collapse", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Shoulder and Elbow Orthopedic Surgery
SUBJECTIVE: 78-year-old presenting with chronic shoulder immobility and grating pain for 4 years.
OBJECTIVE: Shoulder radiographs demonstrate superior humeral head migration with complete articulation against the acromion, severe glenoid erosion, and bone-on-bone arthritis (Hamada grade 4 rotator cuff arthropathy).
ASSESSMENT & PLAN: End-stage rotator cuff tear arthropathy. Isolated soft tissue rotator cuff repair is ineffective and contraindicated in the setting of severe glenohumeral arthritis."""
)

# =========================================================================
# 24. LCD-SBRT: Stereotactic Body Radiation Therapy (SBRT / SABR)
# Criteria:
# c1: early-stage non-small cell lung cancer (t1-t2n0m0) or isolated oligometastasis
# c2: medically inoperable status / multidisciplinary tumor board review
# excl: widespread diffuse metastasis (> 5 sites)
# =========================================================================
add_vignette(
    "LCD-SBRT", "APPROVED", "Medically inoperable clinical Stage I NSCLC of right upper lobe", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 76-year-old with severe baseline COPD (FEV1 32% predicted, home oxygen 2 L/min) evaluated for newly discovered right upper lobe solitary nodule. Thoracic surgery deemed patient medically inoperable due to high operative mortality risk.
OBJECTIVE: PET-CT confirms hypermetabolic 2.2 cm peripheral pulmonary lesion (SUV max 8.4) with zero mediastinal or distant nodal uptake (cT1cN0M0). Brain MRI negative. Multidisciplinary thoracic tumor board reviewed case and recommended stereotactic ablative delivery.
ASSESSMENT & PLAN: Medically inoperable early-stage non-small cell lung cancer. Plan: Stereotactic body radiation therapy (SBRT) delivering 50 Gy in 4 fractions with respiratory motion tracking."""
)
add_vignette(
    "LCD-SBRT", "NEGATIVE_FRAMED", "Disseminated metastatic carcinoma with widespread organ deposits", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Radiation Oncology
SUBJECTIVE: 63-year-old with metastatic breast cancer presenting for evaluation of pulmonary deposits.
OBJECTIVE: Restaging CT shows extensive widespread metastatic disease with multiple bilateral lung nodules (> 15 nodules), diffuse liver involvement, and multiple osseous lesions.
ASSESSMENT & PLAN: Widely metastatic disseminated malignancy. Focused stereotactic body radiation therapy is contraindicated in widespread polymetastatic disease."""
)

# =========================================================================
# 25. LCD-SHOULDER-ARTHRO: Total and Reverse Shoulder Arthroplasty
# Criteria:
# c1: end-stage glenohumeral osteoarthritis or massive irreparable rotator cuff tear
# c2: conservative therapy trial >= 90 days (3 months)
# excl: active joint infection
# =========================================================================
add_vignette(
    "LCD-SHOULDER-ARTHRO", "APPROVED", "Severe glenohumeral osteoarthritis failing 5 months conservative care", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Adult Reconstruction Orthopedics
SUBJECTIVE: 69-year-old presenting with chronic debilitating right shoulder pain and stiffness for 18 months. Patient has completed 20 weeks of supervised physical therapy, oral anti-inflammatories, and two intra-articular steroid injections without lasting relief. Denies active infection.
OBJECTIVE: Passive abduction limited to 60 degrees with bone-on-bone crepitus. Axillary and AP radiographs reveal end-stage glenohumeral osteoarthritis with complete loss of joint space, extensive inferior humeral osteophytes, and posterior glenoid wear. Intact rotator cuff musculature.
ASSESSMENT & PLAN: End-stage primary glenohumeral osteoarthritis with refractory functional disability after 5 months conservative care. Plan: Right anatomic total shoulder arthroplasty."""
)
add_vignette(
    "LCD-SHOULDER-ARTHRO", "NEGATIVE_FRAMED", "Severe shoulder arthrosis with active purulent joint infection", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Adult Reconstruction Orthopedics
SUBJECTIVE: 72-year-old presenting with acute-on-chronic shoulder swelling, severe warmth, and fevers for 3 days.
OBJECTIVE: Arthrocentesis of the right shoulder yields cloudy fluid with 85,000 WBC/uL and gram-positive cocci in clusters, confirming active joint infection (acute septic arthritis).
ASSESSMENT & PLAN: Acute septic glenohumeral joint infection on background chronic arthritis. Prosthetic total joint arthroplasty is strictly contraindicated in the presence of active sepsis."""
)

# =========================================================================
# 26. LCD-WOUND-VAC: Negative Pressure Wound Therapy (NPWT)
# Criteria:
# c1: stage III/IV pressure ulcer / chronic open dehisced surgical wound
# c2: failed standard moist wound dressings trial >= 30 days
# excl: untreated osteomyelitis in wound bed / necrotic tissue
# =========================================================================
add_vignette(
    "LCD-WOUND-VAC", "APPROVED", "Deep dehisced abdominal surgical wound failing 6 weeks moist dressings", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Advanced Wound Care Center
SUBJECTIVE: 61-year-old presenting with non-healing dehisced midline abdominal wound following bowel resection 7 weeks ago. Patient has undergone daily wound packing with moist alginate and hydrogel dressings for 42 days with minimal granulation progress.
OBJECTIVE: Measurement: 6.5 cm length x 3.0 cm width x 2.4 cm depth with healthy red granulation base. Sharp debridement completed; wound bed is completely clean with zero devitalized necrotic eschar. Probe to bone is negative, no untreated osteomyelitis.
ASSESSMENT & PLAN: Full-thickness chronic dehisced surgical wound refractory to 6 weeks of standard moist dressing therapy. Plan: Negative pressure wound therapy pump at 125 mmHg continuous suction."""
)
add_vignette(
    "LCD-WOUND-VAC", "NEGATIVE_FRAMED", "Sacral wound with 100% thick black necrotic eschar without debridement", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Advanced Wound Care Center
SUBJECTIVE: 81-year-old nursing home resident evaluated for chronic sacral ulceration.
OBJECTIVE: Examination reveals a 5 cm ulcer completely covered by thick, adherent black necrotic tissue and devitalized slough. No surgical debridement has been performed.
ASSESSMENT & PLAN: Unstageable necrotic pressure wound. Application of negative pressure wound therapy is contraindicated over un-debrided necrotic tissue or untreated osteomyelitis."""
)

# =========================================================================
# 27. NCD-CARDIAC-REHAB: Comprehensive Outpatient Cardiac Rehabilitation
# Criteria:
# c1: qualifying cardiac event (acute mi / cabg / stable angina / pci)
# c2: physician referral and individualized exercise prescription
# excl: unstable angina / acute decompensated heart failure
# =========================================================================
add_vignette(
    "NCD-CARDIAC-REHAB", "APPROVED", "Recent coronary artery bypass surgery ready for structured rehab", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Preventive Cardiology & Rehabilitation
SUBJECTIVE: 64-year-old presenting for initial intake 5 weeks following uncomplicated three-vessel coronary artery bypass graft surgery. Sternal incision well-healed without instability. Patient reports mild exertional shortness of breath when walking 1 block. Denies unstable angina or resting chest discomfort.
OBJECTIVE: Resting blood pressure 124/76 mmHg, heart rate 68 bpm regular. Normal cardiovascular exam with no third heart sound or peripheral edema. Attending cardiologist signed formal physician referral and prescribed individualized aerobic exercise plan.
ASSESSMENT & PLAN: Recent surgical revascularization for ischemic heart disease in stable clinical condition. Plan: Outpatient comprehensive cardiac rehabilitation program, 3 sessions weekly for 36 sessions."""
)
add_vignette(
    "NCD-CARDIAC-REHAB", "NEGATIVE_FRAMED", "Resting chest pain with acute decompensated heart failure", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Preventive Cardiology & Rehabilitation
SUBJECTIVE: 71-year-old presenting for rehab consultation reporting worsening shortness of breath while lying flat and crushing substernal chest pain occurring at rest over the past 24 hours.
OBJECTIVE: Jugular venous distension to the angle of the jaw, bilateral pulmonary crackles halfway up lung fields, and 3+ pitting pedal edema. ECG shows dynamic ST-segment depressions indicating unstable angina.
ASSESSMENT & PLAN: Acute decompensated heart failure and unstable angina. Exercise rehabilitation is strictly contraindicated; patient transferred immediately to the emergency department."""
)

# =========================================================================
# 28. NCD-CATARACT: Cataract Extraction with IOL Implantation
# Criteria:
# c1: visual acuity impairment <= 20/50 (best corrected)
# c2: functional impairment in activities of daily living (driving / reading)
# excl: visual loss attributable to advanced macular degeneration alone
# =========================================================================
add_vignette(
    "NCD-CATARACT", "APPROVED", "Dense nuclear sclerosis with visual acuity 20/60 impairing driving", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Ophthalmology Clinic
SUBJECTIVE: 73-year-old presenting with 14 months of progressive blurring and severe glare while driving at night. Patient is no longer able to read standard book print even with updated bifocal glasses, creating significant difficulty with daily activities.
OBJECTIVE: Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye. Slit-lamp biomicroscopy reveals 3+ dense nuclear sclerotic cataract and cortical spoking in the right eye. Dilated fundus examination shows healthy macula and optic nerve bilaterally without advanced macular degeneration.
ASSESSMENT & PLAN: Visually significant cataract in right eye causing substantial impairment of activities of daily living refractory to spectacles. Plan: Right phacoemulsification with intraocular lens implantation."""
)
add_vignette(
    "NCD-CATARACT", "NEGATIVE_FRAMED", "Mild 20/25 vision without functional impairment in daily tasks", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Ophthalmology Clinic
SUBJECTIVE: 58-year-old presenting for routine eye checkup. Patient drives without restriction, reads comfortably, and reports zero subjective visual complaints.
OBJECTIVE: Best corrected visual acuity is 20/25 in both eyes. Slit lamp exam shows trace 1+ nuclear discoloration. Clear macular architecture.
ASSESSMENT & PLAN: Mild non-visually significant lens changes with normal functional vision. Cataract surgery is not clinically indicated."""
)

# =========================================================================
# 29. NCD-CCTA: Coronary Computed Tomography Angiography
# Criteria:
# c1: low-to-intermediate pre-test probability of CAD with acute/stable chest pain
# c2: non-diagnostic or equivocal prior ECG / exercise stress test
# excl: high pre-test probability / confirmed acute coronary syndrome
# =========================================================================
add_vignette(
    "NCD-CCTA", "APPROVED", "Intermediate probability exertional chest tightness with equivocal ECG", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Outpatient Cardiology Evaluation
SUBJECTIVE: 51-year-old female with hyperlipidemia presenting with atypical exertional chest tightness lasting 10 minutes after stair climbing. Pre-test probability for obstructive coronary artery disease is intermediate (35%).
OBJECTIVE: Resting baseline 12-lead electrocardiogram demonstrates non-specific ST-T wave abnormalities that render exercise ECG stress testing non-diagnostic. Serum troponin negative. No signs of confirmed acute coronary syndrome.
ASSESSMENT & PLAN: Atypical chest discomfort in intermediate pre-test risk patient with equivocal baseline electrocardiogram. Plan: Coronary computed tomography angiography (CCTA) with prospective ECG gating."""
)
add_vignette(
    "NCD-CCTA", "NEGATIVE_FRAMED", "High-risk acute ST-elevation myocardial infarction", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Outpatient Cardiology Evaluation
SUBJECTIVE: 65-year-old male presenting with 2 hours of crushing substernal chest pressure, diaphoresis, and radiation into the left jaw.
OBJECTIVE: Immediate ECG demonstrates 4 mm ST-segment elevations across leads V1-V4 consistent with acute coronary syndrome and anterior STEMI.
ASSESSMENT & PLAN: Confirmed acute myocardial infarction. Outpatient coronary CT angiography is contraindicated; emergency invasive catheterization activated immediately."""
)

# =========================================================================
# 30. NCD-MPI-PET: Cardiac Positron Emission Tomography (PET)
# Criteria:
# c1: suspected or known CAD with inconclusive SPECT or high body mass index
# c2: myocardial viability assessment prior to surgical revascularization
# excl: low-risk asymptomatic screening
# =========================================================================
add_vignette(
    "NCD-MPI-PET", "APPROVED", "Ischemic cardiomyopathy with inconclusive SPECT due to body habitus", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Advanced Cardiovascular Imaging
SUBJECTIVE: 61-year-old with ischemic cardiomyopathy and BMI 44 kg/m2 evaluated for potential surgical coronary bypass revascularization. Prior SPECT myocardial perfusion study was inconclusive due to severe soft tissue attenuation artifacts.
OBJECTIVE: Echocardiogram shows left ventricular ejection fraction of 28% with anterior hypokinesis. Rest and pharmacological stress testing requested for evaluation of ischemia and hibernating myocardium.
ASSESSMENT & PLAN: Severe coronary disease and ischemic systolic dysfunction with inconclusive SPECT. Plan: Rubidium-82 and FDG cardiac positron emission tomography (PET) for myocardial perfusion and viability assessment."""
)
add_vignette(
    "NCD-MPI-PET", "NEGATIVE_FRAMED", "Asymptomatic executive checkup with zero cardiac risk factors", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Advanced Cardiovascular Imaging
SUBJECTIVE: 36-year-old asymptomatic executive requesting comprehensive full-body cardiovascular scan. Patient exercises vigorously 6 days a week without chest symptoms.
OBJECTIVE: Normal physical exam, normal resting ECG, zero family history of premature CAD.
ASSESSMENT & PLAN: Asymptomatic low-risk status. Diagnostic cardiac PET myocardial perfusion scanning is contraindicated for routine asymptomatic screening."""
)

# =========================================================================
# 31. NCD-PACEMAKER: Permanent Cardiac Pacemakers
# Criteria:
# c1: symptomatic persistent bradycardia (sinus pause > 3 sec / Mobitz II / complete AV block)
# c2: documented symptom-rhythm correlation
# excl: reversible causes (medication toxicity / Lyme carditis / electrolyte disturbance)
# =========================================================================
add_vignette(
    "NCD-PACEMAKER", "APPROVED", "Symptomatic complete third-degree heart block with syncope", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Cardiac Electrophysiology
SUBJECTIVE: 76-year-old presenting with recurrent unheralded syncope and severe dizzy spells. Patient collapsed twice while standing. Not taking AV nodal blocking agents.
OBJECTIVE: Telemetry monitoring reveals sinus rhythm at 75 bpm with complete atrioventricular dissociation and a ventricular escape rate of 32 bpm (complete AV block) correlating directly with pre-syncopal episodes. Normal thyroid function and serum potassium.
ASSESSMENT & PLAN: Symptomatic high-grade third-degree atrioventricular heart block in the absence of reversible causes. Plan: Dual-chamber permanent cardiac pacemaker implantation."""
)
add_vignette(
    "NCD-PACEMAKER", "NEGATIVE_FRAMED", "Transient sinus bradycardia secondary to severe beta-blocker overdose", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Cardiac Electrophysiology
SUBJECTIVE: 62-year-old presenting with lethargy after accidentally ingesting quadruple his prescribed dose of carvedilol.
OBJECTIVE: Heart rate 42 bpm with sinus rhythm and first-degree AV block. Serum toxicology confirms toxic beta-blocker levels. Following glucagon infusion and drug clearance, heart rate normalizes to 68 bpm.
ASSESSMENT & PLAN: Transient drug-induced bradycardia due to medication toxicity. Permanent pacemaker implantation is contraindicated for reversible pharmacological etiologies."""
)

# =========================================================================
# 32. NCD-PET-ONC: FDG-PET for Oncologic Staging and Restaging
# Criteria:
# c1: histologically confirmed biopsy-proven solid malignancy
# c2: initial staging / restaging following completion of therapy / suspected recurrence
# excl: routine surveillance in asymptomatic cancer without recurrence suspicion
# =========================================================================
add_vignette(
    "NCD-PET-ONC", "APPROVED", "Newly diagnosed biopsy-proven esophageal adenocarcinoma staging", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Medical Oncology Clinic
SUBJECTIVE: 60-year-old male with progressive dysphagia for solid foods over 3 months. Endoscopy and endoscopic ultrasound revealed a distal esophageal mass.
OBJECTIVE: Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma. Contrast CT of abdomen shows borderline gastrohepatic lymph nodes without definite distant metastases. Initial systemic staging required to determine resectability.
ASSESSMENT & PLAN: Newly diagnosed locally advanced esophageal carcinoma. Plan: Whole-body 18F-FDG positron emission tomography with computed tomography (PET-CT) for initial oncologic staging."""
)
add_vignette(
    "NCD-PET-ONC", "NEGATIVE_FRAMED", "Asymptomatic surveillance 5 years post-resection of early breast cancer", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Medical Oncology Clinic
SUBJECTIVE: 57-year-old female presenting for routine five-year survivorship checkup after lumpectomy for Stage IA breast cancer. Patient feels completely well with no bone pain, weight loss, or cough.
OBJECTIVE: Normal physical examination, well-healed scar, no adenopathy, recent diagnostic mammogram was negative.
ASSESSMENT & PLAN: Disease-free survivorship with zero clinical suspicion of recurrence. Routine surveillance whole-body PET-CT scanning is not recommended in asymptomatic early-stage survivors."""
)

# =========================================================================
# 33. NCD-PUMP: Implantable Infusion Pumps for Intrathecal Therapy
# Criteria:
# c1: severe chronic intractable pain or spasticity refractory to oral opioids / baclofen
# c2: successful preliminary temporary intrathecal screening trial (>= 50% relief)
# excl: active systemic or local infection / spinal canal obstruction
# =========================================================================
add_vignette(
    "NCD-PUMP", "APPROVED", "Severe intractable cancer pain failing systemic opioids with positive trial", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Pain and Palliative Medicine
SUBJECTIVE: 54-year-old with pelvic chordoma experiencing intractable visceral and somatic pelvic pain. Maximum tolerated oral and transdermal opioid regimens have produced intolerable sedation and constipation without adequate analgesia.
OBJECTIVE: Patient underwent temporary percutaneous intrathecal morphine screening trial under sterile conditions, achieving documented 75% pain reduction and clear sensorium. Normal CSF opening pressure; no spinal canal block. No systemic infection.
ASSESSMENT & PLAN: Intractable pelvic pain refractory to systemic medical therapy with successful preliminary intrathecal screening trial. Plan: Surgical implantation of programmable intrathecal infusion pump."""
)
add_vignette(
    "NCD-PUMP", "NEGATIVE_FRAMED", "Untreated bacteremia and local paraspinal abscess at surgical site", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Pain and Palliative Medicine
SUBJECTIVE: 63-year-old evaluated for severe back pain accompanied by chills and night sweats.
OBJECTIVE: Blood cultures positive for methicillin-sensitive Staphylococcus aureus. Lumbar MRI reveals paraspinal fluid collection and epidural inflammation.
ASSESSMENT & PLAN: Active systemic bacteremia and paraspinal soft tissue infection. Implantation of foreign intrathecal pump hardware is strictly contraindicated in the presence of active sepsis."""
)

# =========================================================================
# 34. NCD-SCS: Spinal Cord Stimulation for Chronic Intractable Pain
# Criteria:
# c1: chronic intractable neuropathic trunk/limb pain (failed back surgery syndrome / crps)
# c2: successful temporary percutaneous trial (>= 50% relief) >= 3 days
# excl: unresolved psychological contraindications / active substance abuse
# =========================================================================
add_vignette(
    "NCD-SCS", "APPROVED", "Failed back surgery syndrome with 80% relief during percutaneous trial", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Pain Clinic
SUBJECTIVE: 51-year-old with persistent burning neuropathic right leg and lower back pain following two prior lumbar decompressions (failed back surgery syndrome). Physical therapy, membrane stabilizers, and injections provided no relief over 2 years.
OBJECTIVE: Pre-procedure psychological evaluation completed and cleared with no unresolved behavioral contraindications. Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance.
ASSESSMENT & PLAN: Chronic neuropathic lower extremity pain refractory to conventional management with highly successful trial stimulation. Plan: Permanent spinal cord stimulation system implantation."""
)
add_vignette(
    "NCD-SCS", "NEGATIVE_FRAMED", "Failed trial stimulation with worsening pain and active cocaine abuse", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Pain Clinic
SUBJECTIVE: 44-year-old presenting following a 4-day temporary percutaneous stimulation trial.
OBJECTIVE: Patient reports that the trial device produced unpleasant dysesthesias with only 10% pain relief. Urine drug screen is positive for illicit cocaine metabolites, and psychiatric evaluation identifies active untreated substance use disorder.
ASSESSMENT & PLAN: Inadequate trial relief (< 50%) and active substance use disorder. Permanent neurostimulator implantation is contraindicated."""
)

# =========================================================================
# 35. NCD-SGD: Speech Generating Devices
# Criteria:
# c1: severe expressive communication impairment (aphasia / dysarthria / als)
# c2: comprehensive evaluation by licensed speech-language pathologist (SLP)
# excl: non-dedicated commercial general-purpose computer
# =========================================================================
add_vignette(
    "NCD-SGD", "APPROVED", "Severe expressive anarthria secondary to ALS failing natural speech", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Speech-Language Pathology & Assistive Technology
SUBJECTIVE: 63-year-old with bulbar-onset amyotrophic lateral sclerosis experiencing progressive loss of oral communication. Patient is unable to speak intelligibly to family or caregivers.
OBJECTIVE: Comprehensive assessment by licensed speech-language pathologist (SLP) documents profound anarthria with severe oral-motor dyspraxia. Receptive language and cognition remain intact. SLP completed formal device trial with dedicated eye-gaze speech-generating system; patient achieved 95% message accuracy. Device requested is a dedicated augmentative communication device.
ASSESSMENT & PLAN: Severe irreversible expressive communication deficit with successful formal SLP device trial. Plan: Dedicated synthesized speech-generating device with integrated eye-tracking access."""
)
add_vignette(
    "NCD-SGD", "NEGATIVE_FRAMED", "Request for un-adapted standard consumer entertainment tablet", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Speech-Language Pathology & Assistive Technology
SUBJECTIVE: 50-year-old with mild slurred speech following minor concussion requesting prescription for a personal consumer electronics tablet.
OBJECTIVE: Formal SLP evaluation indicates speech intelligibility is 88% with natural speech techniques. The requested hardware is an unlocked standard commercial retail tablet without communication software.
ASSESSMENT & PLAN: Mild transient dysarthria without profound expressive impairment; requested equipment is a general-purpose consumer device rather than a dedicated medical communication prosthesis."""
)

# =========================================================================
# 36. OPD-BLEPH: Blepharoplasty, Blepharoptosis Repair, and Brow Lift
# Criteria:
# c1: visual field restriction >= 30% or 12 degrees on testing
# c2: marginal reflex distance 1 (MRD1) <= 2.0 mm
# excl: purely cosmetic eyelid surgery / aesthetic appearance only
# =========================================================================
add_vignette(
    "OPD-BLEPH", "APPROVED", "Severe dermatochalasis with superior visual field restriction", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Ophthalmic Plastic & Reconstructive Surgery
SUBJECTIVE: 68-year-old presenting with heavy upper eyelids obscuring superior vision while reading and driving. Experiences frequent forehead ache from compensatory frontalis muscle strain. Denies requesting cosmetic eyelid rejuvenation.
OBJECTIVE: External photography demonstrates skin overhang resting on eyelashes in primary gaze with Marginal Reflex Distance 1 (MRD1) measured at 1.0 mm bilaterally. Automated visual field testing reveals a 36% superior visual field restriction with lids untaped, improving to normal boundaries when upper lids are manually taped.
ASSESSMENT & PLAN: Bilateral functional dermatochalasis and blepharoptosis with documented objective visual field loss and reduced MRD1. Plan: Bilateral functional upper lid blepharoplasty and ptosis repair."""
)
add_vignette(
    "OPD-BLEPH", "NEGATIVE_FRAMED", "Mild eyelid wrinkling without visual field obscuration", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Ophthalmic Plastic & Reconstructive Surgery
SUBJECTIVE: 49-year-old presenting requesting upper eyelid surgery because she feels her eyes look tired in photographs. She has zero difficulty reading or driving.
OBJECTIVE: External photographs show mild fine skin laxity. Marginal Reflex Distance 1 is 4.0 mm bilaterally (normal). Visual field testing demonstrates zero superior field restriction (loss < 5%).
ASSESSMENT & PLAN: Normal eyelid margins and intact functional visual field; request is purely cosmetic eyelid surgery. Surgical blepharoplasty is not clinically indicated for aesthetic concerns alone."""
)

# =========================================================================
# 37. OPD-BOTOX: Botulinum Toxin Injections
# Criteria:
# c1: chronic migraine frequency >= 15 headache days/month for >= 3 months
# c2: failed trials of >= 2 oral prophylactic drug classes (beta blocker / topiramate / etc.)
# excl: episodic migraine (< 15 days/month)
# =========================================================================
add_vignette(
    "OPD-BOTOX", "APPROVED", "Intractable chronic migraine 18 days/month failing oral prophylaxis", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Headache Center
SUBJECTIVE: 42-year-old presenting with chronic debilitating headaches for 2 years. Headache diary confirms 18 headache days per month, with 12 days meeting full criteria for throbbing migraine with photophobia and nausea. Patient has completed adequate 8-week trials of topiramate and propranolol without efficacy.
OBJECTIVE: Normal neurological examination. Normal brain MRI. Documented adherence to headache calendar over 4 consecutive months confirming chronic non-episodic pattern.
ASSESSMENT & PLAN: Chronic migraine refractory to two standard oral prophylactic medication classes. Plan: Botulinum toxin injection protocol (155 units across 31 designated head and neck sites)."""
)
add_vignette(
    "OPD-BOTOX", "NEGATIVE_FRAMED", "Episodic tension headache occurring 4 days per month", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Comprehensive Headache Center
SUBJECTIVE: 33-year-old evaluated for headaches occurring approximately 4 days per month during stressful work periods. No daily headache pattern.
OBJECTIVE: Neurological exam completely unremarkable. Patient has not trialed any daily preventive medications.
ASSESSMENT & PLAN: Episodic headache disorder (fewer than 15 headache days monthly). Botulinum toxin therapy is contraindicated for episodic migraine and requires prior oral prophylactic trials."""
)

# =========================================================================
# 38. OPD-CERV-DISC: Cervical Artificial Disc Arthroplasty
# Criteria:
# c1: single-level symptomatic cervical radiculopathy with nerve root compression
# c2: conservative therapy trial >= 42 days (6 weeks)
# excl: severe facet joint spondylosis / cervical instability
# =========================================================================
add_vignette(
    "OPD-CERV-DISC", "APPROVED", "Single-level C5-C6 soft disc radiculopathy failing 8 weeks therapy", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Spine Surgery
SUBJECTIVE: 38-year-old presenting with sharp electric radicular pain and tingling in right thumb and index finger for 3 months. Completed 8 weeks of focused physical therapy and non-steroidal medication without lasting improvement.
OBJECTIVE: Decreased sensation in C6 distribution. Cervical MRI shows isolated single-level C5-C6 soft disc herniation compressing the exiting right C6 nerve root. Dynamic flexion-extension views demonstrate preserved sagittal motion without segmental instability; facet joints are normal without arthrosis.
ASSESSMENT & PLAN: Single-level cervical radiculopathy refractory to 8 weeks conservative therapy with healthy facet joints. Plan: C5-C6 anterior cervical artificial disc arthroplasty."""
)
add_vignette(
    "OPD-CERV-DISC", "NEGATIVE_FRAMED", "Severe multilevel facet arthrosis and spondylolisthesis", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Orthopedic Spine Surgery
SUBJECTIVE: 67-year-old presenting with chronic neck stiffness and bilateral shoulder pain.
OBJECTIVE: Cervical CT and MRI demonstrate severe facet joint spondylosis with bridging osteophytes across C4-C7 and 4 mm translation on flexion views indicating dynamic segmental instability.
ASSESSMENT & PLAN: Multilevel degenerative disc disease with severe facet arthrosis and cervical instability. Motion-sparing artificial disc arthroplasty is contraindicated in the presence of facet spondylosis."""
)

# =========================================================================
# 39. OPD-PANNI: Panniculectomy and Abdominoplasty
# Criteria:
# c1: pannus hanging below pubis symphysis (grade 2 or greater)
# c2: refractory intertrigo / dermatitis >= 90 days (3 months)
# excl: purely cosmetic abdominoplasty / aesthetic body contouring
# =========================================================================
add_vignette(
    "OPD-PANNI", "APPROVED", "Massive abdominal pannus hanging past pubis with chronic ulcerated intertrigo", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Plastic and Reconstructive Surgery
SUBJECTIVE: 53-year-old female status post bariatric surgery with massive weight loss of 135 pounds, weight stable for 18 months. Patient presents with severe chronic painful intertrigo beneath the abdominal apron. Has performed topical antifungal powder, barrier creams, and oral antifungals for 5 months without resolution of skin breakdown. Denies cosmetic body contouring.
OBJECTIVE: Clinical photographs demonstrate an abdominal pannus hanging below pubic symphysis to mid-thigh level. Examination of the subpannic crease reveals extensive weeping erythema, maceration, and ulceration.
ASSESSMENT & PLAN: Functional disability and chronic refractory intertrigo secondary to massive apron pannus failing 5 months of topical medical therapy. Plan: Functional surgical panniculectomy."""
)
add_vignette(
    "OPD-PANNI", "NEGATIVE_FRAMED", "Mild abdominal wall laxity without dermatitis or sub-pubic apron", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Plastic and Reconstructive Surgery
SUBJECTIVE: 39-year-old presenting requesting tummy tuck surgery to tighten post-pregnancy stretch marks and abdominal bulge. Zero history of rash or skin infections.
OBJECTIVE: Examination shows mild diastasis recti and skin redundancy. The lower abdominal contour does not reach the pubic symphysis. The skin crease is completely clean, dry, and intact.
ASSESSMENT & PLAN: Aesthetic complaint without functional skin pathology; request is for cosmetic abdominoplasty. Surgical resection is not clinically indicated for aesthetic rejuvenation."""
)

# =========================================================================
# 40. OPD-RHINO: Rhinoplasty and Septoplasty
# Criteria:
# c1: chronic nasal airway obstruction >= 180 days (6 months)
# c2: conservative medical therapy trial >= 28 days (4 weeks) with intranasal steroids
# excl: cosmetic nasal reshaping / aesthetic dissatisfaction only
# =========================================================================
add_vignette(
    "OPD-RHINO", "APPROVED", "Severe nasal septal deviation and valve collapse failing topical steroids", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Otolaryngology - Head and Neck Surgery
SUBJECTIVE: 36-year-old presenting with chronic unilateral right-sided nasal airway obstruction causing persistent mouth breathing and sleep disruption for 1 year following nasal trauma. Patient has used intranasal fluticasone spray and nasal saline irrigations consistently for 8 weeks without improvement in airflow. Denies cosmetic dissatisfaction.
OBJECTIVE: Anterior rhinoscopy reveals marked S-shaped nasal septal deviation impacting the right inferior turbinate and positive modified Cottle maneuver demonstrating external nasal valve collapse on inspiration.
ASSESSMENT & PLAN: Structural nasal airway obstruction with severe septal deviation and valve collapse refractory to 8 weeks topical medical therapy. Plan: Functional septoplasty and functional rhinoplasty with spreader grafts."""
)
add_vignette(
    "OPD-RHINO", "NEGATIVE_FRAMED", "Desire for dorsal hump reduction without breathing obstruction", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Otolaryngology - Head and Neck Surgery
SUBJECTIVE: 24-year-old presenting requesting reduction of a prominent dorsal nasal hump. Patient reports normal bilateral nasal airflow during high-intensity exercise and sleep.
OBJECTIVE: Anterior rhinoscopy shows straight nasal septum with patent nasal passages bilaterally. Negative Cottle test. Intact internal and external valves.
ASSESSMENT & PLAN: Completely patent functional nasal airway; presentation is for cosmetic nasal reshaping. Surgical rhinoplasty is not indicated for aesthetic dorsal modification alone."""
)

# =========================================================================
# 41. OPD-SI-FUSION: Minimally Invasive Sacroiliac Joint Fusion
# Criteria:
# c1: diagnostic SI joint injection pain relief >= 75%
# c2: positive provocation tests >= 3 (FABER / Gaenslen / Thigh thrust / etc.)
# excl: active systemic infection / untreated pelvic malignancy
# =========================================================================
add_vignette(
    "OPD-SI-FUSION", "APPROVED", "Chronic sacroiliac joint dysfunction with positive provocative tests and block", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Spine and Orthopedics
SUBJECTIVE: 47-year-old presenting with persistent unilateral right lower back and buttock pain below L5 for 10 months. Patient completed 16 weeks of focused physical therapy and pelvic stabilization exercises with refractory symptoms. No fever or systemic symptoms.
OBJECTIVE: Physical exam reveals positive provocation tests on 4 validated maneuvers: positive FABER, positive Gaenslen, positive thigh thrust, and positive distraction test. Fluoroscopically guided diagnostic right sacroiliac joint block produced documented 85% relief of baseline pain during the anesthetic window.
ASSESSMENT & PLAN: Severe chronic right sacroiliac joint dysfunction with positive provocative physical signs and > 75% relief on diagnostic intra-articular block. Plan: Minimally invasive right sacroiliac joint fusion."""
)
add_vignette(
    "OPD-SI-FUSION", "NEGATIVE_FRAMED", "Negative provocative tests and zero pain relief from diagnostic block", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Interventional Spine and Orthopedics
SUBJECTIVE: 55-year-old presenting with generalized pelvic and diffuse lower back discomfort.
OBJECTIVE: Sacroiliac provocation testing is negative across all maneuvers (negative FABER, negative compression). Diagnostic SI joint injection performed under fluoroscopy produced zero percent pain reduction.
ASSESSMENT & PLAN: Non-localized axial back pain without clinical or diagnostic evidence of sacroiliac pathology. Sacroiliac joint fusion surgery is not clinically indicated."""
)

# =========================================================================
# 42. OPD-VEIN: Endovenous Ablation Therapy for Varicose Veins
# Criteria:
# c1: venous reflux duration >= 500 ms on duplex ultrasound
# c2: graduated compression stockings trial >= 90 days (3 months)
# excl: asymptomatic spider veins only / cosmetic telangiectasias
# =========================================================================
add_vignette(
    "OPD-VEIN", "APPROVED", "Symptomatic great saphenous insufficiency with 1200ms reflux failing stockings", "APPROVED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Outpatient Clinic
SUBJECTIVE: 52-year-old presenting with severe aching, throbbing, and heavy sensation in right lower extremity after standing for more than 30 minutes at work. Symptoms present for 2 years. Patient has worn prescription 20-30 mmHg graduated compression stockings daily for 16 weeks with persistent painful swelling. Denies cosmetic concerns.
OBJECTIVE: Visible tortuous bulging varicosities along the medial right calf with stasis hyperpigmentation. Standing duplex ultrasound demonstrates great saphenous vein reflux duration of 1450 ms at the saphenofemoral junction with vein diameter of 7.8 mm.
ASSESSMENT & PLAN: Symptomatic severe saphenofemoral incompetence with duplex-verified pathological venous reflux refractory to 4 months graduated compression therapy. Plan: Right great saphenous endovenous radiofrequency ablation."""
)
add_vignette(
    "OPD-VEIN", "NEGATIVE_FRAMED", "Isolated spider veins without axial reflux or compression trial", "DENIED",
    """[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Vascular Surgery Outpatient Clinic
SUBJECTIVE: 30-year-old presenting requesting laser therapy for spider veins on the lateral thighs before summer vacation. Patient denies leg heaviness, swelling, or pain.
OBJECTIVE: Lower extremity examination reveals small superficial telangiectasias and spider veins only. Bilateral standing duplex ultrasound demonstrates normal valvular competence with venous reflux under 150 ms in all deep and superficial veins.
ASSESSMENT & PLAN: Asymptomatic superficial telangiectasias without pathological venous reflux. Endovenous thermal ablation is contraindicated for cosmetic spider veins."""
)

def main():
    print(f"[*] Generating {len(VIGNETTES)} uncued clinical development vignettes...")
    out_file = POLICIES_DIR / "dev_vignettes_extended.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(VIGNETTES, f, indent=2)
    print(f"[*] Saved {len(VIGNETTES)} vignettes to {out_file}")

if __name__ == "__main__":
    main()

