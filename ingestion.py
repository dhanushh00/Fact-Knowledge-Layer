import pdfplumber
from typing import List, Dict, Any, Optional

def extract_pages(
    pdf_path: str,
    max_pages: Optional[int] = None,
    page_numbers: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    Extracts text and tabular content page-by-page from a PDF using pdfplumber.
    Preserves exact 1-indexed page numbers for strict source grounding.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        
        target_indices = []
        if page_numbers:
            # Convert 1-indexed to 0-indexed and filter valid pages
            target_indices = [p - 1 for p in page_numbers if 1 <= p <= total_pages]
        else:
            limit = min(max_pages, total_pages) if max_pages else total_pages
            target_indices = list(range(limit))

        for idx in target_indices:
            page = pdf.pages[idx]
            text = page.extract_text() or ""
            
            # Extract tables and format them cleanly as readable markdown/tabular text
            tables = page.extract_tables() or []
            table_chunks = []
            for table in tables:
                clean_rows = []
                for row in table:
                    if row and any(cell is not None and str(cell).strip() for cell in row):
                        clean_row = [str(cell or "").strip().replace("\n", " ") for cell in row]
                        clean_rows.append(" | ".join(clean_row))
                if clean_rows:
                    header_sep = " | ".join(["---"] * len(clean_rows[0].split(" | ")))
                    clean_rows.insert(1, header_sep)
                    table_chunks.append("\n".join(clean_rows))
            
            combined_content = text.strip()
            if table_chunks:
                combined_content += "\n\n[STRUCTURED TABLES]\n" + "\n\n".join(table_chunks)

            if combined_content.strip():
                pages.append({
                    "page_number": idx + 1,
                    "total_pages": total_pages,
                    "text": combined_content
                })
    return pages