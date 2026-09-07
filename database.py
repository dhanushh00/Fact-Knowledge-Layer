import sqlite3
import json
from typing import List, Dict, Any, Optional
from models import ExtractedFact, ComparisonResult

DB_PATH = "facts.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE,
                total_pages INTEGER DEFAULT 0,
                processed_pages INTEGER DEFAULT 0,
                fact_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_name TEXT,
                page_number INTEGER,
                entity TEXT,
                attribute TEXT,
                value TEXT,
                unit TEXT,
                time_period TEXT,
                fact_type TEXT,
                exact_quote TEXT,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_a_id INTEGER,
                fact_b_id INTEGER,
                relationship TEXT,
                reconciliation_category TEXT,
                reasoning TEXT,
                confidence REAL,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(fact_a_id, fact_b_id)
            );
        """)
        conn.commit()

def record_document(filename: str, total_pages: int, processed_pages: int, fact_count: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO documents (filename, total_pages, processed_pages, fact_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                total_pages = excluded.total_pages,
                processed_pages = excluded.processed_pages,
                fact_count = excluded.fact_count
        """, (filename, total_pages, processed_pages, fact_count))
        conn.commit()

def fetch_documents() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def store_facts(facts: List[ExtractedFact]) -> int:
    inserted = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for f in facts:
            cursor.execute("""
                INSERT INTO facts (
                    document_name, page_number, entity, attribute, value,
                    unit, time_period, fact_type, exact_quote, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f.document_name, f.page_number, f.entity, f.attribute, str(f.value),
                f.unit, f.time_period, f.fact_type.value, f.exact_quote, f.model_dump_json()
            ))
            inserted += 1
        conn.commit()
    return inserted

def fetch_all_facts(document_name: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        query = "SELECT * FROM facts WHERE 1=1"
        params = []
        if document_name:
            query += " AND document_name = ?"
            params.append(document_name)
        if search:
            query += " AND (attribute LIKE ? OR entity LIKE ? OR exact_quote LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])
        query += " ORDER BY id ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def comparison_exists(fact_a_id: int, fact_b_id: int) -> bool:
    with get_connection() as conn:
        # Check both orientations (a, b) and (b, a)
        row = conn.execute("""
            SELECT id FROM comparisons 
            WHERE (fact_a_id = ? AND fact_b_id = ?) OR (fact_a_id = ? AND fact_b_id = ?)
        """, (fact_a_id, fact_b_id, fact_b_id, fact_a_id)).fetchone()
        return row is not None

def store_comparison(fact_a_id: int, fact_b_id: int, comp: Optional[ComparisonResult]):
    if not comp:
        return
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO comparisons (
                fact_a_id, fact_b_id, relationship, reconciliation_category,
                reasoning, confidence, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            fact_a_id,
            fact_b_id,
            comp.relationship.value,
            comp.reconciliation_category.value,
            comp.reconciliation_reason,
            comp.confidence,
            comp.model_dump_json()
        ))
        conn.commit()

def fetch_all_comparisons(relationship: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        query = """
            SELECT 
                c.id, c.fact_a_id, c.fact_b_id, c.relationship, c.reconciliation_category,
                c.reasoning, c.confidence, c.created_at,
                fa.document_name AS doc_a, fa.page_number AS page_a, fa.entity AS entity_a,
                fa.attribute AS attr_a, fa.value AS val_a, fa.unit AS unit_a,
                fa.time_period AS time_a, fa.exact_quote AS quote_a,
                fb.document_name AS doc_b, fb.page_number AS page_b, fb.entity AS entity_b,
                fb.attribute AS attr_b, fb.value AS val_b, fb.unit AS unit_b,
                fb.time_period AS time_b, fb.exact_quote AS quote_b
            FROM comparisons c
            JOIN facts fa ON c.fact_a_id = fa.id
            JOIN facts fb ON c.fact_b_id = fb.id
        """
        params = []
        if relationship:
            query += " WHERE c.relationship = ?"
            params.append(relationship)
        query += " ORDER BY c.id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def clear_all():
    with get_connection() as conn:
        conn.execute("DELETE FROM comparisons")
        conn.execute("DELETE FROM facts")
        conn.execute("DELETE FROM documents")
        conn.commit()