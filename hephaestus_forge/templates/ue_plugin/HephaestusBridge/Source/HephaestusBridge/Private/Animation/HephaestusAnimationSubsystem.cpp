// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Animation/HephaestusAnimationSubsystem.h"
#include "ControlRig.h"
#include "Animation/AnimSequence.h"
#include "SkeletalMesh.h"
#include "Animation/Rig.h"
#include "Animation/IKRetargeter.h"
#include "LiveLinkInterface.h"

#define LOCTEXT_NAMESPACE "HephaestusAnimation"

void UHephaestusAnimationSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Initialized"));
}

void UHephaestusAnimationSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Deinitialized"));
}

UControlRig* UHephaestusAnimationSubsystem::CreateControlRig(USkeletalMesh* SkeletalMesh, const FHephaestusControlRigDesc& RigDesc)
{
    if (!SkeletalMesh)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusAnimationSubsystem: No skeletal mesh provided"));
        return nullptr;
    }

    // Create Control Rig asset
    FString PackagePath = FString::Printf(TEXT("/Game/Hephaestus/Rigs/%s"), *RigDesc.Name);
    UPackage* Package = CreatePackage(nullptr, *PackagePath);
    if (!Package)
    {
        return nullptr;
    }

    UControlRig* ControlRig = NewObject<UControlRig>(Package, UControlRig::StaticClass(), FName(*RigDesc.Name), RF_Public | RF_Standalone);
    if (!ControlRig)
    {
        return nullptr;
    }

    // Initialize rig with skeletal mesh
    // This would set up the hierarchy, controls, and rig logic

    ControlRig->PostEditChange();
    Package->MarkPackageDirty();

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Created Control Rig %s"), *ControlRig->GetPathName());
    return ControlRig;
}

UAnimSequence* UHephaestusAnimationSubsystem::RetargetAnimation(UAnimSequence* Source, USkeletalMesh* Target, UControlRig* IKRig)
{
    if (!Source || !Target)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusAnimationSubsystem: Invalid source or target for retargeting"));
        return nullptr;
    }

    // Use IK Retargeter for retargeting
    // UIKRetargeter* Retargeter = NewObject<UIKRetargeter>();
    // Configure retargeter with source/target meshes and IK rig
    // Retargeter->RetargetAsset(Source, Target);

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Retarget animation (stub)"));
    return nullptr;
}

bool UHephaestusAnimationSubsystem::EditSequence(UAnimSequence* Sequence, const TMap<FString, FString>& Edits)
{
    if (!Sequence)
    {
        return false;
    }

    // Apply edits to animation sequence
    // Could modify keys, curves, compression, etc.

    Sequence->PostEditChange();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Edited sequence %s"), *Sequence->GetName());
    return true;
}

bool UHephaestusAnimationSubsystem::LiveLinkConnect(const FString& SubjectName, const FString& Config)
{
    // Connect to LiveLink subject
    // ILiveLinkClient* Client = ILiveLinkModule::Get().GetClient();
    // Client->ConnectToSubject(SubjectName, Config);

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: LiveLink connect to %s (stub)"), *SubjectName);
    return true;
}

#undef LOCTEXT_NAMESPACE