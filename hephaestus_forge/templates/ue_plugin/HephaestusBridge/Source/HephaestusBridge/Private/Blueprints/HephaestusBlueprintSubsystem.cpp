// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "HephaestusBridge.h"
#include "Engine/Blueprint.h"

void UHephaestusBlueprintSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Initialized (stub)"));
}

void UHephaestusBlueprintSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

bool UHephaestusBlueprintSubsystem::CompileBlueprint(UBlueprint* Blueprint)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CompileBlueprint stub"));
	return Blueprint != nullptr;
}

bool UHephaestusBlueprintSubsystem::AddFunctionToBlueprint(UBlueprint* Blueprint, const FHephaestusFunctionDesc& FunctionDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("AddFunctionToBlueprint stub: %s"), *FunctionDesc.Name);
	return false;
}

bool UHephaestusBlueprintSubsystem::SetBlueprintProperty(UBlueprint* Blueprint, const FString& PropertyName, const FString& Value)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("SetBlueprintProperty stub: %s=%s"), *PropertyName, *Value);
	return false;
}

FHephaestusDiffResult UHephaestusBlueprintSubsystem::DiffBlueprints(UBlueprint* BlueprintA, UBlueprint* BlueprintB)
{
	FHephaestusDiffResult Result;
	Result.bIdentical = (BlueprintA == BlueprintB);
	return Result;
}
