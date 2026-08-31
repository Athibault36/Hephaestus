// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusPCGSubsystem.generated.h"

USTRUCT(BlueprintType)
struct FHephaestusPCGMutation
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString NodeName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString MutationType;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TMap<FString, FString> Properties;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString TargetNode;
};

USTRUCT(BlueprintType)
struct FHephaestusPCGSpatialQuery
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FBox Bounds;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TArray<FString> DataTypes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	int32 MaxResults = 1000;
};

USTRUCT(BlueprintType)
struct FHephaestusPCGSpatialDataResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	TArray<FVector> Points;

	UPROPERTY(BlueprintReadWrite)
	TArray<FTransform> Transforms;

	UPROPERTY(BlueprintReadWrite)
	TMap<FString, FString> Metadata;
};

UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusPCGSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
	bool MutatePCGGraph(UObject* Graph, const TArray<FHephaestusPCGMutation>& Mutations);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
	void SetMetadataParams(UObject* Component, const TMap<FString, FString>& Params);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|PCG")
	FHephaestusPCGSpatialDataResult QuerySpatialData(const FHephaestusPCGSpatialQuery& Query);
};
