# Logos/src/phantasmata/couch.py
"""
A minimalist, modern virtual couch.
Kwargs:
    color (list): RGB float array. Default [0.3, 0.3, 0.4] (charcoal).
"""

def build(builder, **kwargs):
    color = kwargs.get('color', [0.3, 0.3, 0.4])
    
    # Base dimensions
    w, d, h = 2.0, 0.8, 0.4
    
    # Build parts around center (0,0,0) for easy symmetry
    base = builder.box(w, d, h, center=[0, 0, 0], color=color)
    backrest = builder.box(w, 0.2, 0.5, center=[0, (d/2)-0.1, h/2 + 0.25], color=color)
    arm_l = builder.box(0.2, d, 0.3, center=[-(w/2)+0.1, 0, h/2 + 0.15], color=color)
    arm_r = builder.box(0.2, d, 0.3, center=[(w/2)-0.1, 0, h/2 + 0.15], color=color)
    
    # Combine
    mesh = builder.union(base, backrest, arm_l, arm_r)
    
    # MAGIC: Push the lowest point of the couch to Z=0
    mesh = builder.snap_to_floor(mesh)
    
    return mesh