// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusAnimationSubsystem.generated.h"

class UControlRig;
class UAnimSequence;
class USkeletalMesh;

/** Control Rig description */
USTRUCT(BlueprintType)
struct FHephaestusControlRigDesc
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Name;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    USkeletalMesh* SkeletalMesh;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> BoneMapping; // Source bone -> Target bone

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bUseFullBodyIK = true;
};

/**
 * UHephaestusAnimationSubsystem
 * 
 * Control Rig creation, animation retargeting, sequence editing, LiveLink.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusAnimationSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Create Control Rig for skeletal mesh */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
    UControlRig* CreateControlRig(USkeletalMesh* SkeletalMesh, const FHephaestusControlRigDesc& RigDesc);

    /** Retarget animation from source to target */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
    UAnimSequence* RetargetAnimation(UAnimSequence* Source, USkeletalMesh* Target, UControlRig* IKRig);

    /** Edit animation sequence */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
    bool EditSequence(UAnimSequence* Sequence, const TMap<FString, FString>& Edits);

    /** Connect to LiveLink subject */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Animation")
    bool LiveLinkConnect(const FString& SubjectName, const FString& Config);
};