# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Factory-side Gaea bridge: locate Gaea 2 Build Swarm, execute a terrain graph
headlessly, and classify the exported heightmap / weightmap masks / surface
textures on disk for a downstream UE 5.8 landscape import.

Mirrors ``blender_bridge`` conventions: pure factory-side subprocess driver,
no ``unreal`` import, returns a JSON-serialisable dataclass. The operator's
machine runs Gaea for real; unit tests exercise the command construction,
output classification, and UE import staging with a mocked Swarm process.

Gaea 2 CLI (QuadSpinner Build Swarm)::

    Gaea.Swarm.exe --Filename "Terrain.terrain" [--profile P] [--region R]
                   [--seed N] [--ignorecache] [--verbose] [-v key:value ...]

Export nodes write to the project Build folder; each file is named after its
Export node (e.g. ``Height.png``, ``Slope.png``, ``Albedo.png``). Legacy Gaea 1
``.tor`` files are also accepted for backward compatibility.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Gaea graph document extensions (Gaea 2 = .terrain, legacy Gaea 1 = .tor).
GAEA_GRAPH_EXTENSIONS = (".terrain", ".tor")

# Raster extensions Gaea can export.
_IMAGE_EXTENSIONS = (".png", ".tif", ".tiff", ".exr", ".raw", ".r16", ".r32")

# 16/32-bit height-capable formats preferred for a landscape heightmap.
_HEIGHT_EXTENSIONS = (".r16", ".r32", ".raw", ".exr", ".tif", ".tiff")

# Keyword → category classification for Export node names (case-insensitive).
_HEIGHT_KEYWORDS = ("height", "elevation", "heightmap", "terrain", "displace", "displacement")
_MASK_KEYWORDS = (
    "slope", "flow", "flowmap", "sediment", "deposit", "deposits", "curvature",
    "wear", "erosion", "rock", "sand", "snow", "grass", "soil", "dirt", "mud",
    "mask", "occlusion", "ao", "cavity", "coast", "shore", "texture_mask",
    "weight", "weightmap", "splat",
)
_TEXTURE_KEYWORDS = (
    "albedo", "color", "colour", "diffuse", "basecolor", "base_color",
    "normal", "roughness", "metallic", "specular", "surface", "satmap",
)

_WINDOWS_GAEA_DIRS = (
    "Gaea 2",
    "Gaea2",
    "Gaea",
)

_POST_REPORT_NAMES = (
    "PostBuildReport.json",
    "BuildReport.json",
    "post_build_report.json",
)


@dataclass
class GaeaBuildResult:
    """Outcome of a forge → Gaea Build Swarm → on-disk terrain export."""

    success: bool
    gaea_path: Optional[str] = None
    gaea_version: Optional[str] = None
    terrain_file: Optional[str] = None
    build_folder: Optional[str] = None
    profile: Optional[str] = None
    region: Optional[str] = None
    seed: Optional[int] = None
    heightmap: Optional[str] = None
    masks: List[str] = field(default_factory=list)
    textures: List[str] = field(default_factory=list)
    other_outputs: List[str] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    error: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)

    @property
    def outputs(self) -> List[str]:
        """All classified export files (height + masks + textures + other)."""
        combined: List[str] = []
        if self.heightmap:
            combined.append(self.heightmap)
        combined.extend(self.masks)
        combined.extend(self.textures)
        combined.extend(self.other_outputs)
        return combined

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "gaea_path": self.gaea_path,
            "gaea_version": self.gaea_version,
            "terrain_file": self.terrain_file,
            "build_folder": self.build_folder,
            "profile": self.profile,
            "region": self.region,
            "seed": self.seed,
            "heightmap": self.heightmap,
            "masks": list(self.masks),
            "textures": list(self.textures),
            "other_outputs": list(self.other_outputs),
            "outputs": self.outputs,
            "command": list(self.command),
            "return_code": self.return_code,
            "error": self.error,
            "next_steps": list(self.next_steps),
            "stdout_tail": (self.stdout or "")[-2000:],
            "stderr_tail": (self.stderr or "")[-2000:],
        }


def find_gaea(
    explicit: Optional[str] = None,
    *,
    env: Optional[dict] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Locate the Gaea Build Swarm executable and a best-effort version string.

    Order: explicit / GAEA_SWARM / GAEA_EXECUTABLE / GAEA_PATH → PATH
    ``Gaea.Swarm`` → common Windows install dirs. Returns
    ``(path_or_None, version_or_None)``. Version is inferred from the install
    directory name (Gaea Swarm has no stable ``--version`` contract), so it is
    advisory only.
    """
    environ = env if env is not None else os.environ
    candidates: List[object] = []

    if explicit:
        candidates.append(Path(explicit))
    for var in ("GAEA_SWARM", "GAEA_EXECUTABLE", "GAEA_PATH"):
        val = (environ.get(var) or "").strip()
        if val:
            candidates.append(Path(val))
    candidates.append("Gaea.Swarm")
    candidates.append("Gaea.Swarm.exe")

    if os.name == "nt":
        pf = Path(environ.get("ProgramFiles", r"C:\Program Files"))
        pf86 = Path(environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        for base in (pf, pf86):
            for folder in _WINDOWS_GAEA_DIRS:
                candidates.append(base / "QuadSpinner" / folder / "Gaea.Swarm.exe")
                candidates.append(base / folder / "Gaea.Swarm.exe")

    seen: set[str] = set()
    for path in candidates:
        if isinstance(path, Path):
            # A supplied path may point at the install folder or Gaea.exe.
            resolved = _normalize_swarm_path(path)
            if resolved is None:
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            return str(resolved), _infer_version(resolved)
        # Bare command name — resolve via PATH without executing (avoids hangs).
        from shutil import which

        found = which(str(path))
        if found and found not in seen:
            seen.add(found)
            return found, _infer_version(Path(found))
    return None, None


def _normalize_swarm_path(path: Path) -> Optional[Path]:
    """Resolve a user-supplied path to a Gaea.Swarm executable if possible."""
    if path.is_dir():
        candidate = path / "Gaea.Swarm.exe"
        return candidate if candidate.exists() else None
    if path.exists():
        # Point Gaea.exe references at the sibling Swarm build engine.
        if path.name.lower() == "gaea.exe":
            sibling = path.with_name("Gaea.Swarm.exe")
            if sibling.exists():
                return sibling
        return path
    return None


def _infer_version(path: Path) -> Optional[str]:
    """Best-effort Gaea version from the install directory name."""
    for part in path.parts:
        m = re.search(r"Gaea\s*(\d+(?:\.\d+)*)", part, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def classify_outputs(files: Sequence[Path]) -> Tuple[Optional[str], List[str], List[str], List[str]]:
    """
    Split Gaea export files into (heightmap, masks, textures, other).

    Heightmap selection prefers a height-keyworded, height-capable format;
    remaining files are bucketed by keyword. Deterministic ordering keeps the
    result stable for tests and downstream import manifests.
    """
    images = sorted(
        (f for f in files if f.suffix.lower() in _IMAGE_EXTENSIONS),
        key=lambda p: p.name.lower(),
    )

    height_candidates: List[Path] = []
    masks: List[str] = []
    textures: List[str] = []
    other: List[str] = []

    for f in images:
        stem = f.stem.lower()
        suffix = f.suffix.lower()
        is_height_kw = any(k in stem for k in _HEIGHT_KEYWORDS)
        is_mask_kw = any(k in stem for k in _MASK_KEYWORDS)
        is_texture_kw = any(k in stem for k in _TEXTURE_KEYWORDS)

        if is_height_kw and not is_texture_kw:
            height_candidates.append(f)
        elif is_texture_kw:
            textures.append(str(f))
        elif is_mask_kw:
            masks.append(str(f))
        else:
            other.append(str(f))

    heightmap: Optional[str] = None
    if height_candidates:
        # Prefer a high-bit-depth format for the actual landscape heightmap.
        height_candidates.sort(
            key=lambda p: (p.suffix.lower() not in _HEIGHT_EXTENSIONS, p.name.lower())
        )
        heightmap = str(height_candidates[0])
        # Any extra height-keyworded rasters become masks (e.g. displacement).
        for extra in height_candidates[1:]:
            masks.append(str(extra))
    else:
        # No explicit height export — promote the best height-capable "other".
        promotable = [Path(p) for p in other if Path(p).suffix.lower() in _HEIGHT_EXTENSIONS]
        if promotable:
            promotable.sort(key=lambda p: p.name.lower())
            heightmap = str(promotable[0])
            other = [p for p in other if p != heightmap]

    return heightmap, sorted(masks), sorted(textures), sorted(other)


def build_command(
    gaea_path: str,
    terrain_file: str,
    *,
    profile: Optional[str] = None,
    region: Optional[str] = None,
    seed: Optional[int] = None,
    ignore_cache: bool = False,
    verbose: bool = False,
    variables: Optional[Dict[str, str]] = None,
    vars_file: Optional[str] = None,
) -> List[str]:
    """
    Construct a Gaea.Swarm command line.

    ``-v key:value`` variable pairs must come last per the Gaea CLI contract.
    """
    cmd: List[str] = [gaea_path, "--Filename", str(terrain_file)]
    if profile:
        cmd += ["--profile", profile]
    if region:
        cmd += ["--region", region]
    if seed is not None:
        cmd += ["--seed", str(int(seed))]
    if ignore_cache:
        cmd.append("--ignorecache")
    if verbose:
        cmd.append("--verbose")
    if vars_file:
        cmd += ["--vars", str(vars_file)]
    # Variables MUST be the trailing arguments.
    if variables:
        for key, value in variables.items():
            cmd += ["-v", f"{key}:{value}"]
    return cmd


def default_build_dir(terrain_file: Path, project_root: Optional[Path] = None) -> Path:
    """
    Resolve where Gaea Export nodes land.

    Preferred: ``{project}/.hephaestus_forge/gaea_builds/{terrain_stem}``.
    Fallback (no project): a ``Build`` folder beside the terrain file, which is
    Gaea's own default Build folder convention.
    """
    if project_root:
        return Path(project_root).resolve() / ".hephaestus_forge" / "gaea_builds" / terrain_file.stem
    return terrain_file.resolve().parent / "Build"


def ue_landscape_import_next_steps(
    result: "GaeaBuildResult",
    *,
    destination_path: str = "/Game/Hephaestus/Landscapes",
) -> List[str]:
    """Document the two-step Gaea → UE 5.8 landscape import for an operator."""
    steps: List[str] = []
    if result.heightmap:
        h = str(Path(result.heightmap)).replace("\\", "/")
        import_json = (
            '{"command":"landscape.import","params":{'
            f'"heightmap_path":"{h}",'
            f'"destination_path":"{destination_path}"'
            "}}"
        )
        steps.append(
            f"Stop PIE, then import height (editor Remote API :8765): forge command --json '{import_json}'"
        )
    else:
        steps.append(
            "No heightmap export detected — add an Export node named 'Height' (PNG16/EXR/R16)."
        )
    if result.masks:
        steps.append(
            f"Import {len(result.masks)} weightmap mask(s) as landscape paint layers "
            "(landscape.import_weightmap per mask)."
        )
    if result.textures:
        steps.append(
            f"Wire {len(result.textures)} surface texture(s) into the landscape material."
        )
    steps.append(
        "Then bind PCG vegetation/biomes to the painted layers (pcg.bind_vegetation)."
    )
    return steps


def build_terrain(
    terrain_file: str | Path,
    *,
    project_root: Optional[Path] = None,
    build_folder: Optional[str | Path] = None,
    profile: Optional[str] = None,
    region: Optional[str] = None,
    seed: Optional[int] = None,
    ignore_cache: bool = False,
    verbose: bool = False,
    variables: Optional[Dict[str, str]] = None,
    vars_file: Optional[str] = None,
    gaea_executable: Optional[str] = None,
    destination_path: str = "/Game/Hephaestus/Landscapes",
    timeout_seconds: int = 1800,
    _runner=subprocess.run,
) -> GaeaBuildResult:
    """
    Execute a Gaea terrain graph headlessly and classify its exports.

    Returns a :class:`GaeaBuildResult`. The build folder is scanned after the
    Swarm exits; produced rasters are classified into heightmap / masks /
    textures so a downstream UE landscape import knows what to consume.
    """
    terrain = Path(terrain_file)
    if terrain.suffix.lower() not in GAEA_GRAPH_EXTENSIONS:
        return GaeaBuildResult(
            success=False,
            terrain_file=str(terrain),
            error=(
                f"Unsupported Gaea graph {terrain.suffix!r}; "
                f"expected one of {GAEA_GRAPH_EXTENSIONS}"
            ),
        )
    if not terrain.is_file():
        return GaeaBuildResult(
            success=False,
            terrain_file=str(terrain),
            error=f"Gaea graph not found: {terrain}",
        )

    gaea_path, gaea_version = find_gaea(gaea_executable)
    if not gaea_path:
        return GaeaBuildResult(
            success=False,
            terrain_file=str(terrain),
            error=(
                "Gaea Build Swarm not found. Install Gaea 2, or set GAEA_SWARM "
                "to the full path of Gaea.Swarm.exe."
            ),
            next_steps=[
                "Install Gaea 2 from https://quadspinner.com/",
                "Set env GAEA_SWARM to <install>/Gaea.Swarm.exe",
                "Bind Export node OutputPath/Location so exports land in the build folder.",
            ],
        )

    out_dir = Path(build_folder) if build_folder else default_build_dir(terrain, project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot pre-existing files so we only classify freshly written exports.
    before = {p for p in out_dir.rglob("*") if p.is_file()}

    cmd = build_command(
        gaea_path,
        str(terrain),
        profile=profile,
        region=region,
        seed=seed,
        ignore_cache=ignore_cache,
        verbose=verbose,
        variables=variables,
        vars_file=vars_file,
    )

    try:
        proc = _runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return GaeaBuildResult(
            success=False,
            gaea_path=gaea_path,
            gaea_version=gaea_version,
            terrain_file=str(terrain),
            build_folder=str(out_dir),
            profile=profile,
            region=region,
            seed=seed,
            command=cmd,
            error=f"Gaea build timed out after {timeout_seconds}s",
        )
    except Exception as exc:  # pragma: no cover - defensive
        return GaeaBuildResult(
            success=False,
            gaea_path=gaea_path,
            gaea_version=gaea_version,
            terrain_file=str(terrain),
            build_folder=str(out_dir),
            command=cmd,
            error=str(exc),
        )

    after = {p for p in out_dir.rglob("*") if p.is_file()}
    produced = sorted(after - before, key=lambda p: p.name.lower())
    # If nothing is "new" (e.g. cache/overwrite), fall back to all images present.
    scan_set = produced if produced else sorted(after, key=lambda p: p.name.lower())
    heightmap, masks, textures, other = classify_outputs(scan_set)

    produced_any = bool(heightmap or masks or textures or other)
    success = proc.returncode == 0 and produced_any

    error: Optional[str] = None
    if not success:
        if proc.returncode != 0:
            error = f"Gaea Swarm exited with code {proc.returncode}"
        elif not produced_any:
            error = (
                f"Gaea Swarm reported success but no exports were found in {out_dir} — "
                "check Export node Location/OutputPath binding"
            )

    result = GaeaBuildResult(
        success=success,
        gaea_path=gaea_path,
        gaea_version=gaea_version,
        terrain_file=str(terrain),
        build_folder=str(out_dir),
        profile=profile,
        region=region,
        seed=seed,
        heightmap=heightmap,
        masks=masks,
        textures=textures,
        other_outputs=other,
        command=cmd,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        return_code=proc.returncode,
        error=error,
    )
    if success:
        result.next_steps = ue_landscape_import_next_steps(
            result, destination_path=destination_path
        )
    return result
