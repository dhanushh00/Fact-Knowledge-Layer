# Fact Knowledge Layer: Cross-Document Verification & Reconciliation Engine

> An autonomous, domain-agnostic fact extraction, evidence grounding, and cross-document reasoning engine built for the Superjoin VIT 2026 Engineering Intern Hiring Assignment.

---

## 1. Setup and Run Instructions

### Prerequisites
- Python 3.10+ (tested on Python 3.13)
- Google Gemini API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dhanushh00/Fact-Knowledge-Layer.git
   cd Fact-Knowledge-Layer
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your environment variables:**
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY="your_actual_gemini_api_key_here"
   ```

5. **Start the application:**
   ```bash
   uvicorn main:app --reload --port 8080
   ```
   Open your browser at: **`http://localhost:8080`**

### Running the End-to-End Verification Pipeline
To ingest starter PDFs, extract grounded facts, run cross-document reasoning, and display the four demonstrated cases automatically:
```bash
python -u run_pipeline.py
```

---

## 2. Video Demo
- **Demo Video Link:** `[Insert your YouTube / Loom / Google Drive link here]` *(≤ 3 minutes)*
- **Demo Script Summary:**
  1. `0:00 - 0:45`: System overview & live UI at `http://localhost:8000`. Drag-and-drop a new PDF to demonstrate generalizability and page-grounded extraction with verbatim quotes.
  2. `0:45 - 1:30`: Triggering candidate linking and cross-document reasoning across multi-vintage documents.
  3. `1:30 - 2:40`: Walkthrough of the **Four Demonstrated Cases**:
     - **Case 1 (Corroboration):** PIN codes / operational reach corroborated across Delhivery Annual Report & Q4 presentation.
     - **Case 2 (Contradiction):** Genuine or vintage-level conflict surfaced under identical scopes.
     - **Case 3 (Contextual Reconciliation):** Revenue & GDP figure variations explained by time vintage (FY22 vs FY24) and measurement methodology (provisional vs actual).
     - **Case 4 (Failure Analysis):** Root cause breakdown of table header bleed in borderless financial statements and the spatial delimiter mitigation.
  4. `2:40 - 3:00`: Quick review of SQLite schema, API endpoints (`/facts`, `/comparisons`, `/demo-cases`), and incremental caching.

---

## 3. Approach

### A. Architectural Overview
The Fact Knowledge Layer decouples ingestion, extraction, candidate linking, and cross-document reasoning into a robust pipeline:

```
PDF Document ──► [ Ingestion Layer ] ──► Extracts Text & Markdown Tables with Page Numbers
                       │
                       ▼
                 [ Fact Extractor ] ──► Gemini 3.6 Flash + Pydantic Structured Schema
                       │                 (Validates verbatim source quote grounding)
                       ▼
                 [( SQLite DB )] ─────► Stores atomic facts with document metadata
                       │
                       ▼
                 [ Candidate Linker ] ──► Token Jaccard + Metric Domain Clustering
                       │                  (Prunes O(N²) search space down to high-signal pairs)
                       ▼
                 [ Reasoner Engine ] ──► Classifies Corroborate | Contradict | Reconcile
                       │                 (Explains reasoning referencing both source quotes)
                       ▼
                 [ Interactive UI ] ──► Modern Web Dashboard & RESTful Endpoints
```

### B. Ingestion & Grounding Layer (`ingestion.py`)
- Extracts raw page text while using `pdfplumber.extract_tables()` to format multi-column financial statements into structured markdown tables (`| col1 | col2 |`).
- Maintains physical 1-indexed page coordinates for undeniable evidence verification.
- Supports selective page indexing (`page_numbers` or `max_pages`) for efficient large-document handling.

### C. Domain-Agnostic Fact Extraction (`extractor.py`)
- Strictly domain-independent: uses Gemini 3.6 Flash configured with deterministic temperature (`0.0`) and structured output enforcement via Pydantic (`FactExtractionResponse`).
- Extracted schema:
  - `entity`: Subject derived from context (e.g. `Delhivery Limited`, `Indian Economy`).
  - `attribute`: Specific metric or semantic claim (e.g. `Revenue from operations`, `Real GDP growth rate`).
  - `value`: Quantitative or qualitative assertion (`7,225`, `8.2%`, `17,000+`).
  - `unit`: Measurement scale (`INR Crore`, `%`, `PIN codes`).
  - `time_period`: Temporal scope (`FY24`, `Q4 FY24`, `2021-22`).
  - `exact_quote`: Exact verbatim sentence copied from the document text.
  - `page_number` & `document_name`: Source citations.
- **Hallucination Prevention:** Substring verification verifies that the quote string exists within the page content before persistence.

### D. Candidate Linking & Search Pruning (`linker.py`)
- **The $O(N^2)$ Challenge:** Evaluating all pairwise combinations between two 60-fact documents requires 3,600 LLM calls, causing immediate rate limit exhaustion.
- **Solution:** A fast heuristic candidate linker that scores pairs using:
  - Alphanumeric token Jaccard similarity (excluding domain stopwords).
  - Metric cluster alignment (revenue/income, inflation/CPI, volume/tonnage, GDP/growth).
  - Entity compatibility and unit alignment.
  - Prunes thousands of irrelevant comparisons down to 30–40 high-probability candidate pairs.

### E. Cross-Document Reasoning Layer (`reasoner.py`)
Evaluates candidate pairs across documents and classifies their relationship:
1. **Corroborate:** Facts agree on the metric, value, and scope across documents even when expressed in different phrasing or vocabulary.
2. **Contradict:** Incompatible factual conflict under identical scope and time period without explanatory context.
3. **Reconcile with Context:** Apparent numeric discrepancy explained by:
   - *Temporal Differences:* Different fiscal periods (e.g., FY22 vs FY24, or full-year vs quarterly).
   - *Scope of Measurement:* Standalone vs Consolidated financial statements; Express Parcel vs Total Logistics.
   - *Unit Scaling:* Millions vs Crores vs Percentages.
   - *Methodology / Revisions:* Real GDP (constant prices) vs Nominal GDP (current prices); Provisional vs Revised estimates.
- Generates transparent natural language explanations citing exact quotes, numbers, and dates from both documents.

### F. Storage & Brownie Points (`database.py`)
- **Zero-Dependency SQLite:** Self-contained relational database (`facts.db`) storing `documents`, `facts`, and `comparisons`.
- **Incremental Ingestion (Brownie Point):** Adding a new document indexes its facts and runs comparisons against existing stored facts without re-extracting or re-evaluating historical documents.

---

## 4. Limitations and Next Steps

### Limitations
1. **Complex Merged Table Headers:** Heavily nested sub-headers in borderless financial tables can occasionally have horizontal column alignment bleed into adjacent periods.
2. **LLM API Rate Limits:** Sequential calls on free-tier API keys require pacing (`time.sleep`) and exponential backoff to respect RPM limits.
3. **Candidate Filtering Precision:** Pure lexical and metric-cluster filtering may miss subtle cross-lingual or highly abstract semantic contradictions that share zero common keywords.

### Next Steps
1. **Dense Vector Embeddings (Hybrid Retrieval):** Integrate dense embeddings (e.g. `text-embedding-004`) alongside token clustering to capture abstract semantic similarities.
2. **Multi-Hop Fact Graph:** Build an entity graph allowing transitive reasoning across 3+ documents (e.g., Document A implies B, Document B contradicts C).
3. **OCR Integration for Scanned Documents:** Add Tesseract / Surya OCR fallback for scanned, image-only PDFs.

---

## 5. Additional Notes
- **Security & Privacy:** `.gitignore` strictly protects `.env` (API keys), SQLite databases, and virtual environment folders. Credentials are never committed to version control.
- **Explainability First:** In accordance with assignment goals, the system emphasizes clear, auditable reasoning and verifiable verbatim citations over black-box complexity.
