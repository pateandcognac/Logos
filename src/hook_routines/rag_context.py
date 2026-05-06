import json
from pathlib import Path
from typing import Dict, List, Set, Any
import logos
from logos.core import Verbosity
from logos.memory import rag

def _get_implicit_context(lookback: int) -> str:
    """Reads io_buffer.jsonl to find recent human input OR python errors."""
    buffer_path = Path(logos.config.merged.memory_policy.get('buffer_file', 'state/io_buffer.jsonl'))
    if not buffer_path.exists():
        return ""
    
    recent_texts = []
    
    with open(buffer_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in reversed(lines):
        try:
            entry = json.loads(line)
            msg_type = entry.get('type')
            content = entry.get('content', '')
            
            text_to_add = ""
            
            # Normal conversational context
            if msg_type in ['human', 'human_stt']:
                text_to_add = content.strip()
                
            # Auto-debug context: Only grab text after '# stderr\n'
            elif msg_type in ['py_result', 'async_py']:
                if '# stderr\n' in content:
                    text_to_add = content.split('# stderr\n', 1)[-1].strip()
            
            if text_to_add:
                recent_texts.insert(0, text_to_add)
                if len(recent_texts) >= lookback:
                    break
        except Exception:
            continue
            
    return " \n ".join(recent_texts).strip()

def run() -> None:
    cfg = logos.config.merged.get('rag_hook', {})
    if not cfg.get('enabled', False):
        return

    auto_cfg = cfg.get('auto_search', {})
    explicit = cfg.get('explicit_queries', {})
    
    # 1. Gather Queries
    api_queries = explicit.get('api_examples', []).copy()
    summary_queries = explicit.get('summaries', []).copy()
    fact_queries = explicit.get('facts', []).copy()
    
    # If auto-search is on, extract implicit context (human text + stderr)
    if auto_cfg.get('enabled', False):
        context_str = _get_implicit_context(auto_cfg.get('lookback_cells', 2))
        if context_str:
            if auto_cfg.get('include_api'): api_queries.append(context_str)
            if auto_cfg.get('include_summaries'): summary_queries.append(context_str)
            if auto_cfg.get('include_facts'): fact_queries.append(context_str)

    # If no queries at all, print short usage
    if not (api_queries or summary_queries or fact_queries):
        print('To perform a one-loop RAG query: `logos.config.prefs.rag_hook.explicit_queries["api_examples|summaries|facts"].append("My query here.")`')
        return

    # 2. Storage for deduplication (keyed by Chroma ID)
    docs_api: Dict[str, Any] = {}
    docs_examples: Dict[str, Any] = {}
    docs_summaries: Dict[str, Any] = {}
    docs_facts: Dict[str, Any] = {}
    
    max_res = auto_cfg.get('max_results', 3)

    # 3. Execute Searches (Silently to keep logs clean)
    with logos.core.verbosity(Verbosity.SILENT):
        # API & Examples
        for q in set(api_queries): # set() prevents duplicate identical queries
            res = rag.semantic_help(q, n_results=max_res, include_examples=auto_cfg.get('include_examples', True))
            for item in res.get('api_results', []):
                docs_api[item['id']] = item
            for item in res.get('example_results', []):
                docs_examples[item['id']] = item
                
        # Summaries
        for q in set(summary_queries):
            res = rag.search_summaries(q, n_results=max_res)
            for item in res.get('results', []):
                docs_summaries[item['id']] = item
                
        # Facts
        for q in set(fact_queries):
            res = rag.recall_collective_facts(q, n_results=max_res)
            for item in res.get('results', []):
                docs_facts[item['id']] = item

    # 4. Clear explicit queries (Consume-and-clear) so they don't spam next loop
    if explicit.get('api_examples') or explicit.get('summaries') or explicit.get('facts'):
        logos.config.prefs.setdefault('rag_hook', {}).setdefault('explicit_queries', {})
        logos.config.prefs.rag_hook.explicit_queries['api_examples'] = []
        logos.config.prefs.rag_hook.explicit_queries['summaries'] = []
        logos.config.prefs.rag_hook.explicit_queries['facts'] = []
        # No save() here to prevent unnecessary disk thrashing

    # 5. Format Output (Sparse & Clean)
    output = []
    
    if docs_api:
        output.append("### Relevant API Reference")
        for doc in docs_api.values():
            output.append(f"{doc['document']}")
            
    if docs_examples:
        output.append("### Relevant Few-Shot Examples")
        for doc in docs_examples.values():
            output.append(f"--- File: {doc['metadata'].get('filename', 'example')} ---\n{doc['document']}")

    if docs_summaries:
        output.append("### Relevant Past Experiences (Synopses)")
        for doc in docs_summaries.values():
            output.append(f"- [{doc['metadata'].get('relative_time', 'past')}] {doc['document']}")

    if docs_facts:
        output.append("### Relevant Shared Facts")
        for doc in docs_facts.values():
            output.append(f"- [{doc['metadata'].get('relative_time', 'past')}] {doc['document']}")

    if output:
        print("\n--- Semantic RAG Context ---")
        print("\n".join(output))