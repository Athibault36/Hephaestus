// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusBlueprintSubsystem.generated.h"

class UBlueprint;

/** Function description for blueprint generation */
USTRUCT(BlueprintType)
struct FHephaestusFunctionDesc
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Name;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Category = TEXT("Hephaestus");

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Parameters; // Param name -> type

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString ReturnType = TEXT("void");

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString GraphDescription; // Natural language description of logic
};

/** Blueprint diff result */
USTRUCT(BlueprintType)
struct FHephaestusDiffResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite)
    bool bIdentical = false;

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> AddedNodes;

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> RemovedNodes;

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> ModifiedNodes;

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> AddedFunctions;

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> RemovedFunctions;
};

/**
 * UHephaestusBlueprintSubsystem
 * 
 * Blueprint compilation, function addition, property setting, and diffing.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusBlueprintSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Compile a blueprint */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Blueprints")
    bool CompileBlueprint(UBlueprint* Blueprint);

    /** Add a function to a blueprint */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Blueprints")
    bool AddFunctionToBlueprint(UBlueprint* Blueprint, const FHephaestusFunctionDesc& FunctionDesc);

    /** Set a blueprint property */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Blueprints")
    bool SetBlueprintProperty(UBlueprint* Blueprint, const FString& PropertyName, const FString& Value);

    /** Diff two blueprints */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Blueprints")
    FHephaestusDiffResult DiffBlueprints(UBlueprint* BlueprintA, UBlueprint* BlueprintB);
};