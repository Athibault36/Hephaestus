// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Audio/HephaestusAudioSubsystem.h"
#include "HephaestusBridge.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "Engine/GameInstance.h"

void UHephaestusAudioSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: Initialized"));
}

void UHephaestusAudioSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

UObject* UHephaestusAudioSubsystem::CreateMetaSound(const FHephaestusMetaSoundDesc& PatchDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateMetaSound stub — MetaSound integration not linked yet (%s)"), *PatchDesc.Name);
	return nullptr;
}

void UHephaestusAudioSubsystem::PlayQuartzClock(const FString& ClockHandle, const FString& Timeline)
{
	UWorld* World = nullptr;
	if (UGameInstance* GI = GetGameInstance())
	{
		World = GI->GetWorld();
	}
	if (!World)
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayQuartzClock: no world (%s / %s)"), *ClockHandle, *Timeline);
		return;
	}
	if (USoundBase* TestCue = LoadObject<USoundBase>(
			nullptr,
			TEXT("/Engine/EditorSounds/Notifications/CompileSuccess_Cue.CompileSuccess_Cue")))
	{
		UGameplayStatics::PlaySound2D(World, TestCue);
		UE_LOG(LogHephaestusBridge, Log, TEXT("PlayQuartzClock: played test cue for clock=%s"), *ClockHandle);
	}
	else
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayQuartzClock: test cue not found"));
	}
}

USoundWave* UHephaestusAudioSubsystem::SynthesizeAudio(const FString& SynthDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("SynthesizeAudio stub"));
	return nullptr;
}
