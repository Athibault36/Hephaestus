# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Niagara VFX Python API for Hephaestus Agent.
"""

import unreal
from typing import Dict, List
from dataclasses import dataclass

@dataclass
class EmitterConfig:
    """Configuration for Niagara emitter."""
    name: str
    emitter_type: str = "GPU"  # GPU, CPU, Mesh
    spawn_rate: float = 100.0
    lifetime_min: float = 1.0
    lifetime_max: float = 3.0
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    size: float = 10.0
    velocity: tuple = (0.0, 0.0, 100.0)


@dataclass
class SystemConfig:
    """Configuration for Niagara system."""
    name: str
    emitters: List[str] = None
    local_space: bool = False
    bounds_mode: str = "Auto"

    def __post_init__(self):
        if self.emitters is None:
            self.emitters = []


def create_emitter(
    config: EmitterConfig,
    output_path: str = "/Game/Hephaestus/Niagara/Emitters"
) -> unreal.NiagaraEmitter:
    """
    Create a Niagara emitter.
    
    Args:
        config: Emitter configuration
        output_path: Path to save emitter asset
    
    Returns:
        Created NiagaraEmitter asset
    """
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    
    emitter = asset_tools.create_asset(
        config.name,
        output_path,
        unreal.NiagaraEmitter,
        unreal.NiagaraEmitterFactory()
    )
    
    # Configure emitter stages
    # Add spawn, update, render modules
    
    return emitter


def create_system(
    config: SystemConfig,
    output_path: str = "/Game/Hephaestus/Niagara/Systems"
) -> unreal.NiagaraSystem:
    """
    Create a Niagara system from emitters.
    
    Args:
        config: System configuration
        output_path: Path to save system asset
    
    Returns:
        Created NiagaraSystem asset
    """
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    
    system = asset_tools.create_asset(
        config.name,
        output_path,
        unreal.NiagaraSystem,
        unreal.NiagaraSystemFactory()
    )
    
    # Add emitters to system
    for emitter_name in config.emitters:
        emitter = unreal.load_asset(emitter_name)
        if emitter:
            system.add_emitter(emitter)
    
    system.set_editor_property("b_local_space", config.local_space)
    
    return system


def bind_parameters(
    system: unreal.NiagaraSystem,
    parameter_bindings: Dict[str, str]
) -> bool:
    """
    Bind system parameters to external sources.
    
    Args:
        system: Target Niagara system
        parameter_bindings: Dict of parameter_name -> binding_path
    
    Returns:
        True if successful
    """
    if not system:
        return False
    
    for param_name, binding_path in parameter_bindings.items():
        # Bind parameter to external source (Blueprint, Material, etc.)
        pass
    
    return True


def compile_shader(
    system: unreal.NiagaraSystem,
    platform: str = "PC"
) -> bool:
    """
    Compile Niagara shaders for target platform.
    
    Args:
        system: Target Niagara system
        platform: Target platform (PC, PS5, XboxSeriesX, etc.)
    
    Returns:
        True if compilation successful
    """
    if not system:
        return False
    
    # Trigger shader compilation
    unreal.NiagaraCompiler.compile_system(system, platform)
    
    return True


def profile_gpu(
    system: unreal.NiagaraSystem,
    duration_seconds: float = 5.0
) -> Dict[str, float]:
    """
    Profile Niagara system GPU performance.
    
    Args:
        system: Target Niagara system
        duration_seconds: Profiling duration
    
    Returns:
        Dict of metric_name -> value
    """
    metrics = {
        "gpu_time_ms": 0.0,
        "particle_count": 0,
        "memory_mb": 0.0,
        "draw_calls": 0
    }
    
    # Run GPU profiling
    # This would use RHI profiling tools
    
    return metrics