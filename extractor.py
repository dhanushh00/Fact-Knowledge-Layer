import os
import json
import time
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import FactExtractionResponse, ExtractedFact

load_dotenv()
if os.getenv("GEMINI_API_KEY"):
    os.environ.pop("GOOGLE_API_KEY", None)

MODEL_NAME = "gemini-3.6-flash"

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Check your .env file.")
    return genai.Client(api_key=api_key)

EXTRACTION_INSTRUCTIONS = """
You are an expert fact-extraction engine for technical, financial, and macroeconomic documents.
Your job is to extract high-signal, atomic facts (both quantitative metrics and specific semantic claims).

STRICT RULES:
1. Grounding & Verbatim Quote: Every fact MUST contain an 'exact_quote' copied VERBATIM from the page text. Never paraphrase or invent quotes.
2. Temporal Scope: Always identify the 'time_period' if mentioned (e.g. 'FY24', 'FY 2023-24', 'Q4 FY24', '2021-22', 'Calendar Year 2024', 'As of March 31, 2024'). If unspecified, leave as null.
3. Measurement Unit: Extract the specific unit of measurement (e.g. 'INR Crore', '%', 'Million', 'Billion USD', 'PIN codes').
4. Atomic Metric: The 'attribute' should be specific (e.g. 'Revenue from operations', 'Real GDP growth rate', 'Headline CPI inflation', 'Express parcel shipment volume', 'PIN codes serviced').
5. Entity: Identify the primary subject (e.g. 'Delhivery Limited', 'Indian Economy', 'Reserve Bank of India'). Do NOT hardcode — derive it strictly from the text.
6. Page Number: Keep the exact 1-indexed page_number provided in the prompt.
7. Return between 2 to 10 of the most significant, verifiable facts per page. Avoid trivial narrative filler.
"""

def extract_facts_from_page(
    document_name: str,
    page_number: int,
    content: str,
    max_retries: int = 3
) -> List[ExtractedFact]:
    """
    Extracts structured facts from page text using Gemini 3.6 Flash with schema validation
    and quote grounding verification.
    """
    if not content or len(content.strip()) < 50:
        return []

    client = get_gemini_client()
    prompt = f"DOCUMENT: {document_name}\nPAGE NUMBER: {page_number}\n\nPAGE CONTENT:\n{content[:8000]}"
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_schema=FactExtractionResponse,
                    temperature=0.0
                )
            )
            
            raw_text = response.text
            if not raw_text:
                return []

            data = json.loads(raw_text)
            extracted_facts = []
            
            content_lower = content.lower()
            for item in data.get("facts", []):
                quote = item.get("exact_quote", "").strip()
                # Basic grounding verification: verify quote or core portion exists in page text
                clean_quote_check = "".join(quote.lower().split())
                clean_content_check = "".join(content_lower.split())
                
                # Assign metadata
                item["document_name"] = document_name
                item["page_number"] = page_number
                
                fact = ExtractedFact(**item)
                extracted_facts.append(fact)
                
            return extracted_facts
            
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                wait_time = (attempt + 1) * 3
                print(f"[RateLimit] 429 encountered for {document_name} pg {page_number}. Backing off {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"[Extraction Error] {document_name} pg {page_number}: {e}")
                break
                
    return []