import os
import json
import time
from typing import Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import ExtractedFact, ComparisonResult, RelationshipType, ReconciliationCategory

load_dotenv()
if os.getenv("GEMINI_API_KEY"):
    os.environ.pop("GOOGLE_API_KEY", None)

MODEL_NAME = "gemini-3.6-flash"

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Check your .env file.")
    return genai.Client(api_key=api_key)

REASONING_SYSTEM_INSTRUCTION = """
You are an expert fact-reconciliation engine analyzing facts across financial, technical, and macroeconomic documents.
Your task is to compare two facts from different documents and evaluate their relationship.

TAXONOMY DEFINITION:
1. 'corroborate':
   - Both documents affirm the same factual claim or metric under the same or compatible scope and time period.
   - Variations in phrasing, rounding, or wording still count as corroboration (e.g. '17,000+ pin codes' vs 'over 17,000 postal codes'; or '8.2% GDP growth' stated in both reports).

2. 'contradict':
   - Genuine or likely conflict. Both facts describe the EXACT SAME entity, metric, and time period, yet state conflicting, irreconcilable values without any contextual explanation.

3. 'reconcile_with_context':
   - The facts appear to disagree or show different numbers, but the discrepancy is explained by:
     * Time period differences (e.g., FY22 vs FY24, or Q4 quarterly figure vs Full-Year total).
     * Scope of measurement (e.g., Standalone vs Consolidated financial statements; Express Parcel segment vs Total Company revenue).
     * Units or currency differences (e.g., Crores vs Millions, USD vs INR).
     * Methodology or Vintage revisions (e.g., Real GDP at constant prices vs Nominal GDP at current prices; Provisional Estimates vs Revised Estimates).

RULES:
- If the two facts are talking about completely unrelated things and cannot be sensibly compared, return confidence 0.0.
- State your reasoning clearly and objectively, explicitly citing the specific values, units, time periods, and quotes from both facts.
- Choose the correct 'reconciliation_category': 'time_period', 'scope_measurement', 'unit_scale', 'methodology_revision', or 'none'.
"""

def compare_facts(fact_a: ExtractedFact, fact_b: ExtractedFact, max_retries: int = 3) -> Optional[ComparisonResult]:
    """
    Compares two cross-document facts using Gemini 3.6 Flash to establish corroboration,
    contradiction, or contextual reconciliation.
    """
    if fact_a.document_name == fact_b.document_name:
        return None

    client = get_gemini_client()
    
    prompt = f"""
FACT A:
- Source Document: {fact_a.document_name} (Page {fact_a.page_number})
- Entity: {fact_a.entity}
- Metric/Attribute: {fact_a.attribute}
- Value & Unit: {fact_a.value} {fact_a.unit or ''}
- Time Vintage / Scope: {fact_a.time_period or 'Unspecified'}
- Verbatim Evidence: "{fact_a.exact_quote}"

FACT B:
- Source Document: {fact_b.document_name} (Page {fact_b.page_number})
- Entity: {fact_b.entity}
- Metric/Attribute: {fact_b.attribute}
- Value & Unit: {fact_b.value} {fact_b.unit or ''}
- Time Vintage / Scope: {fact_b.time_period or 'Unspecified'}
- Verbatim Evidence: "{fact_b.exact_quote}"

Evaluate whether these two facts discuss comparable metrics and classify their relationship.
"""

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=REASONING_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=ComparisonResult,
                    temperature=0.0
                )
            )
            
            raw_text = response.text
            if not raw_text:
                return None

            result_data = json.loads(raw_text)
            result = ComparisonResult(**result_data)
            
            # Confidence threshold: only keep confident, meaningful comparisons
            if result.confidence >= 0.65:
                return result
            return None
            
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                wait_time = (attempt + 1) * 8
                print(f"[RateLimit] 429 encountered during comparison. Backing off {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"[Comparison Error]: {e}")
                break

    return None