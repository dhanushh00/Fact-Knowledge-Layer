import re
from typing import List, Tuple, Dict, Any
from models import ExtractedFact

STOP_WORDS = {
    "the", "of", "and", "in", "to", "a", "is", "for", "on", "as", "by", "with",
    "at", "from", "total", "rate", "year", "annual", "report", "growth", "limited"
}

METRIC_CLUSTERS = [
    {"revenue", "sales", "income", "turnover", "topline"},
    {"profit", "ebitda", "margin", "net", "loss", "pat", "pbt"},
    {"gdp", "growth", "economy", "gross", "domestic", "product", "gva"},
    {"inflation", "cpi", "wpi", "price", "headline"},
    {"pincode", "pincodes", "pin", "codes", "reach", "coverage", "districts"},
    {"volume", "shipments", "express", "parcels", "freight", "tonnage"},
    {"director", "board", "management", "kmp", "resignation", "appointment", "ceo"},
    {"debt", "borrowings", "liabilities", "cash", "liquidity", "reserves"},
    {"expenditure", "capex", "capital", "spending", "fiscal", "deficit"}
]

def tokenize(text: str) -> set:
    """Extract meaningful alphanumeric tokens, ignoring common stopwords."""
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}

def compute_similarity(fact_a: ExtractedFact, fact_b: ExtractedFact) -> float:
    """
    Computes a multi-feature similarity score between two facts:
    1. Attribute token Jaccard similarity
    2. Shared domain metric cluster
    3. Entity compatibility
    4. Fact type matching (numerical vs semantic)
    """
    # 1. Attribute tokens
    tokens_a = tokenize(fact_a.attribute)
    tokens_b = tokenize(fact_b.attribute)
    
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    jaccard = len(intersection) / len(union) if union else 0.0

    # 2. Check metric cluster alignment
    cluster_match = False
    for cluster in METRIC_CLUSTERS:
        if (tokens_a & cluster) and (tokens_b & cluster):
            cluster_match = True
            break

    # 3. Unit / Type compatibility bonus
    unit_bonus = 0.0
    if fact_a.unit and fact_b.unit and fact_a.unit.lower() == fact_b.unit.lower():
        unit_bonus = 0.15

    # 4. Entity similarity
    ent_tokens_a = tokenize(fact_a.entity)
    ent_tokens_b = tokenize(fact_b.entity)
    ent_overlap = bool(ent_tokens_a.intersection(ent_tokens_b))
    
    # Calculate composite score
    score = jaccard * 0.5 + (0.3 if cluster_match else 0.0) + (0.1 if ent_overlap else 0.0) + unit_bonus
    return score

def find_candidate_pairs(
    facts: List[Tuple[int, ExtractedFact]],
    min_score: float = 0.25,
    max_candidates: int = 40
) -> List[Tuple[int, ExtractedFact, int, ExtractedFact, float]]:
    """
    Discovers high-probability candidate fact pairs across different documents.
    Prevents O(N^2) LLM API call explosion while surfacing high-signal comparisons.
    """
    candidates = []
    
    for i in range(len(facts)):
        id_a, fact_a = facts[i]
        for j in range(i + 1, len(facts)):
            id_b, fact_b = facts[j]
            
            # Cross-document comparison only
            if fact_a.document_name == fact_b.document_name:
                continue
                
            score = compute_similarity(fact_a, fact_b)
            if score >= min_score:
                candidates.append((id_a, fact_a, id_b, fact_b, score))
                
    # Sort by relevance score descending
    candidates.sort(key=lambda x: x[4], reverse=True)
    return candidates[:max_candidates]
