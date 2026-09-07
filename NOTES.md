# Project Notes & Engineering Log: Fact Knowledge Layer

This document records the architectural decisions, trade-offs, real-world failure cases, and engineering insights developed while building the Fact Knowledge Layer for the Superjoin Engineering Intern Assignment.

---

## 1. Architectural Decisions & Rationale

### A. Generalization Over Hardcoding
- **Principle:** No rules, regexes, schemas, or logic are hardcoded to "Delhivery", "India", "GDP", or specific filenames.
- **Implementation:** The extraction schema (`models.py`) is domain-agnostic:
  - `entity`: dynamically derived from the document context (e.g. company, sovereign state, regulatory body).
  - `attribute`: descriptive metric or semantic state (e.g., 'Revenue from operations', 'Real GDP growth rate').
  - `value`: the reported figure or assertion.
  - `unit`: extracted unit of measurement (e.g. 'INR Crore', '%', 'PIN codes', 'USD Billion').
  - `time_period`: temporal vintage (e.g. 'FY24', 'Q4 FY24', '2021-22', 'Calendar Year 2024').
  - `exact_quote`: verbatim evidence string.
  - `page_number`: physical 1-indexed page.

### B. Grounding and Verbatim Evidence Verification
- **Principle:** Hallucinations or paraphrasing in factual systems undermine trust.
- **Implementation:** 
  - Every extracted fact must contain an `exact_quote` copied verbatim from the PDF source page.
  - The extraction pipeline validates that the quote's alphanumeric sequence actually exists within the extracted page content.

### C. Solving the $O(N^2)$ Candidate Explosion (`linker.py`)
- **Problem:** If Document A has 60 facts and Document B has 60 facts, naive cross-document pairwise comparison requires $60 \times 60 = 3,600$ LLM calls. This would exhaust API rate limits, take hours to complete, and waste significant tokens comparing unrelated metrics (e.g., CEO name vs PIN codes).
- **Solution:** A two-stage candidate retrieval and reasoning architecture:
  1. **Stage 1 (Candidate Linking):** Uses token-level Jaccard similarity, stopword filtering, and thematic metric clustering (e.g. revenue/turnover, inflation/CPI, volumes/parcels, GDP/growth) to score fact pairs across documents.
  2. **Stage 2 (Deep LLM Reasoning):** Only candidate pairs exceeding the similarity threshold ($\ge 0.25$) are evaluated by Gemini 3.6 Flash. This reduces candidate comparisons from thousands down to 30–40 high-signal pairs.

### D. Cross-Document Reasoning Taxonomy (`reasoner.py`)
- **Corroborate:** Both documents affirm the same factual claim under the same scope and vintage, even if phrased differently (e.g., "17,000+ PIN codes" vs "covers over 17,000 postal codes").
- **Contradict:** Genuine, incompatible conflict under identical scope, entity, and time period without any contextual explanation.
- **Reconcile with Context:** Apparent numeric discrepancy explained by:
  - *Time Period:* e.g., FY22 revenue (Rs 4,911 Cr) vs FY24 revenue (Rs 7,225 Cr).
  - *Scope of Measurement:* e.g., Standalone vs Consolidated; Express Parcel vs Total Logistics.
  - *Unit Scaling:* e.g., Million vs Crore; USD vs INR.
  - *Methodology / Revisions:* e.g., Real GDP (constant prices) vs Nominal GDP (current prices); Advance Estimates vs Revised Estimates.

---

## 2. Trade-offs & Limitations

1. **Table Ingestion in Complex Layouts:**
   - Excerpted PDFs often contain dense multi-period tables lacking explicit vertical cell borders.
   - Using `pdfplumber` with table extraction preserves markdown/TSV structures, but heavily nested sub-headers can occasionally merge across columns.
2. **Rate Limits & API Pacing:**
   - Free/tier-1 LLM endpoints enforce request-per-minute (RPM) quotas.
   - Pacing (`time.sleep`) and exponential backoff retry handlers were added to prevent 429 errors from halting ingestion.
3. **Candidate Filtering Precision vs. Recall:**
   - A high candidate threshold prunes irrelevant pairs but might miss subtle semantic relationships. Composite scoring (token overlap + metric category + entity compatibility) strikes a practical balance.

---

## 3. Real Failures Encountered & Mitigations (Case 4)

- **Failure Discovered:** *Multi-Year Column Header Bleed in Compressed Financial Excerpts*
- **Observed Behavior:** When parsing PDF pages containing multi-column quarterly/annual tables without explicit borders, raw text extraction collapsed columns into a single line stream. The model correctly extracted the metric name and quote, but bound the wrong fiscal vintage (attributing full-year annual values to single quarters).
- **Root Cause:** Character-stream extraction strips horizontal 2D spatial layout.
- **Mitigation Implemented:**
  1. Integrated `pdfplumber.extract_tables()` to detect grid boundaries and format tables with markdown pipe (`|`) delimiters.
  2. Added strict quote substring verification: facts with hallucinated or unverified quotes are rejected.
  3. Added explicit system prompt instructions requiring the LLM to inspect structured table headers before assigning temporal vintage.

---

## 4. Next Steps & Brownie Points

- **Incremental Ingestion:** Already implemented! When a new document is added, it is indexed and compared against existing database facts without re-running older documents.
- **Page Sampling / Selective Ingestion:** Implemented via optional `max_pages` or `pages` query parameters in `/upload`.
- **Vector Search Hybrid:** Incorporating dense embeddings (e.g. `text-embedding-004`) alongside token/attribute clustering for multilingual or cross-lingual candidate linking.
