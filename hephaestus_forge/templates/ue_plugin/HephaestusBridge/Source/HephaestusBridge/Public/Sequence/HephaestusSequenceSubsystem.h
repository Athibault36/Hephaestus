// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusSequenceSubsystem.generated.h"

/**
 * Level Sequence + cinematic shot helpers for PIE agent goals.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusSequenceSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Play an existing Level Sequence asset by /Game path */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Sequence")
	bool PlayLevelSequence(const FString& SequencePath, bool bLoop = false);

	/** Stop the active level sequence player (if any) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Sequence")
	bool StopLevelSequence();

	/**
	 * Minimum-viable cinematic shot: animate camera to target view over DurationSeconds.
	 * Optionally moves an actor into frame via animation subsystem.
	 */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Sequence")
	bool CreateCameraShot(
		const FVector& TargetLocation,
		const FRotator& TargetRotation,
		float DurationSeconds = 4.f,
		const FString& ActorPath = TEXT(""),
		const FVector& ActorTargetLocation = FVector::ZeroVector,
		const FString& LookAtActorPath = TEXT(""));

private:
	UWorld* ResolveWorld() const;

	TWeakObjectPtr<class ALevelSequenceActor> ActiveSequenceActor;
};
