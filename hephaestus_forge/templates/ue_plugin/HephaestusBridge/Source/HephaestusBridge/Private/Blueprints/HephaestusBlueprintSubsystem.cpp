// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "HephaestusBridge.h"
#include "Engine/Blueprint.h"

#if WITH_EDITOR
#include "Kismet2/KismetEditorUtilities.h"
#endif

void UHephaestusBlueprintSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Initialized"));
}

void UHephaestusBlueprintSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

bool UHephaestusBlueprintSubsystem::CompileBlueprint(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return false;
	}
#if WITH_EDITOR
	FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::None);
	return Blueprint->Status != BS_Error;
#else
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CompileBlueprint requires editor build"));
	return false;
#endif
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
