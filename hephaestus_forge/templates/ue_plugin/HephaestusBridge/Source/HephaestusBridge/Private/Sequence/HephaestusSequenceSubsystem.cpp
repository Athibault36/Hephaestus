// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Sequence/HephaestusSequenceSubsystem.h"
#include "Animation/HephaestusAnimationSubsystem.h"
#include "World/HephaestusWorldSubsystem.h"
#include "HephaestusBridge.h"

#include "Engine/World.h"
#include "Engine/GameInstance.h"
#include "LevelSequence.h"
#include "LevelSequenceActor.h"
#include "LevelSequencePlayer.h"
#include "MovieSceneSequencePlayer.h"

void UHephaestusSequenceSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusSequenceSubsystem: Initialized"));
}

void UHephaestusSequenceSubsystem::Deinitialize()
{
	StopLevelSequence();
	Super::Deinitialize();
}

UWorld* UHephaestusSequenceSubsystem::ResolveWorld() const
{
	if (const UGameInstance* GI = GetGameInstance())
	{
		return GI->GetWorld();
	}
	return nullptr;
}

bool UHephaestusSequenceSubsystem::PlayLevelSequence(const FString& SequencePath, bool bLoop)
{
	if (SequencePath.IsEmpty())
	{
		return false;
	}

	UWorld* World = ResolveWorld();
	if (!World)
	{
		return false;
	}

	StopLevelSequence();

	ULevelSequence* Sequence = LoadObject<ULevelSequence>(nullptr, *SequencePath);
	if (!Sequence)
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayLevelSequence: failed to load %s"), *SequencePath);
		return false;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.ObjectFlags |= RF_Transient;
	ALevelSequenceActor* SeqActor = World->SpawnActor<ALevelSequenceActor>(
		ALevelSequenceActor::StaticClass(), FTransform::Identity, SpawnParams);
	if (!SeqActor)
	{
		return false;
	}

	SeqActor->SetSequence(Sequence);
	SeqActor->InitializePlayer();

	ULevelSequencePlayer* Player = SeqActor->GetSequencePlayer();
	if (!Player)
	{
		SeqActor->Destroy();
		return false;
	}

	FMovieSceneSequencePlaybackSettings Settings;
	Settings.bAutoPlay = false;
	Settings.LoopCount.Value = bLoop ? -1 : 0;
	Player->Initialize(Sequence, World, Settings);
	Player->Play();
	ActiveSequenceActor = SeqActor;
	return true;
}

bool UHephaestusSequenceSubsystem::StopLevelSequence()
{
	if (ActiveSequenceActor.IsValid())
	{
		if (ULevelSequencePlayer* Player = ActiveSequenceActor->GetSequencePlayer())
		{
			Player->Stop();
		}
		ActiveSequenceActor->Destroy();
		ActiveSequenceActor.Reset();
		return true;
	}
	return false;
}

bool UHephaestusSequenceSubsystem::CreateCameraShot(
	const FVector& TargetLocation,
	const FRotator& TargetRotation,
	float DurationSeconds,
	const FString& ActorPath,
	const FVector& ActorTargetLocation,
	const FString& LookAtActorPath,
	bool bEaseInOut)
{
	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}

	UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	if (!WorldSubsystem)
	{
		return false;
	}

	FRotator FinalRotation = TargetRotation;
	if (!LookAtActorPath.IsEmpty())
	{
		if (AActor* LookTarget = WorldSubsystem->FindActorByPath(LookAtActorPath))
		{
			const FVector ToTarget = LookTarget->GetActorLocation() - TargetLocation;
			if (!ToTarget.IsNearlyZero())
			{
				FinalRotation = ToTarget.Rotation();
				FinalRotation.Pitch -= 8.f;
			}
		}
	}

	const bool bCameraOk = WorldSubsystem->AnimateViewTo(TargetLocation, FinalRotation, DurationSeconds, bEaseInOut);
	bool bActorOk = true;
	if (!ActorPath.IsEmpty() && !ActorTargetLocation.IsNearlyZero())
	{
		if (UHephaestusAnimationSubsystem* Anim = GI->GetSubsystem<UHephaestusAnimationSubsystem>())
		{
			bActorOk = Anim->PlayTransformSequence(ActorPath, ActorTargetLocation, DurationSeconds);
		}
		else
		{
			bActorOk = false;
		}
	}

	return bCameraOk && bActorOk;
}
