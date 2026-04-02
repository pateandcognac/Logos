# src/hook_routines/workbench.py

import logos

def add(name: str, code: str, ltl: int = 1):
    """
    Helper function for Logos to put a snippet on the context workbench.
    
    Usage in a <py> block:
        import hook_routines.workbench as workbench
        workbench.add("check_docs", "print(logos.files.show('docs.md'))", ltl=2)
    """
    # Initialize workbench state if it doesn't exist
    bench = logos.hooks.state.setdefault('workbench', {})
    bench[name] = {'code': code, 'ltl': ltl}
    print(f"Workbench: Added '{name}' for the next {ltl} loop(s).")

def run(location: str):
    """
    The context workbench hook execution logic. Can be placed in both arche and ephemera.
    """
    bench = logos.hooks.state.get('workbench', {})
    if not bench:
        usage = (f"\n=== Context Workbench ({location}) ===\n"
                "Runs a small snippet of context emitting `code` for `ltl` loops-to-live. Enables temporary viewing of large docs, changing variables, etc. without cluttering my palimpsest.\n"
                "Example usage:\n"
                """workbench.add(name="perusing_docs", code="logos.files.show(path='docs.md', pattern='some regex')", ltl=2)\n""")
        print(usage)
        return 

    print(f"\n=== Context Workbench ({location}) ===")
    to_remove = []
    
    for name, item in bench.items():
        print(f"--- [ {name} ] (Loops remaining: {item['ltl']}) ---")
        try:
            # We execute the code in the global namespace so it has access
            # to my persistent variables, and we capture anything it prints.
            # I must remember to use print() in my workbench code to see the output!
            exec(item['code'], globals())
        except Exception as e:
            print(f"Workbench Error in '{name}': {e}")
        
        # Decrement Loops To Live
        item['ltl'] -= 1
        if item['ltl'] <= 0:
            to_remove.append(name)
            
    print("=========================\n")
    
    # Cleanup expired items
    for name in to_remove:
        del bench[name]