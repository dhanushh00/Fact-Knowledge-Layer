from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class FactType(str, Enum):
    NUMERICAL = "numerical"
    SEMANTIC = "semantic"

class ExtractedFact(BaseModel):
    id: Optional[int] = Field(None, description="Database unique ID")
    entity: str = Field(description="The entity name, e.g., 'Delhivery Limited', 'Indian Economy', 'Reserve Bank of India'")
    attribute: str = Field(description="Metric, claim, or state, e.g., 'Revenue from operations', 'Real GDP growth rate', 'Active express delivery pin codes'")
    value: str = Field(description="Raw figure, percentage, or semantic state, e.g., '7,225', '8.2%', '17,000+'")
    unit: Optional[str] = Field(None, description="Measurement unit (e.g., 'INR Crore', '%', 'pincodes', 'USD Billion')")
    time_period: Optional[str] = Field(None, description="Time vintage or temporal scope (e.g., 'FY24', 'FY22', 'Q4 FY24', '2024-25', 'As of Dec 31, 2021')")
    fact_type: FactType = Field(FactType.NUMERICAL, description="Numerical metric or semantic statement")
    exact_quote: str = Field(description="Exact snippet quoted directly from the source PDF page")
    page_number: int = Field(description="1-indexed physical page number of the source document")
    document_name: Optional[str] = Field(None, description="Filename of the source PDF")

class FactExtractionResponse(BaseModel):
    facts: List[ExtractedFact]

class RelationshipType(str, Enum):
    CORROBORATE = "corroborate"
    CONTRADICT = "contradict"
    RECONCILE_WITH_CONTEXT = "reconcile_with_context"

class ReconciliationCategory(str, Enum):
    TIME_PERIOD = "time_period"
    SCOPE_MEASUREMENT = "scope_measurement"
    UNIT_SCALE = "unit_scale"
    METHODOLOGY_REVISION = "methodology_revision"
    NOT_APPLICABLE = "none"

class ComparisonResult(BaseModel):
    relationship: RelationshipType = Field(description="Cross-document relationship classification")
    reconciliation_category: ReconciliationCategory = Field(
        default=ReconciliationCategory.NOT_APPLICABLE,
        description="The primary driver of context reconciliation (time, scope, unit, methodology)"
    )
    reconciliation_reason: str = Field(
        description="Clear natural language explanation explaining why facts corroborate, genuinely conflict, or reconcile via contextual differences, referencing both sources and figures."
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score of this relationship (0.0 to 1.0)")