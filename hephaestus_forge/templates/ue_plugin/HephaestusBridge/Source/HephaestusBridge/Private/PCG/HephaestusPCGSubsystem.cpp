// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "PCG/HephaestusPCGSubsystem.h"
#include "HephaestusBridge.h"

void UHephaestusPCGSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Initialized"));
}

void UHephaestusPCGSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

bool UHephaestusPCGSubsystem::MutatePCGGraph(UObject* Graph, const TArray<FHephaestusPCGMutation>& Mutations)
{
	if (!Graph)
	{
		return false;
	}
	if (Mutations.Num() == 0)
	{
		return true;
	}
	for (const FHephaestusPCGMutation& Mutation : Mutations)
	{
		UE_LOG(
			LogHephaestusBridge,
			Log,
			TEXT("MutatePCGGraph: %s on graph %s"),
			*Mutation.MutationType,
			*Graph->GetName());
	}
	return true;
}

void UHephaestusPCGSubsystem::SetMetadataParams(UObject* Component, const TMap<FString, FString>& Params)
{
	if (!Component)
	{
		return;
	}
	for (const TPair<FString, FString>& Pair : Params)
	{
		UE_LOG(LogHephaestusBridge, Log, TEXT("SetMetadataParams: %s=%s on %s"), *Pair.Key, *Pair.Value, *Component->GetName());
	}
}

FHephaestusPCGSpatialDataResult UHephaestusPCGSubsystem::QuerySpatialData(const FHephaestusPCGSpatialQuery& Query)
{
	FHephaestusPCGSpatialDataResult Result;
	const FVector Center = Query.Bounds.GetCenter();
	Result.Points.Add(Center);
	Result.Transforms.Add(FTransform(Center));
	Result.Metadata.Add(TEXT("source"), TEXT("pcg.query_spatial"));
	return Result;
}
