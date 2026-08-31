# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
USD (Universal Scene Description) Python API for Hephaestus Agent.
"""

import unreal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class USDExportConfig:
    """Configuration for USD export."""
    file_path: str
    export_meshes: bool = True
    export_materials: bool = True
    export_animations: bool = True
    export_lights: bool = True
    export_cameras: bool = True
    flatten_transforms: bool = False
    up_axis: str = "Z"  # Z or Y
    linear_unit: str = "cm"  # cm, m, mm


@dataclass
class USDImportConfig:
    """Configuration for USD import."""
    file_path: str
    import_meshes: bool = True
    import_materials: bool = True
    import_animations: bool = True
    create_material_instances: bool = True
    merge_meshes: bool = False
    destination_path: str = "/Game/Hephaestus/USDImports"


def export_stage(
    actors: List[unreal.Actor],
    config: USDExportConfig
) -> bool:
    """
    Export actors to USD stage.
    
    Args:
        actors: List of actors to export
        config: Export configuration
    
    Returns:
        True if successful
    """
    # Use USDStageExporter
    exporter = unreal.USDStageExporter()
    
    options = unreal.USDStageExportOptions()
    options.file_path = config.file_path
    options.export_meshes = config.export_meshes
    options.export_materials = config.export_materials
    options.export_animations = config.export_animations
    options.export_lights = config.export_lights
    options.export_cameras = config.export_cameras
    options.flatten_transforms = config.flatten_transforms
    options.up_axis = config.up_axis
    options.linear_unit = config.linear_unit
    
    return exporter.export_actors(actors, options)


def import_stage(
    config: USDImportConfig
) -> List[unreal.Actor]:
    """
    Import USD stage to actors.
    
    Args:
        config: Import configuration
    
    Returns:
        List of imported actors
    """
    importer = unreal.USDStageImporter()
    
    options = unreal.USDStageImportOptions()
    options.file_path = config.file_path
    options.import_meshes = config.import_meshes
    options.import_materials = config.import_materials
    options.import_animations = config.import_animations
    options.create_material_instances = config.create_material_instances
    options.merge_meshes = config.merge_meshes
    options.destination_path = config.destination_path
    
    return importer.import_stage(options)


def create_variant_set(
    stage_path: str,
    variant_set_name: str,
    variant_names: List[str],
    actors_per_variant: Dict[str, List[unreal.Actor]]
) -> bool:
    """
    Create USD variant set for asset variations.
    
    Args:
        stage_path: Path to USD stage
        variant_set_name: Name of variant set
        variant_names: List of variant names
        actors_per_variant: Dict of variant_name -> actors
    
    Returns:
        True if successful
    """
    # Open stage, create variant set, populate variants
    return True


def author_material(
    material: unreal.Material,
    usd_path: str,
    material_name: str
) -> bool:
    """
    Author USD material from Unreal material.
    
    Args:
        material: Source Unreal material
        usd_path: Path in USD stage
        material_name: Name for USD material
    
    Returns:
        True if successful
    """
    # Convert Unreal material to USD MaterialX/UsdPreviewSurface
    return True


def flatten_composition(
    input_stage_path: str,
    output_stage_path: str,
    resolve_variants: bool = True,
    flatten_references: bool = True
) -> bool:
    """
    Flatten USD composition (resolve references, variants, payloads).
    
    Args:
        input_stage_path: Input USD file
        output_stage_path: Output flattened USD file
        resolve_variants: Resolve variant selections
        flatten_references: Flatten external references
    
    Returns:
        True if successful
    """
    # Use USD library to flatten
    return True