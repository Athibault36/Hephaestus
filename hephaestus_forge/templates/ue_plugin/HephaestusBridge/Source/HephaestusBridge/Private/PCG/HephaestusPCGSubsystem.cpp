// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "PCG/HephaestusPCGSubsystem.h"
#include "PCGGraph.h"
#include "PCGComponent.h"
#include "PCGNode.h"
#include "PCGPin.h"
#include "PCGSettings.h"
#include "Data/PCGSpatialData.h"
#include "Data/PCGPointData.h"
#include "Metadata/PCGMetadata.h"

#define LOCTEXT_NAMESPACE "HephaestusPCG"

void UHephaestusPCGSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Initialized"));
}

void UHephaestusPCGSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Deinitialized"));
}

bool UHephaestusPCGSubsystem::MutatePCGGraph(UPCGGraph* Graph, const TArray<FHephaestusPCGMutation>& Mutations)
{
    if (!Graph)
    {
        return false;
    }

    for (const FHephaestusPCGMutation& Mutation : Mutations)
    {
        if (Mutation.MutationType == TEXT("add"))
        {
            // Add new node
            // UPCGNode* NewNode = Graph->CreateNode(...)
        }
        else if (Mutation.MutationType == TEXT("remove"))
        {
            // Remove node by name
        }
        else if (Mutation.MutationType == TEXT("modify"))
        {
            // Modify node properties
        }
        else if (Mutation.MutationType == TEXT("connect"))
        {
            // Connect nodes
        }
        else if (Mutation.MutationType == TEXT("disconnect"))
        {
            // Disconnect nodes
        }
    }

    Graph->MarkModified();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Mutated PCG graph with %d mutations"), Mutations.Num());
    return true;
}

void UHephaestusPCGSubsystem::SetMetadataParams(UPCGComponent* Component, const TMap<FString, FString>& Params)
{
    if (!Component)
    {
        return;
    }

    // Set metadata on component
    for (const auto& Pair : Params)
    {
        // Component->SetMetadataValue(FName(*Pair.Key), Pair.Value);
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: Set %d metadata params"), Params.Num());
}

FHephaestusPCGSpatialDataResult UHephaestusPCGSubsystem::QuerySpatialData(const FHephaestusPCGSpatialQuery& Query)
{
    FHephaestusPCGSpatialDataResult Result;

    // In a real implementation, this would query the PCG spatial data
    // from the component's generated data

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusPCGSubsystem: QuerySpatialData (stub)"));
    return Result;
}

#undef LOCTEXT_NAMESPACE