// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusLandscapeSubsystem.generated.h"

/** Result of a landscape height / weightmap import. */
USTRUCT(BlueprintType)
struct FHephaestusLandscapeResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	bool bSuccess = false;

	/** Path of the created / targeted ALandscape actor. */
	UPROPERTY(BlueprintReadWrite)
	FString ActorPath;

	/** Heightmap/weightmap resolution actually imported. */
	UPROPERTY(BlueprintReadWrite)
	int32 SizeX = 0;

	UPROPERTY(BlueprintReadWrite)
	int32 SizeY = 0;

	/** Landscape layer that was painted (weightmap import). */
	UPROPERTY(BlueprintReadWrite)
	FString LayerName;

	UPROPERTY(BlueprintReadWrite)
	FString Error;
};

/**
 * UHephaestusLandscapeSubsystem
 *
 * Editor-only real UE Landscape height apply + weightmap → paint layer import.
 * Decodes a Gaea/heightmap raster (via ImageWrapper) and performs an actual
 * ALandscape::Import (height) or LandscapeEditorUtils::SetWeightmapData
 * (paint layer). Runtime (non-editor) builds return a clear error rather than
 * crashing.
 *
 * Requires the "Landscape" (runtime) and "LandscapeEditor" (editor) modules.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusLandscapeSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/**
	 * Create an ALandscape from a heightmap raster and apply real height data.
	 *
	 * @param HeightmapPath        Absolute path to a 16-bit grayscale height raster (PNG16/EXR/RAW).
	 * @param DestinationPath      Content path used for generated layer-info assets.
	 * @param LandscapeName        Optional actor label.
	 * @param SectionSize          Quads per section (e.g. 63).
	 * @param SectionsPerComponent 1, 2, or 4.
	 * @param Location             World location for the landscape actor.
	 * @param Scale                Landscape draw scale (default 100,100,100).
	 */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Landscape")
	FHephaestusLandscapeResult ImportHeightmap(
		const FString& HeightmapPath,
		const FString& DestinationPath,
		const FString& LandscapeName,
		int32 SectionSize,
		int32 SectionsPerComponent,
		FVector Location,
		FVector Scale);

	/**
	 * Import a mask raster as a landscape paint (weight) layer on an existing landscape.
	 *
	 * @param LandscapePath  Path of the target ALandscape actor.
	 * @param WeightmapPath  Absolute path to an 8-bit grayscale mask raster.
	 * @param LayerName      Paint layer name (created if missing when bCreateLayer).
	 * @param DestinationPath Content path used for the generated ULandscapeLayerInfoObject.
	 * @param bCreateLayer   Create the layer info asset if it does not exist.
	 */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Landscape")
	FHephaestusLandscapeResult ImportWeightmap(
		const FString& LandscapePath,
		const FString& WeightmapPath,
		const FString& LayerName,
		const FString& DestinationPath,
		bool bCreateLayer);

private:
	/** Decode a raster file to 16-bit grayscale samples. Returns false + error on failure. */
	bool DecodeHeightRaster(const FString& Path, TArray<uint16>& OutData, int32& OutSizeX, int32& OutSizeY, FString& OutError) const;

	/** Decode a raster file to 8-bit grayscale samples. Returns false + error on failure. */
	bool DecodeWeightRaster(const FString& Path, TArray<uint8>& OutData, int32& OutSizeX, int32& OutSizeY, FString& OutError) const;
};
