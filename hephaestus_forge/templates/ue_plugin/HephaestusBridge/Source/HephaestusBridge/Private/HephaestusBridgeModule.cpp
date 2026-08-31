// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "HephaestusBridgeModule.h"
#include "Modules/ModuleManager.h"
#include "Subsystems/SubsystemManager.h"

DEFINE_LOG_CATEGORY(LogHephaestusBridge);

#define LOCTEXT_NAMESPACE "FHephaestusBridgeModule"

void FHephaestusBridgeModule::StartupModule()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Starting up..."));

    // Subsystems are auto-registered via UGameInstanceSubsystem
    // They will be created when a GameInstance is created

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Startup complete"));
}

void FHephaestusBridgeModule::ShutdownModule()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Shutting down..."));
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Shutdown complete"));
}

#undef LOCTEXT_NAMESPACE