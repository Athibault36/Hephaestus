// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Audio/HephaestusAudioSubsystem.h"
#include "HephaestusBridge.h"

void UHephaestusAudioSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: Initialized (stub)"));
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
	UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayQuartzClock stub: %s"), *ClockHandle);
}

USoundWave* UHephaestusAudioSubsystem::SynthesizeAudio(const FString& SynthDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("SynthesizeAudio stub"));
	return nullptr;
}
