// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusAudioSubsystem.generated.h"

class UMetaSoundSource;
class USoundWave;

/** MetaSound patch description */
USTRUCT(BlueprintType)
struct FHephaestusMetaSoundDesc
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Name;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Nodes; // Node name -> node type/config

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> Connections; // "OutputNode.OutputPin -> InputNode.InputPin"

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Parameters; // Parameter name -> default value
};

/**
 * UHephaestusAudioSubsystem
 * 
 * MetaSound creation, Quartz clock management, audio synthesis.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusAudioSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Create MetaSound source from patch description */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
    UMetaSoundSource* CreateMetaSound(const FHephaestusMetaSoundDesc& PatchDesc);

    /** Play Quartz clock */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
    void PlayQuartzClock(const FString& ClockHandle, const FString& Timeline);

    /** Synthesize audio procedurally */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Audio")
    USoundWave* SynthesizeAudio(const FString& SynthDesc);
};