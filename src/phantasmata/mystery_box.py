
def build(builder, **kwargs):
    # A 30cm cube
    mesh = builder.box(0.3, 0.3, 0.3, center=[0,0,0], color=kwargs.get('color', [0.0, 1.0, 1.0]))
    # Let's verify snapping works by pushing it to floor, then lifting it up manually in YAML
    mesh = builder.snap_to_floor(mesh) 
    return mesh
