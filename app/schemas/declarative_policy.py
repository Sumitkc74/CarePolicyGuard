from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

class CriterionType(str, Enum):
    NUMERIC_THRESHOLD = "NUMERIC_THRESHOLD"
    ORDINAL_RANK = "ORDINAL_RANK"
    TEMPORAL_DURATION = "TEMPORAL_DURATION"
    FINDING_PRESENCE = "FINDING_PRESENCE"
    EXCLUSION_SYMPTOM = "EXCLUSION_SYMPTOM"

class DeclarativeCriterion(BaseModel):
    """
    Policy-as-Data Declarative Criterion Schema.
    Decouples clinical policy definition from procedural execution code.
    Enables zero-code addition of new CMS LCDs/NCDs via structured JSON/YAML.
    """
    model_config = ConfigDict(from_attributes=True)

    criterion_code: str = Field(..., description="Unique criterion code e.g. CRIT-ICD-01")
    name: str = Field(..., description="Human-readable criterion title")
    description: str = Field(..., description="Official statutory criterion narrative")
    clinical_intent: str = Field(default="Statutory Medicare coverage requirement", description="Clinical justification")
    criterion_type: CriterionType = Field(default=CriterionType.NUMERIC_THRESHOLD, description="Operational evaluation paradigm")
    entity_names: List[str] = Field(default_factory=list, description="Clinical synonyms, abbreviations, and trade names")
    operator: Optional[str] = Field(default=None, description="Relational operator: <=, >=, <, >, ==, in")
    threshold: Optional[float] = Field(default=None, description="Numeric cutoff e.g. 35.0 for LVEF or 15.0 for AHI")
    target_unit: Optional[str] = Field(default=None, description="Expected unit e.g. %, events/hr, mm Hg")
    ordinal_allowed: Optional[List[str]] = Field(default=None, description="Qualifying ordinal classes e.g. ['II', 'III', 'IV']")
    min_duration_days: Optional[int] = Field(default=None, description="Minimum duration required e.g. 90 days for GDMT")
    is_exclusion: bool = Field(default=False, description="True if meeting this condition disqualifies coverage")
    negation_sensitive: bool = Field(default=True, description="Enforces ConText/NegEx clinical scope analysis")
    required_temporal_window: Optional[str] = Field(default="Within past 12 months", description="Statutory window")
    icd10_preconditions: List[str] = Field(default_factory=list, description="Diagnostic ICD-10 code patterns")
    cpt_preconditions: List[str] = Field(default_factory=list, description="Procedure CPT code patterns")
    min_score: float = Field(default=0.85, description="Evidence sufficiency weight")

class DeclarativePolicy(BaseModel):
    """
    Full Policy-as-Data Container representing a complete Medicare NCD/LCD.
    """
    model_config = ConfigDict(from_attributes=True)

    policy_id: str = Field(..., description="CMS Policy Identifier e.g. NCD-20.4 or LCD-L33829")
    title: str = Field(..., description="Official Policy Title")
    jurisdiction: str = Field(default="National Coverage Determination (NCD)", description="Jurisdiction")
    effective_date: str = Field(default="2024-01-01", description="Statutory effective date")
    category: str = Field(default="General Medicine", description="Clinical domain")
    description: str = Field(..., description="Summary of policy coverage")
    criteria: List[DeclarativeCriterion] = Field(default_factory=list, description="Declarative criteria set")
    statutory_waiting_periods: List[Dict[str, Any]] = Field(default_factory=list, description="Longitudinal timeline rules")
