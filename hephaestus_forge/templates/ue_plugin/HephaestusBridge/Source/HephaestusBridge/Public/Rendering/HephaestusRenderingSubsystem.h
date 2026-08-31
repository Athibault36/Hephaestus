// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusRenderingSubsystem.generated.h"

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
 * Render Graph pass management and compute shader dispatch (stubs for now).
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

	/** Create a named shader parameter set (JSON/string stub) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
	FString CreateShaderParameterStruct(const FString& StructName, const TMap<FString, FString>& Parameters);

	/** Execute compute shader */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
	bool ExecuteComputeShader(const FString& ShaderPath, const FIntVector& DispatchSize, const TMap<FString, FString>& Parameters);

	/** Whether a scene renderer is currently available */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Rendering")
	bool HasSceneRenderer() const;
};
