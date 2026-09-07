import os
import shutil
import json
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Query, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from database import (
    init_db, store_facts, fetch_all_facts, store_comparison,
    fetch_all_comparisons, comparison_exists, record_document,
    fetch_documents, clear_all
)
from ingestion import extract_pages
from extractor import extract_facts_from_page
from linker import find_candidate_pairs
from reasoner import compare_facts
from models import ExtractedFact

app = FastAPI(
    title="Fact Knowledge Layer",
    description="Automated Fact Extraction, Evidence Grounding, and Cross-Document Reconciliation"
)

DATA_DIR = "uploads"
STATIC_DIR = "static"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

init_db()

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Fact Knowledge Layer API is running. Check /docs for Swagger.</h1>"

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    max_pages: Optional[int] = Form(None),
    pages: Optional[str] = Form(None)
):
    """
    Upload a PDF, extract text & tables with page grounding, and extract structured facts.
    Supports optional page filtering (max_pages or comma-separated page numbers).
    """
    dest_path = os.path.join(DATA_DIR, file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    page_numbers = None
    if pages and pages.strip():
        try:
            page_numbers = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
        except Exception:
            page_numbers = None

    # Default to 3 pages for rapid interactive responses and avoiding 100-page rate limit lockups
    effective_max = max_pages if (max_pages is not None and max_pages > 0) else (3 if not page_numbers else None)

    extracted_pages = extract_pages(dest_path, max_pages=effective_max, page_numbers=page_numbers)
    total_doc_pages = extracted_pages[0]["total_pages"] if extracted_pages else 0
    
    all_facts = []
    for p in extracted_pages:
        facts = extract_facts_from_page(file.filename, p["page_number"], p["text"])
        all_facts.extend(facts)
        
    inserted = store_facts(all_facts)
    record_document(file.filename, total_doc_pages, len(extracted_pages), inserted)
    
    return {
        "filename": file.filename,
        "total_pdf_pages": total_doc_pages,
        "pages_processed": len(extracted_pages),
        "facts_extracted": inserted
    }

@app.get("/documents")
def get_documents():
    return {"documents": fetch_documents()}

@app.get("/facts")
def get_facts(
    document: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return {"facts": fetch_all_facts(document_name=document, search=search)}

@app.post("/run-comparisons")
def run_comparisons(max_candidates: int = Query(5)):
    """
    Discovers top candidate cross-document fact pairs and evaluates them using LLM reasoning.
    Processes in batches of 5 to provide immediate 5-second interactive responses without HTTP timeouts.
    """
    raw_facts = fetch_all_facts()
    fact_objs = [(r["id"], ExtractedFact(**json.loads(r["raw_json"]))) for r in raw_facts]
    
    # 1. Candidate Linking (Attribute similarity & Domain clusters)
    # Filter candidates that haven't been evaluated yet
    all_candidates = find_candidate_pairs(fact_objs, min_score=0.25, max_candidates=50)
    unseen_candidates = [
        c for c in all_candidates if not comparison_exists(c[0], c[2])
    ][:min(max_candidates, 8)]
    
    new_comparisons = 0
    skipped_existing = 0
    
    for id_a, fact_a, id_b, fact_b, score in unseen_candidates:
        result = compare_facts(fact_a, fact_b)
        if result:
            store_comparison(id_a, id_b, result)
            new_comparisons += 1

    return {
        "status": "complete",
        "candidate_pairs_evaluated": len(unseen_candidates),
        "new_comparisons_stored": new_comparisons,
        "total_comparisons": len(fetch_all_comparisons())
    }

@app.get("/comparisons")
def get_comparisons(relationship: Optional[str] = Query(None)):
    return {"comparisons": fetch_all_comparisons(relationship=relationship)}

@app.get("/demo-cases")
def demo_cases():
    """
    Returns the four required demonstration cases for evaluation.
    """
    comps = fetch_all_comparisons()
    corroborations = [c for c in comps if c["relationship"] == "corroborate"]
    contradictions = [c for c in comps if c["relationship"] == "contradict"]
    reconciliations = [c for c in comps if c["relationship"] == "reconcile_with_context"]
    
    return {
        "case_1_corroborated": corroborations[0] if corroborations else {
            "status": "pending",
            "instruction": "Upload at least two overlapping PDFs and call POST /run-comparisons"
        },
        "case_2_contradiction": contradictions[0] if contradictions else {
            "status": "pending",
            "instruction": "Upload at least two overlapping PDFs and call POST /run-comparisons"
        },
        "case_3_reconciliation": reconciliations[0] if reconciliations else {
            "status": "pending",
            "instruction": "Upload at least two overlapping PDFs and call POST /run-comparisons"
        },
        "case_4_failure_case": {
            "title": "Header-Data Misalignment in Multi-Period Financial Tables",
            "category": "Extraction & Semantic Binding Failure",
            "description": "In dense excerpted financial tables lacking vertical column lines, line item metrics spanning multiple quarters/years (e.g. FY23 vs FY24 vs Q4 FY24) can have values shifted to adjacent column periods during plain text extraction.",
            "why_it_happened": "Without structural spatial bounding boxes, tabular text columns merge into a single text stream, causing the LLM to misattribute full-year annual figures to single-quarter line items.",
            "handling_and_mitigation": "1. Upgraded pdfplumber ingestion to run extract_tables() and inject structured markdown/TSV grids into the page payload. 2. Added verbatim quote validation: rejecting any fact whose quote cannot be strictly matched to the raw page text."
        }
    }

@app.post("/reset")
def reset_knowledge_layer():
    clear_all()
    return {"status": "success", "message": "Knowledge layer database reset."}