// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusRenderingSubsystem.generated.h"

class FRDGBuilder;
class FRHICommandList;
class FShaderParameterStruct;

/** Render Graph pass description */
USTRUCT(BlueprintType)
struct FHephaestusRenderPassDesc
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString PassName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString ShaderPath;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Parameters;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> InputTextures;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> OutputTextures;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bIsComputePass = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FIntVector ComputeDispatchSize = FIntVector(1, 1, 1);
};

/**
 * UHephaestusRenderingSubsystem
 * 
 * Render Graph pass management, shader parameter structures, compute shader dispatch.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusRenderingSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Add a custom render graph pass */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
    bool AddRenderGraphPass(const FHephaestusRenderPassDesc& PassDesc);

    /** Create shader parameter struct */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
    FShaderParameterStruct* CreateShaderParameterStruct(const FString& StructName, const TMap<FString, FString>& Parameters);

    /** Execute compute shader */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
    bool ExecuteComputeShader(const FString& ShaderPath, const FIntVector& DispatchSize, const TMap<FString, FString>& Parameters);

    /** Get current scene renderer */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
    class FSceneRenderer* GetSceneRenderer() const;
};