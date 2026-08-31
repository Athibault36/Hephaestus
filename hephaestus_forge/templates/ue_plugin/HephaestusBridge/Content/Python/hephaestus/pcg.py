# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
PCG (Procedural Content Generation) Python API for Hephaestus Agent.
"""

import unreal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class BiomeConfig:
    """Configuration for biome generation."""
    name: str
    foliage_density: float = 1.0
    tree_types: List[str] = None
    ground_materials: List[str] = None
    height_range: tuple = (0.0, 1.0)
    slope_range: tuple = (0.0, 45.0)

    def __post_init__(self):
        if self.tree_types is None:
            self.tree_types = ["SM_Tree_Pine", "SM_Tree_Oak"]
        if self.ground_materials is None:
            self.ground_materials = ["M_Ground_Grass", "M_Ground_Dirt"]


@dataclass
class ScatterConfig:
    """Configuration for foliage scattering."""
    static_meshes: List[str]
    density: float = 100.0
    min_scale: float = 0.8
    max_scale: float = 1.2
    align_to_normal: bool = True
    collision_check: bool = True
    cull_distance: float = 50000.0


def generate_landscape(
    size_km: float = 2.0,
    resolution: int = 2017,
    heightmap_path: Optional[str] = None,
    noise_seed: int = 42,
    noise_frequency: float = 0.01,
    noise_octaves: int = 6
) -> unreal.Landscape:
    """
    Generate a procedural landscape.
    
    Args:
        size_km: Landscape size in kilometers
        resolution: Heightmap resolution (must be 2^n + 1)
        heightmap_path: Optional path to existing heightmap
        noise_seed: Random seed for noise generation
        noise_frequency: Noise frequency
        noise_octaves: Number of noise octaves
    
    Returns:
        Generated Landscape actor
    """
    # Create landscape proxy
    landscape_proxy = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.LandscapeProxy,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0)
    )
    
    # Configure landscape
    landscape_proxy.set_editor_property("landscape_guid", unreal.Guid())
    
    # Create landscape components
    # This would use the LandscapeEditorModule in practice
    
    return landscape_proxy


def scatter_foliage(
    landscape: unreal.Landscape,
    configs: List[ScatterConfig],
    biome_mask: Optional[unreal.Texture2D] = None
) -> List[unreal.InstancedStaticMeshComponent]:
    """
    Scatter foliage on landscape using PCG.
    
    Args:
        landscape: Target landscape
        configs: List of scatter configurations
        biome_mask: Optional texture mask for biome blending
    
    Returns:
        List of created InstancedStaticMeshComponents
    """
    components = []
    
    for config in configs:
        for mesh_path in config.static_meshes:
            static_mesh = unreal.load_asset(mesh_path)
            if not static_mesh:
                continue
            
            ism_component = unreal.InstancedStaticMeshComponent()
            ism_component.set_static_mesh(static_mesh)
            
            # Configure scattering
            # This would use PCG graph in practice
            
            components.append(ism_component)
    
    return components


def create_biome_graph(
    biomes: List[BiomeConfig],
    output_path: str = "/Game/Hephaestus/PCG/BiomeGraph"
) -> unreal.PCGGraph:
    """
    Create a PCG biome graph.
    
    Args:
        biomes: List of biome configurations
        output_path: Path to save the graph asset
    
    Returns:
        Created PCGGraph asset
    """
    # Create PCG graph asset
    graph = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "BiomeGraph",
        output_path,
        unreal.PCGGraph,
        unreal.PCGGraphFactory()
    )
    
    # Add biome nodes
    # This would programmatically build the PCG graph
    
    return graph


def mutate_metadata(
    pcg_component: unreal.PCGComponent,
    metadata_updates: Dict[str, Any]
) -> bool:
    """
    Mutate PCG metadata parameters at runtime.
    
    Args:
        pcg_component: Target PCG component
        metadata_updates: Dictionary of metadata key -> value
    
    Returns:
        True if successful
    """
    if not pcg_component:
        return False
    
    for key, value in metadata_updates.items():
        # Set metadata on component
        pcg_component.set_metadata_value(key, value)
    
    pcg_component.request_refresh()
    return True


def export_pcg_assets(
    pcg_component: unreal.PCGComponent,
    output_directory: str,
    export_meshes: bool = True,
    export_textures: bool = True,
    export_materials: bool = True
) -> List[str]:
    """
    Export PCG-generated assets to disk.
    
    Args:
        pcg_component: PCG component with generated data
        output_directory: Output directory path
        export_meshes: Export static meshes
        export_textures: Export textures
        export_materials: Export materials
    
    Returns:
        List of exported asset paths
    """
    exported = []
    
    # Get generated data from PCG component
    # Export each data type
    
    return exported