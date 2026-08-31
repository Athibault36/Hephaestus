// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusAudioSubsystem.generated.h"

class USoundWave;

USTRUCT(BlueprintType)
struct FHephaestusMetaSoundDesc
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString Name;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TMap<FString, FString> Nodes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TArray<FString> Connections;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TMap<FString, FString> Parameters;
};

UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusAudioSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Returns a MetaSound asset when MetaSound plugin integration is enabled */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
	UObject* CreateMetaSound(const FHephaestusMetaSoundDesc& PatchDesc);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
	void PlayQuartzClock(const FString& ClockHandle, const FString& Timeline);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
	USoundWave* SynthesizeAudio(const FString& SynthDesc);
};
