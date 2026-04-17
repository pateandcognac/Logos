# src/hook_routines/workbench.py

import logos

def upsert(name: str, code: str, ltl: int = 1, location: str = 'ephemera'):
    """
    Add or update a snippet on the workbench.
    
    Args:
        name: Unique key for this snippet.
        code: The Python string to execute.
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
                "Example Usage:\n"
                "# I need to temporarily [search through some docs|crop/zoom/view an image|monitor a changing var|etc], but don't want to blow up my palimpsest. I'll put it on the auto-expiring workbench.\n"
                """workbench.upsert(name="doc_review", code="logos.files.show(path='docs.md', pattern='some regex')", ltl=2, location='arche|ephemera')""")
        
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
            # Execute in global scope so it can see 'logos', etc.
            exec(item['code'], env_globals())
            print()
        except Exception as e:
            print(f"Workbench Error in '{name}': {e}")
        
        # Decrement LTL (only once per loop, even if in both hooks—but we've split them now)
        item['ltl'] -= 1
        if item['ltl'] <= 0:
            to_remove.append(name)

    # Cleanup the main state dict
    for name in to_remove:
        del bench[name]