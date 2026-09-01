// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Audio/HephaestusAudioSubsystem.h"
#include "HephaestusBridge.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundWave.h"
#include "Engine/GameInstance.h"
#include "UObject/SoftObjectPath.h"

#if WITH_HEPHAESTUS_METASOUND
#include "MetasoundSource.h"
#endif

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
	FString SourcePath;
	if (const FString* Found = PatchDesc.Parameters.Find(TEXT("source_path")))
	{
		SourcePath = *Found;
	}
	if (SourcePath.IsEmpty() && PatchDesc.Name.StartsWith(TEXT("/")))
	{
		SourcePath = PatchDesc.Name;
	}

#if WITH_HEPHAESTUS_METASOUND
	if (!SourcePath.IsEmpty())
	{
		if (UObject* Loaded = FSoftObjectPath(SourcePath).TryLoad())
		{
			UE_LOG(
				LogHephaestusBridge,
				Log,
				TEXT("CreateMetaSound: loaded %s (%s)"),
				*SourcePath,
				*Loaded->GetClass()->GetName());
			return Loaded;
		}
		UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateMetaSound: source_path not found: %s"), *SourcePath);
		return nullptr;
	}

	UE_LOG(
		LogHephaestusBridge,
		Warning,
		TEXT("CreateMetaSound: provide source_path to an existing MetaSound asset (%s)"),
		*PatchDesc.Name);
	return nullptr;
#else
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateMetaSound: MetaSound module not linked (%s)"), *PatchDesc.Name);
	return nullptr;
#endif
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
	const FString Trimmed = SynthDesc.TrimStartAndEnd();
	if (Trimmed.StartsWith(TEXT("/")))
	{
		if (USoundWave* Wave = LoadObject<USoundWave>(nullptr, *Trimmed))
		{
			UE_LOG(LogHephaestusBridge, Log, TEXT("SynthesizeAudio: loaded %s"), *Trimmed);
			return Wave;
		}
	}
	UE_LOG(
		LogHephaestusBridge,
		Warning,
		TEXT("SynthesizeAudio: provide a /Game or /Engine SoundWave path (got: %s)"),
		*Trimmed);
	return nullptr;
}
