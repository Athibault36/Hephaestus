// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#include "HephaestusBridge.generated.h"

/**
 * HephaestusBridge - Main plugin module for HEPHAESTUS agent integration.
 * Provides C++ subsystems for Vision, Command Handling, World Manipulation,
 * Asset Management, Blueprints, Rendering, PCG, Animation, and Audio.
 */
class FHephaestusBridgeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

    // Singleton access
    static FHephaestusBridgeModule& Get()
    {
        return FModuleManager::LoadModuleChecked<FHephaestusBridgeModule>("HephaestusBridge");
    }

    static bool IsAvailable()
    {
        return FModuleManager::Get().IsModuleLoaded("HephaestusBridge");
    }

private:
    // Module state
    bool bIsInitialized = false;
};