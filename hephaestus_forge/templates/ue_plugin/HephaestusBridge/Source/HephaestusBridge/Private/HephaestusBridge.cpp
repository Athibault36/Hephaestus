// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "HephaestusBridge.h"
#include "Modules/ModuleManager.h"
#include "Subsystems/SubsystemManager.h"
#include "Engine/GameInstance.h"
#include "Engine/Engine.h"

#include "Vision/HephaestusVisionSubsystem.h"
#include "Command/HephaestusCommandHandler.h"
#include "World/HephaestusWorldSubsystem.h"
#include "Assets/HephaestusAssetSubsystem.h"
#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "Rendering/HephaestusRenderingSubsystem.h"
#include "PCG/HephaestusPCGSubsystem.h"
#include "Animation/HephaestusAnimationSubsystem.h"
#include "Audio/HephaestusAudioSubsystem.h"

DEFINE_LOG_CATEGORY(LogHephaestusBridge);

#define LOCTEXT_NAMESPACE "FHephaestusBridgeModule"

void FHephaestusBridgeModule::StartupModule()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Starting up..."));

    // Register all subsystems with the GameInstance
    if (GEngine)
    {
        // Subsystems are auto-registered via UGameInstanceSubsystem
        // but we can force initialization here if needed
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Engine available, subsystems will auto-register"));
    }

    // Initialize third-party libraries
#if WITH_TRT_LLM
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: TensorRT-LLM support enabled"));
#endif

#if WITH_LLAMA_CPP
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: llama.cpp support enabled"));
#endif

#if WITH_GRPC
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: gRPC support enabled"));
#endif

#if WITH_OPENCV
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: OpenCV support enabled"));
#endif

    bIsInitialized = true;
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Startup complete"));
}

void FHephaestusBridgeModule::ShutdownModule()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Shutting down..."));
    bIsInitialized = false;
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Shutdown complete"));
}

#undef LOCTEXT_NAMESPACE