// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusWorldSubsystem.generated.h"

class AActor;
class UClass;
class IAssetRegistry;

/**
 * UHephaestusWorldSubsystem
 *
 * Provides world/actor manipulation capabilities to the agent.
 * Spawn, destroy, batch edit, spatial queries.
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
	AActor* SpawnActor(const FString& ClassPath, const FTransform& Transform);

	/** Spawn a StaticMeshActor and assign a mesh (default: Engine cube) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	AActor* SpawnStaticMeshActor(const FString& MeshPath, const FTransform& Transform);

	/** Destroy an actor by path */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool DestroyActor(const FString& ActorPath, bool bNetForce = false);

	/** Batch edit multiple actors' properties */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	int32 BatchEditActors(const TArray<FString>& ActorPaths, const TMap<FString, FString>& PropertyEdits);

	/** Query actors within spatial bounds */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	TArray<AActor*> QuerySpatial(const FBox& Bounds, TSubclassOf<AActor> FilterClass = nullptr);

	/** Find actor by path */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	AActor* FindActorByPath(const FString& ActorPath) const;

	/** Get all actors of class */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	TArray<AActor*> GetAllActorsOfClass(TSubclassOf<AActor> ActorClass) const;

	/** List actor paths currently in the world (optionally filter by class path) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	TArray<FString> ListActors(const FString& ClassPathFilter = TEXT("")) const;

	/** Set world transform on an existing actor (by path or short name) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool SetActorTransform(const FString& ActorPath, const FTransform& Transform);

	/** Set PointLight intensity / color / radius (no-op if actor is not a point light) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool SetPointLightProperties(const FString& ActorPath, float Intensity, const FLinearColor& Color, float AttenuationRadius = 1000.f);

	/** Player / PIE camera location + forward (for in-view spawns) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool GetView(FVector& OutLocation, FRotator& OutRotation, FVector& OutForward) const;

	/** Move the player pawn + control rotation (simple cinematic framing) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool SetView(const FVector& Location, const FRotator& Rotation) const;

	/** Smoothly animate camera/pawn view to a target over DurationSeconds */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool AnimateViewTo(
		const FVector& TargetLocation,
		const FRotator& TargetRotation,
		float DurationSeconds = 4.f,
		bool bEaseInOut = true);

	/** Tint a StaticMeshActor with a readable MID color */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool SetStaticMeshColor(const FString& ActorPath, const FLinearColor& Color);

	/** Serialize actor state to JSON for planner verification */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool DescribeActor(const FString& ActorPath, FString& OutJson) const;

	/** Apply movement input to the possessed pawn for DurationSeconds (gameplay locomotion) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool ApplyMoveInput(float Forward, float Right, float DurationSeconds = 2.f);

	/** JSON snapshot of possessed pawn velocity/location */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|World")
	bool GetPawnStateJson(FString& OutJson) const;

	/** Native (non-UHT) asset registry access */
	IAssetRegistry& GetAssetRegistry();

private:
	UClass* ResolveClass(const FString& ClassPath) const;
	UWorld* ResolveWorld() const;
	bool IsSpawnClassAllowed(const FString& ClassPath, UClass* Resolved) const;
};
