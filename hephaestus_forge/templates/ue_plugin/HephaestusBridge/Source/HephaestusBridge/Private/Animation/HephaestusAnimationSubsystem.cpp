// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Animation/HephaestusAnimationSubsystem.h"
#include "HephaestusBridge.h"

void UHephaestusAnimationSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Initialized (stub)"));
}

void UHephaestusAnimationSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

UObject* UHephaestusAnimationSubsystem::CreateControlRig(USkeletalMesh* SkeletalMesh, const FHephaestusControlRigDesc& RigDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateControlRig stub — ControlRig integration not linked yet (%s)"), *RigDesc.Name);
	return nullptr;
}

UAnimSequence* UHephaestusAnimationSubsystem::RetargetAnimation(UAnimSequence* Source, USkeletalMesh* Target, UObject* IKRig)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("RetargetAnimation stub"));
	return nullptr;
}

bool UHephaestusAnimationSubsystem::EditSequence(UAnimSequence* Sequence, const TMap<FString, FString>& Edits)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("EditSequence stub"));
	return false;
}

bool UHephaestusAnimationSubsystem::LiveLinkConnect(const FString& SubjectName, const FString& Config)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("LiveLinkConnect stub: %s"), *SubjectName);
	return false;
}
