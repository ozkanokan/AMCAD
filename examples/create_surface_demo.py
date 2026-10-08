"""V1.4 illustrative surface ports on the same shared, noncommercial cavity."""
from pathlib import Path
from core.cavity_surface import SurfaceAnchor,ChannelSection,normalized,resolve_anchor
from core.graph import save_graph
from examples.create_physical_demo import create_physical_demo


def create_surface_demo():
    project=create_physical_demo()
    project.metadata['name']='Illustrative parallel Check Valve — surface/channel demonstrator'
    physical=project.definitions['illustrative-check-valve'].physical
    profile=physical.cavity_profile
    inlet,outlet=physical.hydraulic_interfaces
    inlet.interface_type='SURFACE'
    inlet.surface_anchor=SurfaceAnchor('LINE',profile.vertices[4].id,profile.vertices[5].id,t=.8,angle_deg=0)
    inlet.direction=(0,0,1); inlet.section=ChannelSection('CIRCLE',diameter_mm=4); inlet.preview_length_mm=12
    outlet.interface_type='SURFACE'
    outlet.surface_anchor=SurfaceAnchor('LINE',profile.vertices[2].id,profile.vertices[3].id,t=(14.5-8)/12,angle_deg=90)
    outlet.direction=normalized((0,1,.25)); outlet.section=ChannelSection('SLOT',width_mm=4,length_mm=7)
    outlet.section_rotation_deg=20; outlet.preview_length_mm=10
    for marker in physical.hydraulic_interfaces:
        xyz,_=resolve_anchor(profile,marker.surface_anchor)
        marker.z_mm=xyz[2]; marker.r_mm=(xyz[0]**2+xyz[1]**2)**.5
    project.validate()
    return project


if __name__=='__main__':
    root=Path(__file__).parent
    project=create_surface_demo()
    project.save(root/'parallel_check_valves_3d.amcad.json')
    save_graph(project,root/'parallel_check_valves_3d.graph.json')
