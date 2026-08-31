// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusPCGSubsystem.generated.h"

class UPCGGraph;
class UPCGComponent;

/** PCG graph mutation description */
USTRUCT(BlueprintType)
struct FHephaestusPCGMutation
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString NodeName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString MutationType; // "add", "remove", "modify", "connect", "disconnect"

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Properties; // Property changes

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString TargetNode; // For connect/disconnect
};

/** Spatial query for PCG */
USTRUCT(BlueprintType)
struct FHephaestusPCGSpatialQuery
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FBox Bounds;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> DataTypes; // Point, Mesh, Texture, etc.

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 MaxResults = 1000;
};

/** Spatial query result */
USTRUCT(BlueprintType)
struct FHephaestusPCGSpatialDataResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite)
    TArray<FVector> Points;

    UPROPERTY(BlueprintReadWrite)
    TArray<FTransform> Transforms;

    UPROPERTY(BlueprintReadWrite)
    TMap<FString, TArray<float>> Metadata; // Attribute name -> values
};

/**
 * UHephaestusPCGSubsystem
 * 
 * PCG graph mutation, metadata parameter setting, spatial data queries.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusPCGSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Mutate a PCG graph */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
    bool MutatePCGGraph(UPCGGraph* Graph, const TArray<FHephaestusPCGMutation>& Mutations);

    /** Set metadata parameters on PCG component */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
    void SetMetadataParams(UPCGComponent* Component, const TMap<FString, FString>& Params);

    /** Query spatial data from PCG */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
    FHephaestusPCGSpatialDataResult QuerySpatialData(const FHephaestusPCGSpatialQuery& Query);
};