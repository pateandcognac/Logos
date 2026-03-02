# Logos/src/hooks/memory_manager.py

import logos
import json

def run_policy_check():
    """
    The core logic for the automated memory manager. It reads the io_buffer,
    applies the policy from logos.config, and triggers summarization if needed.
    """
    policy = logos.config.memory_policy
    if not policy.enabled:
        return

    # 1. Check Preconditions
    try:
        with open(logos.memory.BUFFER_FILE, 'r') as f:
            messages = [json.loads(line) for line in f]
    except FileNotFoundError:
        return # No buffer file yet, nothing to do.

    total_tokens = sum(msg.get('token_count', 0) for msg in messages)

    if len(messages) <= policy.max_cells and total_tokens <= policy.max_tokens:
        return # Below thresholds, nothing to do.

    print("Memory Manager: Thresholds exceeded, beginning analysis.")

    # --- SINGLE PASS ANALYSIS ---
    cells_to_summarize = set()
    
    # 2a. Identify and Score Candidates (Oldest/Largest)
    tail = max(policy.untouchable_tail, 0)
    summarizable_part = messages[:-tail] if tail > 0 else messages

    if len(summarizable_part) > 0:
        candidates = []
        py_map = {} # { msg_id: cell_index }
        
        for i, msg in enumerate(summarizable_part):
            if msg.get('type') == 'me':
                py_map[msg['id']] = i
            if msg.get('type') in policy.summarizable_types:
                candidates.append({'cell_index': i, 'msg': msg, 'paired': False})

        if not candidates:
            print("Memory Manager: No eligible cells to summarize.")
            return

        for cand in candidates:
            if cand['msg'].get('type') == 'py_result' and cand['msg'].get('filename') in py_map:
                me_index = py_map[cand['msg']['filename']]
                # Find the corresponding 'me' candidate and mark both as paired
                for me_cand in candidates:
                    if me_cand['cell_index'] == me_index:
                        me_cand['paired'] = True
                        cand['paired'] = True
                        break
        
        max_token_count = max(c['msg'].get('token_count', 1) for c in candidates) or 1
        for cand in candidates:
            norm_age = cand['cell_index'] / len(summarizable_part)
            norm_size = cand['msg'].get('token_count', 0) / max_token_count
            score = (norm_age * policy.age_weight) + (norm_size * policy.size_weight)
            if cand['paired']: score += 0.1 # Prioritize paired actions
            cand['score'] = score
            
        candidates.sort(key=lambda c: c['score'], reverse=True)

        # Select top candidates based on policy
        selected_units = 0
        temp_cells = set()
        for cand in candidates:
            if cand['cell_index'] in temp_cells: continue
            
            temp_cells.add(cand['cell_index'])
            if cand['paired']:
                me_index = py_map.get(cand['msg'].get('filename'))
                if me_index is not None: temp_cells.add(me_index)
            
            selected_units += 1
            if selected_units >= policy.min_cells_to_summarize:
                break
        cells_to_summarize.update(temp_cells)

    # 2b. Identify Contiguous Summaries for Recursion
    contiguous_summaries = []
    for i, msg in enumerate(messages):
        if msg.get('type') == 'summary':
            contiguous_summaries.append(i)
        else:
            if len(contiguous_summaries) > policy.max_contiguous_summaries:
                cells_to_summarize.update(contiguous_summaries)
            contiguous_summaries = []
    # Check after the loop for a trailing block of summaries
    if len(contiguous_summaries) > policy.max_contiguous_summaries:
        cells_to_summarize.update(contiguous_summaries)

    # 3. Execute Summarization
    if cells_to_summarize:
        final_cell_list = sorted(list(cells_to_summarize))
        print(f"Memory Manager: Submitting {len(final_cell_list)} cells for summarization.")
        logos.memory.summarize_io_buffer(cell_indices=final_cell_list)
    else:
        print("Memory Manager: Analysis complete, no action needed.")