# src/hook_routines/workbench.py

import logos

def upsert(name: str, code: str, ltl: int = 1, location: str = 'ephemera'):
    """
    Add or update a snippet on the workbench.
    
    Args:
        name: Unique key for this snippet.
        code: The Python string to execute. Remember to use print() inside!
        ltl: Loops To Live.
        location: 'arche' (top of context) or 'ephemera' (bottom).
    """
    bench = logos.hooks.state.setdefault('workbench', {})
    bench[name] = {
        'code': code, 
        'ltl': ltl, 
        'location': location.lower()
    }
    print(f"Workbench: Upserted '{name}' in {location} for {ltl} loops.")

def run(location: str, env_globals: dict): 
    """Called by the hook system. Location is 'arche' or 'ephemera'."""
    bench = logos.hooks.state.get('workbench', {})
    if not bench:
        usage = (f"\n--- Context Workbench ({location}) ---\n"
                "No content.\n---\n"
                "Use case: When I want to view some token heavy context, but don't want it to clutter up my palimpsest long-term, I can put it on this auto-expiring workbench hook for a number of loops-to-live.\n"
                """Example: `hook_routines.workbench.upsert(name="doc_review", code="logos.files.show(path='docs.md', pattern='some regex')", ltl=2)`""")
        
        print(usage)
        return 

    # Filter for snippets designated for this specific hook location
    active_snippets = {k: v for k, v in bench.items() if v.get('location') == location}
     
    if not active_snippets:
        return

    print(f"\n--- Context Workbench ({location}) ---")
    to_remove = []
    
    for name, item in active_snippets.items():
        print(f"--- [ {name} ] (ltl: {item['ltl']}) ---")
        try:
            # Execute in global scope without calling the dict as a function
            exec(item['code'], env_globals)
        except Exception as e:
            print(f"Workbench Error in '{name}': {e}")
        print() # add a trailing newline for neatness
        
        # Decrement LTL
        item['ltl'] -= 1
        if item['ltl'] <= 0:
            to_remove.append(name)

    # Cleanup the main state dict
    for name in to_remove:
        del bench[name]