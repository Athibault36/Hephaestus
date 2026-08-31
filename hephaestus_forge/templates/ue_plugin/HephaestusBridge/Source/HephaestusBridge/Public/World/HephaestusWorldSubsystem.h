// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusWorldSubsystem.generated.h"

class AActor;
class UClass;

/**
 * UHephaestusWorldSubsystem
 * 
 * Provides world/actor manipulation capabilities to the agent.
 * Spawn, destroy, batch edit, spatial queries via octree.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusWorldSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Spawn an actor from class path */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    AActor* SpawnActor(const FString& ClassPath, const FTransform& Transform, const FActorSpawnParameters& SpawnParams = FActorSpawnParameters());

    /** Destroy an actor by path */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    bool DestroyActor(const FString& ActorPath, bool bNetForce = false);

    /** Batch edit multiple actors' properties */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    int32 BatchEditActors(const TArray<FString>& ActorPaths, const TMap<FString, FString>& PropertyEdits);

    /** Query actors within spatial bounds */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    TArray<AActor*> QuerySpatial(const FBox& Bounds, TSubclassOf<AActor> FilterClass = nullptr);

    /** Get asset registry */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    class IAssetRegistry& GetAssetRegistry();

    /** Find actor by path */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    AActor* FindActorByPath(const FString& ActorPath) const;

    /** Get all actors of class */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
    TArray<AActor*> GetAllActorsOfClass(TSubclassOf<AActor> ActorClass) const;

private:
    /** Resolve class from path */
    UClass* ResolveClass(const FString& ClassPath) const;
};