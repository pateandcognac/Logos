import logos

workbench = logos.config.merged.get('workbench', {})
files_to_open = workbench.get('files', [])
vars_to_inspect = workbench.get('vars', [])

# todo: what if... instead of files / vars
# execute a one-liner?
# like `print(var=)` or `print(logos.files.show(path: str, max_chars: int = 2000, pattern: Optional[str] = None))`

if files_to_open or vars_to_inspect:
    print("=== 📄 Context Workbench 🛠️ ===")
    
    for f in files_to_open:
        print(f"\n--- File: {f} ---")
        try:
            # If it's an image, view it. If text, show it.
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                print(f'<file path="{f}">Pinned image</file>')
            else:
                logos.files.show(f, max_chars=3000)
        except Exception as e:
            print(f"Could not open {f}: {e}")

    for v in vars_to_inspect:
        print(f"\n--- Variable: {v} ---")
        # globals() carries over in the persistent environment!
        if v in globals():
            val = globals()[v]
            # Print a safe, truncated representation
            print(repr(val)[:1000] + ("..." if len(repr(val)) > 1000 else ""))
        else:
            print(f"Variable '{v}' is not currently in memory.")
