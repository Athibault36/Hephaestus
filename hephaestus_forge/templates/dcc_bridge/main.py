# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
DCC Bridge - FastAPI microservice for Blender, CC5/iClone, Meshy integration.
Called by HEPHAESTUS agent via HTTP tools.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn


# ─── Configuration ────────────────────────────────────────────────────────────

class Config:
    blender_executable: str = os.getenv("BLENDER_EXECUTABLE", "blender")
    blender_timeout: int = int(os.getenv("BLENDER_TIMEOUT", "300"))
    cc5_executable: str = os.getenv("CC5_EXECUTABLE", "rlpython")
    cc5_timeout: int = int(os.getenv("CC5_TIMEOUT", "120"))
    meshy_api_key: str = os.getenv("MESHY_API_KEY", "")
    meshy_base_url: str = os.getenv("MESHY_BASE_URL", "https://api.meshy.ai/v1")
    meshy_timeout: int = int(os.getenv("MESHY_TIMEOUT", "120"))
    host: str = os.getenv("DCC_BRIDGE_HOST", "127.0.0.1")
    port: int = int(os.getenv("DCC_BRIDGE_PORT", "8084"))


# ─── Request/Response Models ──────────────────────────────────────────────────

class BlenderExecRequest(BaseModel):
    script: str
    args: List[str] = []
    timeout: Optional[int] = None


class BlenderExecResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    return_code: int
    output_files: List[str] = []


class BlenderRetopoRequest(BaseModel):
    input_mesh: str
    output_mesh: str
    target_face_count: int = 5000
    method: str = "quadriflow"


class BlenderUVRequest(BaseModel):
    input_mesh: str
    output_mesh: str
    margin: float = 0.001


class BlenderBakeRequest(BaseModel):
    high_poly: str
    low_poly: str
    output_dir: str
    maps: List[str] = ["normal", "ao", "curvature"]
    resolution: int = 2048


class BlenderRigifyRequest(BaseModel):
    input_mesh: str
    output_mesh: str
    rig_type: str = "human"
    auto_weights: bool = True


class BlenderGeometryNodesRequest(BaseModel):
    input_blend: str
    node_group_name: str
    inputs: Dict[str, Any]
    output_mesh: str


class CC5ExportRequest(BaseModel):
    character_name: str
    output_path: str
    export_format: str = "FBX"
    include_morphs: bool = True
    include_cloth: bool = True
    lod_levels: int = 3


class CC5ConformRequest(BaseModel):
    character_name: str
    cloth_item: str
    output_path: str


class CC5AccuRigRequest(BaseModel):
    character_name: str
    rig_preset: str = "Game_UE5"
    output_path: str = ""


class CC5FacialProfileRequest(BaseModel):
    character_name: str
    profile_name: str = "Standard"
    custom_blendshapes: Optional[Dict[str, float]] = None


class CC5RetargetRequest(BaseModel):
    source_character: str
    target_character: str
    motion_file: str
    output_path: str


class CC5LiveLinkRequest(BaseModel):
    character_name: str
    enable: bool = True
    port: int = 11111


class MeshyGenerateRequest(BaseModel):
    prompt: str
    image_url: Optional[str] = None
    art_style: str = "realistic"
    topology: str = "quad"
    target_polycount: int = 10000
    symmetry: bool = True
    generate_uvs: bool = True


class MeshyTextureRequest(BaseModel):
    model_url: str
    prompt: str
    art_style: str = "realistic"
    resolution: int = 2048


class MeshyStatusRequest(BaseModel):
    task_id: str


class MeshyImportRequest(BaseModel):
    model_path: str
    ue_project_path: str
    destination_path: str = "/Game/Hephaestus/MeshyImports"
    create_material_instances: bool = True


# ─── Blender Execution ────────────────────────────────────────────────────────

async def run_blender_script(script: str, args: List[str] = None, timeout: int = None) -> BlenderExecResponse:
    """Execute Blender Python script asynchronously."""
    timeout = timeout or Config.blender_timeout
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        cmd = [Config.blender_executable, "--background", "--python", script_path]
        if args:
            cmd.extend(["--"] + args)
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return BlenderExecResponse(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=f"Timeout after {timeout}s"
            )
        
        return BlenderExecResponse(
            success=process.returncode == 0,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            return_code=process.returncode
        )
    
    finally:
        try:
            os.unlink(script_path)
        except:
            pass


# ─── CC5 Execution ────────────────────────────────────────────────────────────

async def run_cc5_script(script: str, timeout: int = None) -> Dict[str, Any]:
    """Execute CC5 rlpython script when rlpython is installed."""
    timeout = timeout or Config.cc5_timeout
    try:
        from hephaestus_forge.cc5_bridge import find_rlpython
    except ImportError:
        find_rlpython = None  # type: ignore
    rlpy = find_rlpython() if find_rlpython else None
    if not rlpy:
        return {
            "success": False,
            "error": "cc5_unavailable — rlpython not found (set RLPYTHON / install Character Creator 5)",
        }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            rlpy,
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": f"rlpython timed out after {timeout}s"}
        return {
            "success": proc.returncode == 0,
            "stdout": (stdout or b"").decode("utf-8", errors="replace"),
            "stderr": (stderr or b"").decode("utf-8", errors="replace"),
            "return_code": proc.returncode,
            "error": "" if proc.returncode == 0 else "rlpython failed",
        }
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


# ─── Meshy API ────────────────────────────────────────────────────────────────

class MeshyClient:
    def __init__(self):
        self.session = requests.Session()
        if Config.meshy_api_key:
            self.session.headers.update({"Authorization": f"Bearer {Config.meshy_api_key}"})
        self.session.headers.update({"Content-Type": "application/json"})
        self.base_url = Config.meshy_base_url
    
    def generate(self, request: MeshyGenerateRequest) -> Dict[str, Any]:
        payload = {
            "mode": "preview" if not request.image_url else "refine",
            "prompt": request.prompt,
            "art_style": request.art_style,
            "topology": request.topology,
            "target_polycount": request.target_polycount,
            "symmetry": request.symmetry,
            "generate_uvs": request.generate_uvs
        }
        if request.image_url:
            payload["image_url"] = request.image_url
        
        response = self.session.post(
            f"{self.base_url}/openapi/generate",
            json=payload,
            timeout=Config.meshy_timeout
        )
        return response.json()
    
    def texture(self, request: MeshyTextureRequest) -> Dict[str, Any]:
        payload = {
            "model_url": request.model_url,
            "prompt": request.prompt,
            "art_style": request.art_style,
            "resolution": request.resolution
        }
        
        response = self.session.post(
            f"{self.base_url}/openapi/texture",
            json=payload,
            timeout=Config.meshy_timeout
        )
        return response.json()
    
    def status(self, task_id: str) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/openapi/status/{task_id}",
            timeout=Config.meshy_timeout
        )
        return response.json()


mesh_client = MeshyClient()


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Hephaestus DCC Bridge", version="1.0.0")


def _probe_blender_exe() -> dict:
    """Honest Blender detection (not always 'available')."""
    try:
        from hephaestus_forge.blender_bridge import find_blender
        path, version = find_blender()
        return {"available": bool(path), "path": path, "version": version}
    except Exception:
        import shutil
        exe = shutil.which(Config.blender_executable) or shutil.which("blender")
        return {"available": bool(exe), "path": exe, "version": None}


# Health — prefer factory dcc_server via `forge dcc start`; this scaffold stays for adopt copies.
@app.get("/health")
@app.get("/v1/health")
async def health():
    blender = _probe_blender_exe()
    return {
        "ok": True,
        "status": "healthy" if blender["available"] else "degraded",
        "service": "hephaestus-dcc-scaffold",
        "ready": blender["available"],
        "blender": blender,
        "services": {
            "blender": "available" if blender["available"] else "missing",
            "cc5": "probe_via_forge_cc5",
            "meshy": "configured" if Config.meshy_api_key else "no_api_key",
        },
        "hint": "Prefer `forge dcc start` (factory hephaestus_forge.dcc_server) for /v1/command verbs",
    }


@app.post("/v1/command")
async def v1_command(request: Request):
    """UE-like command surface; delegates to factory route_command when importable."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    cmd = body.get("command") or ""
    params = body.get("params") or body.get("args") or {}
    try:
        from hephaestus_forge.dcc_server import route_command
        result = route_command(str(cmd), params if isinstance(params, dict) else {})
        status = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status)
    except ImportError:
        raise HTTPException(
            501,
            "Factory dcc_server not on PYTHONPATH — run: forge dcc start",
        )


# Blender Endpoints
@app.post("/blender/exec", response_model=BlenderExecResponse)
async def blender_exec(request: BlenderExecRequest):
    """Execute arbitrary Blender Python script."""
    return await run_blender_script(request.script, request.args, request.timeout)


@app.post("/blender/retopologize", response_model=BlenderExecResponse)
async def blender_retopologize(request: BlenderRetopoRequest):
    """Retopologize mesh using Blender."""
    script = f"""
import bpy

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import
bpy.ops.import_scene.fbx(filepath=r'{request.input_mesh}')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj

# Retopology
bpy.ops.object.modifier_add(type='REMESH')
obj.modifiers['Remesh'].mode = 'QUAD'
obj.modifiers['Remesh'].quadriflow_target_faces = {request.target_face_count}
bpy.ops.object.modifier_apply(modifier='Remesh')

# Export
bpy.ops.export_scene.fbx(filepath=r'{request.output_mesh}', use_selection=True)
"""
    result = await run_blender_script(script)
    if result.success:
        result.output_files = [request.output_mesh]
    return result


@app.post("/blender/uv_pack", response_model=BlenderExecResponse)
async def blender_uv_pack(request: BlenderUVRequest):
    """Pack UVs."""
    script = f"""
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.import_scene.fbx(filepath=r'{request.input_mesh}')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin={request.margin})
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.export_scene.fbx(filepath=r'{request.output_mesh}', use_selection=True)
"""
    result = await run_blender_script(script)
    if result.success:
        result.output_files = [request.output_mesh]
    return result


@app.post("/blender/bake", response_model=BlenderExecResponse)
async def blender_bake(request: BlenderBakeRequest):
    """Bake maps from high-poly to low-poly."""
    maps_str = ", ".join([f"'{m}'" for m in request.maps])
    script = f"""
import bpy, os
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

bpy.ops.import_scene.fbx(filepath=r'{request.high_poly}')
high = bpy.context.selected_objects[0]
high.name = 'HighPoly'

bpy.ops.import_scene.fbx(filepath=r'{request.low_poly}')
low = bpy.context.selected_objects[0]
low.name = 'LowPoly'

bpy.context.view_layer.objects.active = low
low.select_set(True)
high.select_set(True)

for m in [{maps_str}]:
    img = bpy.data.images.new(f'LowPoly_{{m}}', width={request.resolution}, height={request.resolution})

bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.bake_type = 'COMBINED'
bpy.context.scene.render.bake.use_cage = True
bpy.context.scene.render.bake.cage_extrusion = 1.0
bpy.context.scene.render.bake.margin = 16

for m in [{maps_str}]:
    bpy.context.scene.cycles.bake_type = m.upper()
    bpy.ops.object.bake(type=m.upper())
    img = bpy.data.images[f'LowPoly_{{m}}']
    img.save_render(os.path.join(r'{request.output_dir}', f'LowPoly_{{m}}.png'))

bpy.ops.export_scene.fbx(filepath=r'{os.path.join(request.output_dir, "low_poly_baked.fbx")}', use_selection=True)
"""
    result = await run_blender_script(script, timeout=600)
    if result.success:
        result.output_files = [os.path.join(request.output_dir, f"low_poly_{m}.png") for m in request.maps]
        result.output_files.append(os.path.join(request.output_dir, "low_poly_baked.fbx"))
    return result


@app.post("/blender/rigify", response_model=BlenderExecResponse)
async def blender_rigify(request: BlenderRigifyRequest):
    """Auto-rig with Rigify."""
    script = f"""
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.import_scene.fbx(filepath=r'{request.input_mesh}')
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.armature_human_metarig_add()
rig = bpy.context.active_object
rig.name = 'Rigify_Rig'
bpy.ops.pose.rigify_generate()
obj.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO' if {str(request.auto_weights).lower()} else 'ARMATURE_NAME')
bpy.ops.export_scene.fbx(filepath=r'{request.output_mesh}', use_selection=True, add_leaf_bones=False)
"""
    result = await run_blender_script(script, timeout=600)
    if result.success:
        result.output_files = [request.output_mesh]
    return result


@app.post("/blender/geometry_nodes", response_model=BlenderExecResponse)
async def blender_geometry_nodes(request: BlenderGeometryNodesRequest):
    """Evaluate Geometry Nodes."""
    input_assignments = []
    for key, value in request.inputs.items():
        if isinstance(value, str):
            input_assignments.append(f"inputs['{key}'].default_value = '{value}'")
        elif isinstance(value, (int, float)):
            input_assignments.append(f"inputs['{key}'].default_value = {value}")
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            input_assignments.append(f"inputs['{key}'].default_value = ({value[0]}, {value[1]}, {value[2]})")
    
    script = f"""
import bpy
bpy.ops.wm.open_mainfile(filepath=r'{request.input_blend}')
for obj in bpy.data.objects:
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.node_group.name == '{request.node_group_name}':
            inputs = mod.node_group.interface.items_tree
            {'; '.join(input_assignments)}
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.ops.export_scene.fbx(filepath=r'{request.output_mesh}', use_selection=True)
            break
"""
    result = await run_blender_script(script)
    if result.success:
        result.output_files = [request.output_mesh]
    return result


# CC5 Endpoints
@app.post("/cc5/export")
async def cc5_export(request: CC5ExportRequest):
    """Export character from CC5."""
    script = f"""
import RLPy
character = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.character_name}")
if character:
    export_settings = RLPy.RFbxExport()
    export_settings.SetExportMorphTargets({str(request.include_morphs).lower()})
    export_settings.SetExportCloth({str(request.include_cloth).lower()})
    export_settings.SetLODLevels({request.lod_levels})
    RLPy.RFileIO.ExportFbx("{request.output_path}", export_settings)
"""
    return await run_cc5_script(script)


@app.post("/cc5/conform")
async def cc5_conform(request: CC5ConformRequest):
    """Conform cloth to character."""
    script = f"""
import RLPy
character = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.character_name}")
cloth = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, "{request.cloth_item}")
if character and cloth:
    RLPy.RCloth.Conform(cloth, character)
"""
    return await run_cc5_script(script)


@app.post("/cc5/accu_rig")
async def cc5_accu_rig(request: CC5AccuRigRequest):
    """Auto-rig with AccuRIG."""
    script = f"""
import RLPy
character = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.character_name}")
if character:
    RLPy.RAccuRig.AutoRig(character, "{request.rig_preset}")
"""
    return await run_cc5_script(script)


@app.post("/cc5/facial_profile")
async def cc5_facial_profile(request: CC5FacialProfileRequest):
    """Setup facial profile."""
    script = f"""
import RLPy
character = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.character_name}")
if character:
    face_profile = character.GetFaceProfile()
    face_profile.LoadProfile("{request.profile_name}")
"""
    return await run_cc5_script(script)


@app.post("/cc5/retarget")
async def cc5_retarget(request: CC5RetargetRequest):
    """Retarget motion."""
    script = f"""
import RLPy
source = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.source_character}")
target = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.target_character}")
if source and target:
    motion = RLPy.RFileIO.LoadMotion("{request.motion_file}")
    retargeted = RLPy.RMotion.Retarget(motion, source, target)
    RLPy.RFileIO.SaveMotion(retargeted, "{request.output_path}")
"""
    return await run_cc5_script(script)


@app.post("/cc5/livelink")
async def cc5_livelink(request: CC5LiveLinkRequest):
    """Start/stop LiveLink facial."""
    script = f"""
import RLPy
character = RLPy.RScene.FindObject(RLPy.EObjectType_Avatar, "{request.character_name}")
if character:
    live_link = character.GetLiveLink()
    if {str(request.enable).lower()}:
        live_link.StartStreaming({request.port})
    else:
        live_link.StopStreaming()
"""
    return await run_cc5_script(script)


# Meshy Endpoints
@app.post("/meshy/generate")
async def meshy_generate(request: MeshyGenerateRequest):
    """Generate 3D model from text/image."""
    return mesh_client.generate(request)


@app.post("/meshy/texture")
async def meshy_texture(request: MeshyTextureRequest):
    """Generate PBR textures."""
    return mesh_client.texture(request)


@app.post("/meshy/status")
async def meshy_status(request: MeshyStatusRequest):
    """Get task status."""
    return mesh_client.status(request.task_id)


@app.post("/meshy/import")
async def meshy_import(request: MeshyImportRequest):
    """Import Meshy model to UE (runs in UE Python context)."""
    # This endpoint documents the import process
    # Actual import happens in UE via hephaestus.dcc_bridge.meshy_import_to_ue
    return {
        "success": True,
        "message": "Import must be run from within UE Python environment",
        "function": "hephaestus.dcc_bridge.meshy_import_to_ue"
    }


if __name__ == "__main__":
    uvicorn.run(app, host=Config.host, port=Config.port)