# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Blender IPC (Inter-Process Communication) Python API for Hephaestus Agent.
Executes Blender Python scripts via subprocess or persistent Blender MCP server.
"""

import subprocess
import tempfile
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class BlenderConfig:
    """Blender execution configuration."""
    blender_executable: str = "blender"
    background: bool = True
    python_script: Optional[str] = None
    python_expr: Optional[str] = None
    args: List[str] = None
    timeout_seconds: int = 300
    working_dir: Optional[str] = None

    def __post_init__(self):
        if self.args is None:
            self.args = []


@dataclass
class BlenderResult:
    """Result from Blender execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    output_files: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.output_files is None:
            self.output_files = []


class BlenderIPC:
    """Blender IPC client for executing Python scripts."""
    
    def __init__(self, config: BlenderConfig = None):
        self.config = config or BlenderConfig()
    
    def exec_script(self, script: str, args: List[str] = None) -> BlenderResult:
        """
        Execute a Blender Python script.
        
        Args:
            script: Python script content
            args: Additional arguments to pass to script
        
        Returns:
            BlenderResult with execution outcome
        """
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            script_path = f.name
        
        try:
            cmd = [self.config.blender_executable]
            
            if self.config.background:
                cmd.append("--background")
            
            cmd.extend(["--python", script_path])
            
            if args:
                cmd.extend(["--"] + args)
            
            if self.config.args:
                cmd.extend(self.config.args)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=self.config.working_dir
            )
            
            return BlenderResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode
            )
        
        except subprocess.TimeoutExpired:
            return BlenderResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=f"Timeout after {self.config.timeout_seconds}s"
            )
        except Exception as e:
            return BlenderResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )
        finally:
            # Cleanup temp file
            try:
                os.unlink(script_path)
            except:
                pass
    
    def exec_expr(self, expr: str) -> BlenderResult:
        """
        Execute a Blender Python expression.
        
        Args:
            expr: Python expression
        
        Returns:
            BlenderResult with execution outcome
        """
        cmd = [self.config.blender_executable]
        
        if self.config.background:
            cmd.append("--background")
        
        cmd.extend(["--python-expr", expr])
        
        if self.config.args:
            cmd.extend(self.config.args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=self.config.working_dir
            )
            
            return BlenderResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode
            )
        
        except subprocess.TimeoutExpired:
            return BlenderResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=f"Timeout after {self.config.timeout_seconds}s"
            )
        except Exception as e:
            return BlenderResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )


def retopologize(
    input_mesh: str,
    output_mesh: str,
    target_face_count: int = 5000,
    method: str = "quadriflow"
) -> BlenderResult:
    """
    Retopologize a mesh using Blender.
    
    Args:
        input_mesh: Path to input mesh (FBX/OBJ/GLTF)
        output_mesh: Path to output mesh
        target_face_count: Target face count
        method: Retopology method (quadriflow, instant_meshes, manual)
    
    Returns:
        BlenderResult with output mesh path
    """
    script = f"""
import bpy
import sys

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import mesh
bpy.ops.import_scene.fbx(filepath=r'{input_mesh}')
# or bpy.ops.import_scene.obj/gltf

# Get imported object
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj

# Retopology
if '{method}' == 'quadriflow':
    # Use Quadriflow remesh
    bpy.ops.object.modifier_add(type='REMESH')
    obj.modifiers['Remesh'].mode = 'QUAD'
    obj.modifiers['Remesh'].quadriflow_target_faces = {target_face_count}
    bpy.ops.object.modifier_apply(modifier='Remesh')

# Export
bpy.ops.export_scene.fbx(filepath=r'{output_mesh}', use_selection=True)
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [output_mesh]
    
    return result


def uv_pack(
    input_mesh: str,
    output_mesh: str,
    margin: float = 0.001,
    method: str = "default"
) -> BlenderResult:
    """
    Pack UVs for a mesh.
    
    Args:
        input_mesh: Path to input mesh
        output_mesh: Path to output mesh
        margin: UV margin
        method: Packing method (default, lightmap)
    
    Returns:
        BlenderResult with output mesh path
    """
    script = f"""
import bpy

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import
bpy.ops.import_scene.fbx(filepath=r'{input_mesh}')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj

# UV Pack
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin={margin})
bpy.ops.object.mode_set(mode='OBJECT')

# Export
bpy.ops.export_scene.fbx(filepath=r'{output_mesh}', use_selection=True)
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [output_mesh]
    
    return result


def bake_maps(
    high_poly: str,
    low_poly: str,
    output_dir: str,
    maps: List[str] = None,
    resolution: int = 2048,
    cage_multiplier: float = 1.0
) -> BlenderResult:
    """
    Bake normal, AO, curvature maps from high-poly to low-poly.
    
    Args:
        high_poly: Path to high-poly mesh
        low_poly: Path to low-poly mesh
        output_dir: Output directory for baked textures
        maps: List of maps to bake (normal, ao, curvature, position, thickness)
        resolution: Texture resolution
        cage_multiplier: Cage extrusion multiplier
    
    Returns:
        BlenderResult with output texture paths
    """
    if maps is None:
        maps = ["normal", "ao", "curvature"]
    
    maps_str = ", ".join([f"'{m}'" for m in maps])
    
    script = f"""
import bpy
import os

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import high poly
bpy.ops.import_scene.fbx(filepath=r'{high_poly}')
high_obj = bpy.context.selected_objects[0]
high_obj.name = 'HighPoly'

# Import low poly
bpy.ops.import_scene.fbx(filepath=r'{low_poly}')
low_obj = bpy.context.selected_objects[0]
low_obj.name = 'LowPoly'

# Setup bake
bpy.context.view_layer.objects.active = low_obj
low_obj.select_set(True)
high_obj.select_set(True)

# Create images for baking
for map_name in [{maps_str}]:
    img = bpy.data.images.new(f'LowPoly_{{map_name}}', width={resolution}, height={resolution})
    # Setup material with image texture node

# Bake settings
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.bake_type = 'COMBINED'  # or specific type
bpy.context.scene.render.bake.use_cage = True
bpy.context.scene.render.bake.cage_extrusion = {cage_multiplier}
bpy.context.scene.render.bake.margin = 16

# Bake each map
for map_name in [{maps_str}]:
    bpy.context.scene.cycles.bake_type = map_name.upper()
    bpy.ops.object.bake(type=map_name.upper())
    # Save image
    img = bpy.data.images[f'LowPoly_{{map_name}}']
    img.save_render(os.path.join(r'{output_dir}', f'LowPoly_{{map_name}}.png'))

# Export low poly with baked textures
bpy.ops.export_scene.fbx(filepath=r'{os.path.join(output_dir, "low_poly_baked.fbx")}', use_selection=True)
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [os.path.join(output_dir, f"low_poly_{m}.png") for m in maps]
        result.output_files.append(os.path.join(output_dir, "low_poly_baked.fbx"))
    
    return result


def rigify_character(
    input_mesh: str,
    output_mesh: str,
    rig_type: str = "human",
    auto_weights: bool = True
) -> BlenderResult:
    """
    Auto-rig character using Rigify.
    
    Args:
        input_mesh: Path to character mesh
        output_mesh: Path to output rigged mesh
        rig_type: Rigify preset (human, quadruped, bird, etc.)
        auto_weights: Auto-assign vertex weights
    
    Returns:
        BlenderResult with output rigged mesh
    """
    script = f"""
import bpy

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import
bpy.ops.import_scene.fbx(filepath=r'{input_mesh}')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj

# Add Rigify armature
bpy.ops.object.armature_human_metarig_add()
rig = bpy.context.active_object
rig.name = 'Rigify_Rig'

# Scale rig to match mesh
# ... match proportions ...

# Generate rig
bpy.ops.pose.rigify_generate()

# Parent mesh to rig
obj.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO' if {auto_weights} else 'ARMATURE_NAME')

# Export
bpy.ops.export_scene.fbx(filepath=r'{output_mesh}', use_selection=True, add_leaf_bones=False)
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [output_mesh]
    
    return result


def export_fbx(
    input_blend: str,
    output_fbx: str,
    selected_only: bool = True,
    apply_modifiers: bool = True
) -> BlenderResult:
    """
    Export Blender file to FBX.
    
    Args:
        input_blend: Path to .blend file
        output_fbx: Path to output FBX
        selected_only: Export only selected objects
        apply_modifiers: Apply modifiers before export
    
    Returns:
        BlenderResult with output FBX path
    """
    script = f"""
import bpy

# Open blend file
bpy.ops.wm.open_mainfile(filepath=r'{input_blend}')

# Select objects
if {selected_only}:
    bpy.ops.object.select_all(action='DESELECT')
    # Select specific objects
else:
    bpy.ops.object.select_all(action='SELECT')

# Export
bpy.ops.export_scene.fbx(
    filepath=r'{output_fbx}',
    use_selection={selected_only},
    apply_modifiers={apply_modifiers},
    add_leaf_bones=False,
    primary_bone_axis='Y',
    secondary_bone_axis='X'
)
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [output_fbx]
    
    return result


def geometry_nodes_eval(
    input_blend: str,
    node_group_name: str,
    inputs: Dict[str, Any],
    output_mesh: str
) -> BlenderResult:
    """
    Evaluate Geometry Nodes and export result.
    
    Args:
        input_blend: Path to .blend file with Geometry Nodes
        node_group_name: Name of Geometry Node group
        inputs: Dict of input socket name -> value
        output_mesh: Path to output mesh
    
    Returns:
        BlenderResult with output mesh
    """
    # Build input assignments
    input_assignments = []
    for key, value in inputs.items():
        if isinstance(value, str):
            input_assignments.append(f"inputs['{key}'].default_value = '{value}'")
        elif isinstance(value, (int, float)):
            input_assignments.append(f"inputs['{key}'].default_value = {value}")
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            input_assignments.append(f"inputs['{key}'].default_value = ({value[0]}, {value[1]}, {value[2]})")
    
    inputs_code = "\n".join(input_assignments)
    
    script = f"""
import bpy

# Open blend file
bpy.ops.wm.open_mainfile(filepath=r'{input_blend}')

# Find geometry nodes modifier
for obj in bpy.data.objects:
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.node_group.name == '{node_group_name}':
            inputs = mod.node_group.interface.items_tree
            {inputs_code}
            # Apply modifier
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=mod.name)
            
            # Export result
            bpy.ops.export_scene.fbx(filepath=r'{output_mesh}', use_selection=True)
            break
"""
    
    ipc = BlenderIPC()
    result = ipc.exec_script(script)
    
    if result.success:
        result.output_files = [output_mesh]
    
    return result