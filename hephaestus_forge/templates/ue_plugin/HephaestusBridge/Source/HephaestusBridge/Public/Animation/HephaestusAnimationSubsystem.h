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
};
