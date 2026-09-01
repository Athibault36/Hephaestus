// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusAnimationSubsystem.generated.h"

class UAnimSequence;
class USkeletalMesh;

USTRUCT(BlueprintType)
struct FHephaestusControlRigDesc
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString Name;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TObjectPtr<USkeletalMesh> SkeletalMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TMap<FString, FString> BoneMapping;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	bool bUseFullBodyIK = true;
};

UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusAnimationSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Returns a ControlRig asset when ControlRig plugin integration is enabled */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	UObject* CreateControlRig(USkeletalMesh* SkeletalMesh, const FHephaestusControlRigDesc& RigDesc);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	UAnimSequence* RetargetAnimation(UAnimSequence* Source, USkeletalMesh* Target, UObject* IKRig);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool EditSequence(UAnimSequence* Sequence, const TMap<FString, FString>& Edits);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool LiveLinkConnect(const FString& SubjectName, const FString& Config);

	/** Spawn a skeletal mesh actor in PIE (default: Engine mannequin if path empty) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	AActor* SpawnSkeletalMeshActor(const FString& MeshPath, const FTransform& Transform, const FString& AnimBlueprintPath = TEXT(""));

	/** Play an anim sequence on a skeletal mesh actor by path */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool PlayAnimSequence(const FString& ActorPath, const FString& AnimPath, bool bLoop = true);

	/** Create a transient level sequence moving an actor to TargetLocation over DurationSeconds, then play */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool PlayTransformSequence(const FString& ActorPath, const FVector& TargetLocation, float DurationSeconds = 3.f);

	/** Whether a skeletal mesh actor is currently playing animation */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool IsActorAnimPlaying(const FString& ActorPath) const;

	/** Play an anim montage on a skeletal actor */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool PlayMontage(const FString& ActorPath, const FString& MontagePath, bool bLoop = false);

	/** Try project/engine fallback idle|walk|run anims when no explicit anim path is known */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool PlayLocomotionFallback(const FString& ActorPath, const FString& Mode, bool bLoop = true);

	/** Spawn a character with skeletal mesh (better for gameplay locomotion than mesh actor) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	AActor* SpawnLocomotionCharacter(const FString& MeshPath, const FTransform& Transform, const FString& AnimBlueprintPath = TEXT(""));

	/** Stop animation on a skeletal actor or character */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
	bool StopAnimation(const FString& ActorPath);

private:
	UWorld* ResolveWorld() const;

	UPROPERTY()
	TArray<FString> ConnectedLiveLinkSubjects;
};
