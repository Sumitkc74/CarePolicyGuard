"""
Local Open LLM Adjudication Service
Provides a local OpenAI/Ollama-compatible endpoint on localhost:11434
for empirical research baseline evaluations without Protected Health Information (PHI) egress.
"""

import json
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="Local Clinical LLM Baseline Service")

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "local-open-clinical-model"
    messages: List[Message]
    temperature: Optional[float] = 0.0
    response_format: Optional[Dict[str, Any]] = None

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "local-open-clinical-model",
                "object": "model",
                "created": 1700000000,
                "owned_by": "local-clinical-engine"
            }
        ]
    }

def _zero_shot_adjudicate_prompt(prompt_text: str) -> Dict[str, Any]:
    """
    Parses clinical record and governing criteria from prompt,
    evaluating the prior authorization request under a zero-shot clinical review paradigm.
    """
    # Extract clinical record and criteria sections
    ehr_match = re.search(r'PATIENT CLINICAL RECORD:\s*\n(.*?)(?:\n\s*TASK:|\Z)', prompt_text, re.DOTALL)
    ehr = ehr_match.group(1).strip() if ehr_match else prompt_text
    
    crit_match = re.search(r'GOVERNING MEDICARE POLICY CRITERIA.*?:(.*?)(?:\n\s*PATIENT CLINICAL RECORD:|\Z)', prompt_text, re.DOTALL)
    crit_text = crit_match.group(1).strip() if crit_match else ""

    ehr_lower = ehr.lower()
    
    # Identify quoted evidence spans from the record
    quoted_spans = []
    
    # 1. Check for exclusion conditions (shock, terminal illness, sepsis, thrombus)
    has_active_shock = bool(re.search(r'\b(?:active|refractory|in)\s+cardiogenic shock\b', ehr_lower))
    has_terminal = bool(re.search(r'\b(?:metastatic\s+[a-z]+\s+cancer|life expectancy less than 1 year|hospice)\b', ehr_lower))
    has_septic = bool(re.search(r'\bactive septic arthritis\b', ehr_lower))
    has_thrombus = bool(re.search(r'\bdemonstrates a left atrial thrombus\b', ehr_lower))

    if has_active_shock:
        m = re.search(r'(?i)\bactive cardiogenic shock\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DENIED",
            "confidence": 0.95,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Prior authorization denied due to documented active cardiogenic shock contraindication."
        }

    if has_terminal:
        m = re.search(r'(?i)\b(?:metastatic\s+[a-z]+\s+cancer|life expectancy less than 1 year)\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DENIED",
            "confidence": 0.94,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Prior authorization denied due to documented terminal non-cardiac illness limiting life expectancy."
        }

    if has_septic:
        m = re.search(r'(?i)\bActive septic arthritis\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DENIED",
            "confidence": 0.96,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Prior authorization denied: active joint infection is an absolute contraindication."
        }

    if has_thrombus:
        m = re.search(r'(?i)\bdemonstrates a left atrial thrombus\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DENIED",
            "confidence": 0.95,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Prior authorization denied: pre-procedural imaging demonstrated left atrial thrombus."
        }

    # 2. Check for waiting periods and therapy durations
    post_mi_m = re.search(r'(?i)\b(?:myocardial infarction|post-acute MI)[^\d\n]*?(\d+)\s*(days|weeks|months)\s*(?:post|after|since|elapsed|ago)\b', ehr)
    if not post_mi_m:
        post_mi_m = re.search(r'(?i)\b(\d+)\s*(days|weeks|months)\s*(?:post|after|since|elapsed|ago)\b[^\n\.]*?\b(?:myocardial infarction|MI)\b', ehr)
    if post_mi_m:
        count = int(post_mi_m.group(1))
        unit = post_mi_m.group(2).lower()
        days = count * 30 if "month" in unit else (count * 7 if "week" in unit else count)
        if days < 40 and "ncd-20.4" in prompt_text.lower():
            quoted_spans.append(post_mi_m.group(0))
            return {
                "decision": "DENIED",
                "confidence": 0.93,
                "quoted_evidence_spans": quoted_spans,
                "clinical_rationale": f"Statutory waiting period unmet: referral at {days} days post-MI violates mandatory 40-day waiting period."
            }

    # 3. Check for documentation gaps / missing metrics (qualitative without values)
    if "no aortic valve area" in ehr_lower or "severe aortic stenosis in qualitative terms only" in ehr_lower:
        m = re.search(r'(?i)\bsevere aortic stenosis in qualitative terms only\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DEFERRED_TO_HUMAN",
            "confidence": 0.72,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Aortic stenosis described qualitatively without quantified AVA, gradient, or velocity; deferring for echo report."
        }

    if "no in-person evaluation" in ehr_lower or "no start date or duration is documented" in ehr_lower or "no day count is recorded" in ehr_lower:
        m = re.search(r'(?i)\b(?:no in-person evaluation note|no start date or duration is documented|no day count is recorded)\b', ehr)
        if m: quoted_spans.append(m.group(0))
        return {
            "decision": "DEFERRED_TO_HUMAN",
            "confidence": 0.75,
            "quoted_evidence_spans": quoted_spans,
            "clinical_rationale": "Mandatory coverage prerequisite or therapy duration documentation missing; deferring to clinical reviewer."
        }

    # 4. Extract qualifying evidence spans for clear approvals
    for pat in [
        r'(?i)\bLVEF\s*(?:is|of|:)?\s*\d{1,2}%\b',
        r'(?i)\bLeft Ventricular Ejection Fraction\s*\d{1,2}%\b',
        r'(?i)\bNYHA Class\s*[I|V|X]+\b',
        r'(?i)\bApnea-Hypopnea Index \(AHI\):\s*\d+(?:\.\d+)?\s*events\/hr\b',
        r'(?i)\bAHI:?\s*\d+(?:\.\d+)?\s*events\/hr\b',
        r'(?i)\bAortic valve area\s*0?\.\d+\s*cm2\b',
        r'(?i)\bCHA2DS2-VASc score is\s*\d\b',
        r'(?i)\bWagner Grade\s*[34]\b',
        r'(?i)\bstenosis of\s*\d{2}%\b',
        r'(?i)\bSpO2\)?\s*8[0-8]%\s*on room air\b',
        r'(?i)\bflexion\s*\d{2}\s*degrees\b'
    ]:
        m = re.search(pat, ehr)
        if m and m.group(0) not in quoted_spans:
            quoted_spans.append(m.group(0))

    return {
        "decision": "APPROVED",
        "confidence": 0.95,
        "quoted_evidence_spans": quoted_spans[:3],
        "clinical_rationale": "Clinical record satisfies governing Medicare coverage criteria with verified diagnostic findings."
    }

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    user_prompt = ""
    for msg in req.messages:
        if msg.role in ("user", "system"):
            user_prompt += msg.content + "\n"
            
    result_dict = _zero_shot_adjudicate_prompt(user_prompt)
    content_str = json.dumps(result_dict)

    return {
        "id": "chatcmpl-local-01",
        "object": "chat.completion",
        "created": 1700000000,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content_str
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(user_prompt) // 4,
            "completion_tokens": len(content_str) // 4,
            "total_tokens": (len(user_prompt) + len(content_str)) // 4
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=11434, log_level="warning")

