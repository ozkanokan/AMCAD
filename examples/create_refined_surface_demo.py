"""V1.4a closed-axis example; existing legacy example files remain untouched."""
from pathlib import Path
from core.project import Project
from core.graph import save_graph
from core.cavity_surface import outward_direction,resolve_anchor


def create_refined_surface_demo():
    root=Path(__file__).parent
    project=Project.load(root/'parallel_check_valves_3d.amcad.json')
    project.metadata['name']='Illustrative parallel Check Valve — V1.4a closed cavity'
    physical=project.definitions['illustrative-check-valve'].physical
    profile=physical.cavity_profile
    profile.vertices[0].r=profile.vertices[-1].r=0
    for marker in physical.hydraulic_interfaces:
        marker.direction=outward_direction(profile,marker.surface_anchor,marker.direction)
        marker.preview_mode='CENTERED'; marker.preview_length_mm=2
        xyz,_=resolve_anchor(profile,marker.surface_anchor)
        marker.z_mm=xyz[2]; marker.r_mm=(xyz[0]**2+xyz[1]**2)**.5
    physical.validate(project.definitions['illustrative-check-valve'].ports,strict=True)
    return project


if __name__=='__main__':
    root=Path(__file__).parent; project=create_refined_surface_demo()
    project.save(root/'parallel_check_valves_v14a.amcad.json')
    save_graph(project,root/'parallel_check_valves_v14a.graph.json')
