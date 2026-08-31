// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "PCG/HephaestusPCGSubsystem.h"
#include "HephaestusBridge.h"

void UHephaestusPCGSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Initialized (stub)"));
}

void UHephaestusPCGSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

bool UHephaestusPCGSubsystem::MutatePCGGraph(UObject* Graph, const TArray<FHephaestusPCGMutation>& Mutations)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("MutatePCGGraph stub (%d mutations)"), Mutations.Num());
	return false;
}

void UHephaestusPCGSubsystem::SetMetadataParams(UObject* Component, const TMap<FString, FString>& Params)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("SetMetadataParams stub (%d params)"), Params.Num());
}

FHephaestusPCGSpatialDataResult UHephaestusPCGSubsystem::QuerySpatialData(const FHephaestusPCGSpatialQuery& Query)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("QuerySpatialData stub"));
	return FHephaestusPCGSpatialDataResult();
}
