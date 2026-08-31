// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "HephaestusBridgeModule.h"
#include "HephaestusBridge.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogHephaestusBridge);

IMPLEMENT_MODULE(FHephaestusBridgeModule, HephaestusBridge)

void FHephaestusBridgeModule::StartupModule()
{
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Startup complete"));
}

void FHephaestusBridgeModule::ShutdownModule()
{
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBridge: Shutdown complete"));
}

FHephaestusBridgeModule& FHephaestusBridgeModule::Get()
{
	return FModuleManager::LoadModuleChecked<FHephaestusBridgeModule>("HephaestusBridge");
}

bool FHephaestusBridgeModule::IsAvailable()
{
	return FModuleManager::Get().IsModuleLoaded("HephaestusBridge");
}
