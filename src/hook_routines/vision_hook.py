# Logos/src/hook_routines/vision_hook.py

"""
The Eyes of the Pneuma. 👁️

This hook routine executes the camera capture plan defined in `logos.config.vision`.
It handles simple single-shot captures as well as multi-step pan/tilt sequences.

It populates the global Python environment with `CaptureResult` objects (or lists of them)
based on the `var_name` configured in the YAML.
"""

import logos
import time

def run():
    # Iterate through the configured capture hooks
    for config in logos.config.vision.hook_captures:
        # 1. Skip if not active
        if not config.get('active', True):
            continue

        source = config['source']
        var_name = config.get('var_name')
        view = config.get('view', False)
        
        # 1.5 Skip if chora
        if source =='chora':
            continue

        # 2. Handle Pan/Tilt Sequences (Special Case)
        if source == 'pan_tilt' and 'pt_sequence' in config:
            sequence_results = []
            
            # Execute each step in the sequence
            for step in config['pt_sequence']:
                # Move head
                pan = step.get('pan', 0)
                tilt = step.get('tilt', 0)
                logos.pantilt.move(pan, tilt, verbosity=logos.Verbosity.SILENT)
                
                # Wait briefly for servo to settle/motion blur to clear
                time.sleep(0.35) 
                
                # Capture
                res = step.get('resolution', config.get('resolution'))
                result = logos.vision.capture(
                    source=source, 
                    resolution=res, 
                    view=view,
                    # We add a tiny metadata tag so I know which step this was
                    meta={'pt_seq_step': f"{pan}_{tilt}"}
                )
                
                if result:
                    sequence_results.append(result)

            # Assign the list of results to the global variable
            if var_name:
                globals()[var_name] = sequence_results
                
            # Return head to home after sequence? Optional, but good manners.
            logos.pantilt.home(verbosity=logos.Verbosity.SILENT)

        # 3. Handle Standard Single Capture
        else:
            # For Astra, respect feed configuration
            astra_feeds = tuple(config.get('astra_feeds', ['rgb'])) if source == 'astra' else None
            
            result = logos.vision.capture(
                source=source,
                resolution=config.get('resolution'),
                astra_feeds=astra_feeds,
                view=view
            )
            
            if var_name and result:
                globals()[var_name] = result
