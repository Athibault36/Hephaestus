// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Audio/HephaestusAudioSubsystem.h"
#include "Sound/SoundWave.h"

#define LOCTEXT_NAMESPACE "HephaestusAudio"

void UHephaestusAudioSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: Initialized"));
}

void UHephaestusAudioSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: Deinitialized"));
}

UMetaSoundSource* UHephaestusAudioSubsystem::CreateMetaSound(const FHephaestusMetaSoundDesc& PatchDesc)
{
    // Stub until HEPHAESTUS_FULL_BUILD + MetaSoundEngine are available.
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: CreateMetaSound - %s (stub)"), *PatchDesc.Name);
    return nullptr;
}

void UHephaestusAudioSubsystem::PlayQuartzClock(const FString& ClockHandle, const FString& Timeline)
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: PlayQuartzClock - %s (stub)"), *ClockHandle);
}

USoundWave* UHephaestusAudioSubsystem::SynthesizeAudio(const FString& SynthDesc)
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAudioSubsystem: SynthesizeAudio (stub)"));
    return nullptr;
}

#undef LOCTEXT_NAMESPACE
