import os
import sys
import json
import time
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()
if os.getenv("GEMINI_API_KEY"):
    os.environ.pop("GOOGLE_API_KEY", None)

from database import (
    init_db, store_facts, fetch_all_facts, store_comparison,
    fetch_all_comparisons, record_document, comparison_exists
)
from ingestion import extract_pages
from extractor import extract_facts_from_page
from linker import find_candidate_pairs
from reasoner import compare_facts
from models import ExtractedFact

def run_real_dataset_pipeline():
    print("=" * 75)
    print("  FACT KNOWLEDGE LAYER — AUTOMATED END-TO-END VERIFICATION PIPELINE")
    print("=" * 75)

    init_db()
    
    delhivery_dir = os.path.join("starter-datasets", "delhivery")
    macro_dir = os.path.join("starter-datasets", "india-macroeconomy")

    # High-signal curated excerpt pages with strong cross-document overlap
    documents_to_process = [
        {
            "path": os.path.join(delhivery_dir, "01-delhivery-prospectus-2022-excerpt.pdf"),
            "name": "01-delhivery-prospectus-2022-excerpt.pdf",
            "pages": [1, 3, 4]
        },
        {
            "path": os.path.join(delhivery_dir, "02-delhivery-annual-report-fy24-excerpt.pdf"),
            "name": "02-delhivery-annual-report-fy24-excerpt.pdf",
            "pages": [2, 3, 12]
        },
        {
            "path": os.path.join(delhivery_dir, "03-delhivery-q4-fy24-earnings-presentation.pdf"),
            "name": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "pages": [7, 9]
        },
        {
            "path": os.path.join(macro_dir, "01-india-economic-survey-2024-25-excerpt.pdf"),
            "name": "01-india-economic-survey-2024-25-excerpt.pdf",
            "pages": [4, 5]
        },
        {
            "path": os.path.join(macro_dir, "02-rbi-annual-report-2024-25-excerpt.pdf"),
            "name": "02-rbi-annual-report-2024-25-excerpt.pdf",
            "pages": [5, 6]
        },
        {
            "path": os.path.join(macro_dir, "03-imf-india-2025-article-iv-excerpt.pdf"),
            "name": "03-imf-india-2025-article-iv-excerpt.pdf",
            "pages": [1, 2]
        }
    ]

    # Step 1: Incremental Ingestion & Extraction
    print("\n--- [STEP 1/3] INCREMENTAL PDF INGESTION & GROUNDED FACT EXTRACTION ---")
    
    for doc in documents_to_process:
        if not os.path.exists(doc["path"]):
            print(f"Skipping {doc['name']} (file not found)")
            continue

        existing = fetch_all_facts(document_name=doc["name"])
        if existing:
            print(f"[Incremental Skip] {doc['name']}: {len(existing)} facts already in knowledge layer.")
            continue

        print(f"\n[Ingesting] {doc['name']} (Pages {doc['pages']})...")
        extracted_pages = extract_pages(doc["path"], page_numbers=doc["pages"])
        
        doc_facts = []
        for p in extracted_pages:
            print(f"  -> Page {p['page_number']} ({len(p['text'])} chars)...", end=" ", flush=True)
            facts = extract_facts_from_page(doc["name"], p["page_number"], p["text"])
            print(f"Extracted {len(facts)} grounded facts.")
            doc_facts.extend(facts)
            time.sleep(1.5)

        inserted = store_facts(doc_facts)
        total_pages_in_pdf = extracted_pages[0]["total_pages"] if extracted_pages else 0
        record_document(doc["name"], total_pages_in_pdf, len(extracted_pages), inserted)
        print(f"  => Stored {inserted} facts for {doc['name']}")

    all_stored_facts = fetch_all_facts()
    print(f"\n[Extraction Completed] Total Grounded Facts in Database: {len(all_stored_facts)}")

    # Step 2: Candidate Linking
    print("\n--- [STEP 2/3] CANDIDATE PAIR LINKING (Pruning O(N^2)) ---")
    fact_objs = [(r["id"], ExtractedFact(**json.loads(r["raw_json"]))) for r in all_stored_facts]
    
    candidates = find_candidate_pairs(fact_objs, min_score=0.20, max_candidates=40)
    print(f"Discovered {len(candidates)} high-potential cross-document candidate pairs.")

    # Step 3: Cross-Document Reasoning
    print("\n--- [STEP 3/3] CROSS-DOCUMENT REASONING & CLASSIFICATION ---")
    new_comps = 0
    for idx, (id_a, fa, id_b, fb, score) in enumerate(candidates):
        if comparison_exists(id_a, id_b):
            continue
        print(f"Evaluating Pair {idx+1}/{len(candidates)}: [{fa.attribute}] vs [{fb.attribute}]...", end=" ", flush=True)
        result = compare_facts(fa, fb)
        if result:
            store_comparison(id_a, id_b, result)
            new_comps += 1
            print(f"[{result.relationship.value.upper()}] ({result.reconciliation_category.value})")
            print(f"    Reasoning: {result.reconciliation_reason[:95]}...")
        else:
            print("[Not comparable / low confidence]")
        time.sleep(1.2)

    print(f"\n[Reasoning Completed] Recorded {new_comps} new relationships.")

    # Step 4: Summary of Demonstrated Cases
    print("\n" + "=" * 75)
    print("RESULTS: THE FOUR DEMONSTRATED CASES (GROUNDED IN STARTER DATASETS)")
    print("=" * 75)

    comps = fetch_all_comparisons()
    corroborate = [c for c in comps if c["relationship"] == "corroborate"]
    contradict = [c for c in comps if c["relationship"] == "contradict"]
    reconciled = [c for c in comps if c["relationship"] == "reconcile_with_context"]

    print(f"\nSummary of relationships: Corroborated={len(corroborate)}, Contradictions={len(contradict)}, Reconciled={len(reconciled)}")

    print("\n--- CASE 1: CORROBORATION ACROSS DOCUMENTS ---")
    if corroborate:
        for idx, c in enumerate(corroborate[:2]):
            print(f"\n[Corroboration #{idx+1}]")
            print(f"  Source A: {c['doc_a']} (Pg {c['page_a']}) => {c['attr_a']}: {c['val_a']} {c['unit_a'] or ''} ({c['time_a'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_a']}\"")
            print(f"  Source B: {c['doc_b']} (Pg {c['page_b']}) => {c['attr_b']}: {c['val_b']} {c['unit_b'] or ''} ({c['time_b'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_b']}\"")
            print(f"  System Reasoning: {c['reasoning']}")
    else:
        print("  None found in sample.")

    print("\n--- CASE 2: GENUINE OR LIKELY CONTRADICTION ---")
    if contradict:
        for idx, c in enumerate(contradict[:2]):
            print(f"\n[Contradiction #{idx+1}]")
            print(f"  Source A: {c['doc_a']} (Pg {c['page_a']}) => {c['attr_a']}: {c['val_a']} {c['unit_a'] or ''} ({c['time_a'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_a']}\"")
            print(f"  Source B: {c['doc_b']} (Pg {c['page_b']}) => {c['attr_b']}: {c['val_b']} {c['unit_b'] or ''} ({c['time_b'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_b']}\"")
            print(f"  System Reasoning: {c['reasoning']}")
    else:
        print("  No direct contradictions found in candidate pairs.")

    print("\n--- CASE 3: APPARENT CONTRADICTION RECONCILED BY CONTEXT ---")
    if reconciled:
        for idx, c in enumerate(reconciled[:2]):
            print(f"\n[Reconciliation #{idx+1}] (Context Category: {c['reconciliation_category']})")
            print(f"  Source A: {c['doc_a']} (Pg {c['page_a']}) => {c['attr_a']}: {c['val_a']} {c['unit_a'] or ''} ({c['time_a'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_a']}\"")
            print(f"  Source B: {c['doc_b']} (Pg {c['page_b']}) => {c['attr_b']}: {c['val_b']} {c['unit_b'] or ''} ({c['time_b'] or 'N/A'})")
            print(f"    Quote: \"{c['quote_b']}\"")
            print(f"  System Reasoning: {c['reasoning']}")
    else:
        print("  None found in sample.")

    print("\n--- CASE 4: REAL EXTRACTION / REASONING FAILURE ANALYSIS ---")
    print("  Title: Multi-Year Column Header Bleed in Compressed Financial Excerpts")
    print("  Category: Ingestion & Spatial Binding Failure")
    print("  Description: When extracting tables from PDF excerpts without explicit gridlines, columns representing different fiscal vintages (e.g., FY22 vs FY23 vs FY24) merge into single text blocks. The LLM extracts the correct metric name and quote, but misattributes the temporal vintage.")
    print("  Root Cause: Pure character-stream extraction loses horizontal 2D layout semantics.")
    print("  Mitigation Implemented: Integrated pdfplumber's extract_tables() to serialize structured Markdown tables with column delimiters (|) and added quote grounding verification.")

if __name__ == "__main__":
    run_real_dataset_pipeline()
