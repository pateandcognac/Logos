import json
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple

import logos
from logos.core import verbosity, Verbosity
from logos.memory import rag

def _extract_query(cell_type: str, content: str) -> str:
    """Extract semantic intent from a palimpsest cell based on its type."""
    if cell_type in ("human", "human_stt"):
        return content.strip()
        
    elif cell_type in ("py_result", "async_py"):
        # Look for the stderr marker to grab tracebacks
        if "# stderr\n" in content:
            error_text = content.split("# stderr\n")[-1].strip()
            # If it's a massive traceback, just grab the last 500 chars 
            # so we don't overwhelm the embedding model, the actual error is at the bottom anyway.
            return error_text[-500:] if len(error_text) > 500 else error_text
            
    elif cell_type == "me":
        # Subconscious priming: Extract Logos's own internal thoughts/comments
        comments = re.findall(r'#\s*(.*)', content)
        if comments:
            return " ".join(comments)
            
    return ""

def _fetch_and_penalize(query_func, queries: List[Tuple[int, str]], max_results: int, penalty: float) -> List[Dict]:
    """Runs a specific RAG function across multiple queries, merging and penalizing by age."""
    if max_results <= 0:
        return []
        
    merged_results = []
    seen_ids = set()
    
    for age, query_text in queries:
        try:
            # We bypass the pre-formatted 'context' string the RAG functions usually return
            # because we want to manually merge the raw 'results' dictionaries.
            response = query_func(query_text, n_results=max_results)
            
            for res in response.get("results", []):
                doc_id = res.get("id")
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    # Apply temporal penalty to distance (Chroma L2 distance: lower is better)
                    res["distance"] += (age * penalty)
                    merged_results.append(res)
        except Exception:
            # Fail silently on RAG errors so we don't crash the hook loop
            pass
            
    # Sort by penalized distance and truncate to requested max
    merged_results.sort(key=lambda x: x.get("distance", 999.0))
    return merged_results[:max_results]

def run():
    """Main entry point for the auto_rag hook."""
    cfg = logos.config.merged.get("auto_rag_hook", {})
    lookback = cfg.get("lookback_cells", 2)
    limits = cfg.get("n_results", {})
    penalty = cfg.get("penalty_per_cell", 0.15)
    
    buffer_file = logos.memory.BUFFER_FILE
    if not buffer_file.exists():
        return
        
    # 1. Read the latest cells from io_buffer
    cells = []
    try:
        with open(buffer_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
            for line in lines[-lookback:]:
                cells.append(json.loads(line))
    except Exception:
        return
        
    # Reverse to process newest (age=0) to oldest (age=lookback-1)
    cells.reverse()
    
    # 2. Extract actionable queries
    # We maintain a list of (age, query_text) to apply distance penalties later
    queries: List[Tuple[int, str]] = []
    for age, cell in enumerate(cells):
        # Handle variations in JSONL schema (type/role, content/text)
        c_type = cell.get("type", cell.get("role", ""))
        c_text = cell.get("content", cell.get("text", ""))
        
        query_text = _extract_query(c_type, c_text)
        if query_text:
            queries.append((age, query_text))
            
    if not queries:
        return
        
    # 3. Retrieve and Merge (Silently, so memory calls don't spam stdout)
    with verbosity(Verbosity.SILENT):
        api_res = _fetch_and_penalize(rag.search_api_help, queries, limits.get("api_refs", 3), penalty)
        ex_res = _fetch_and_penalize(rag.search_examples, queries, limits.get("examples", 1), penalty)
        sum_res = _fetch_and_penalize(rag.search_summaries, queries, limits.get("summaries", 0), penalty)
        fact_res = _fetch_and_penalize(rag.recall_collective_facts, queries, limits.get("facts", 5), penalty)
        
    # 4. Format the output to stdout (which the hook system captures)
    has_output = any([api_res, ex_res, sum_res, fact_res])
    if not has_output:
        return
        
    print("\n--- Subconscious Context Retrieval ---")
    
    if api_res:
        print("\n[ Relevant API Reference ]")
        for r in api_res:
            print(f"- {r['metadata'].get('symbol', 'Unknown')}:")
            print(f"  {r['document'].strip().replace(chr(10), chr(10)+'  ')}")
            
    if ex_res:
        print("\n[ Curated Example ]")
        for r in ex_res:
            # Print the example code, but indented to keep it visually contained
            print(f"  {r['document'].strip().replace(chr(10), chr(10)+'  ')}")
            
    if sum_res:
        print("\n[ Recalled Experiences ]")
        for r in sum_res:
            time_ago = r['metadata'].get('relative_time', '')
            prefix = f"({time_ago}) " if time_ago else ""
            print(f"- {prefix}{r['document'].strip()}")
            
    if fact_res:
        print("\n[ Known Facts ]")
        for r in fact_res:
            print(f"- {r['document'].strip()}")