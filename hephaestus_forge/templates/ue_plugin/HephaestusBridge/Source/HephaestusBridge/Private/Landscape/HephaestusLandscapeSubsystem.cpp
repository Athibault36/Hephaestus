// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Landscape/HephaestusLandscapeSubsystem.h"
#include "HephaestusBridge.h"

#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Modules/ModuleManager.h"

#if WITH_EDITOR
#include "Landscape.h"
#include "LandscapeProxy.h"
#include "LandscapeInfo.h"
#include "LandscapeLayerInfoObject.h"
#include "LandscapeEditorUtils.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "UObject/SavePackage.h"
#include "EngineUtils.h"
#endif

void UHephaestusLandscapeSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusLandscapeSubsystem: Initialized"));
}

void UHephaestusLandscapeSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

namespace
{
	EImageFormat DetectImageFormat(const FString& Path)
	{
		const FString Ext = FPaths::GetExtension(Path).ToLower();
		if (Ext == TEXT("png"))
		{
			return EImageFormat::PNG;
		}
		if (Ext == TEXT("exr"))
		{
			return EImageFormat::EXR;
		}
		if (Ext == TEXT("tif") || Ext == TEXT("tiff"))
		{
			return EImageFormat::TIFF;
		}
		if (Ext == TEXT("jpg") || Ext == TEXT("jpeg"))
		{
			return EImageFormat::JPEG;
		}
		return EImageFormat::Invalid;
	}
}

bool UHephaestusLandscapeSubsystem::DecodeHeightRaster(
	const FString& Path, TArray<uint16>& OutData, int32& OutSizeX, int32& OutSizeY, FString& OutError) const
{
	if (!FPaths::FileExists(Path))
	{
		OutError = FString::Printf(TEXT("heightmap not found: %s"), *Path);
		return false;
	}

	// Native .r16 / .raw: interpret as square 16-bit grayscale if possible.
	const FString Ext = FPaths::GetExtension(Path).ToLower();
	if (Ext == TEXT("r16") || Ext == TEXT("raw"))
	{
		TArray<uint8> Bytes;
		if (!FFileHelper::LoadFileToArray(Bytes, *Path) || Bytes.Num() < 2)
		{
			OutError = TEXT("failed to read raw heightmap bytes");
			return false;
		}
		const int32 SampleCount = Bytes.Num() / 2;
		const int32 Side = FMath::RoundToInt(FMath::Sqrt(static_cast<double>(SampleCount)));
		if (Side * Side != SampleCount)
		{
			OutError = TEXT("raw heightmap is not square — supply a PNG16/EXR with known dimensions");
			return false;
		}
		OutSizeX = Side;
		OutSizeY = Side;
		OutData.SetNumUninitialized(SampleCount);
		FMemory::Memcpy(OutData.GetData(), Bytes.GetData(), SampleCount * sizeof(uint16));
		return true;
	}

	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	const EImageFormat Format = DetectImageFormat(Path);
	if (Format == EImageFormat::Invalid)
	{
		OutError = FString::Printf(TEXT("unsupported heightmap format: %s"), *Path);
		return false;
	}
	TArray<uint8> Compressed;
	if (!FFileHelper::LoadFileToArray(Compressed, *Path))
	{
		OutError = TEXT("failed to read heightmap file");
		return false;
	}
	TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(Format);
	if (!Wrapper.IsValid() || !Wrapper->SetCompressed(Compressed.GetData(), Compressed.Num()))
	{
		OutError = TEXT("failed to decode heightmap image");
		return false;
	}
	OutSizeX = Wrapper->GetWidth();
	OutSizeY = Wrapper->GetHeight();

	TArray<uint8> Raw;
	if (!Wrapper->GetRaw(ERGBFormat::Gray, 16, Raw))
	{
		// Fall back to 8-bit grayscale, upscaled to 16-bit range.
		TArray<uint8> Raw8;
		if (!Wrapper->GetRaw(ERGBFormat::Gray, 8, Raw8))
		{
			OutError = TEXT("heightmap is not grayscale — export a 16-bit height channel");
			return false;
		}
		OutData.SetNumUninitialized(Raw8.Num());
		for (int32 i = 0; i < Raw8.Num(); ++i)
		{
			OutData[i] = static_cast<uint16>(Raw8[i]) << 8;
		}
		return true;
	}
	const int32 SampleCount = Raw.Num() / 2;
	OutData.SetNumUninitialized(SampleCount);
	FMemory::Memcpy(OutData.GetData(), Raw.GetData(), SampleCount * sizeof(uint16));
	return true;
}

bool UHephaestusLandscapeSubsystem::DecodeWeightRaster(
	const FString& Path, TArray<uint8>& OutData, int32& OutSizeX, int32& OutSizeY, FString& OutError) const
{
	if (!FPaths::FileExists(Path))
	{
		OutError = FString::Printf(TEXT("weightmap not found: %s"), *Path);
		return false;
	}
	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	const EImageFormat Format = DetectImageFormat(Path);
	if (Format == EImageFormat::Invalid)
	{
		OutError = FString::Printf(TEXT("unsupported weightmap format: %s"), *Path);
		return false;
	}
	TArray<uint8> Compressed;
	if (!FFileHelper::LoadFileToArray(Compressed, *Path))
	{
		OutError = TEXT("failed to read weightmap file");
		return false;
	}
	TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(Format);
	if (!Wrapper.IsValid() || !Wrapper->SetCompressed(Compressed.GetData(), Compressed.Num()))
	{
		OutError = TEXT("failed to decode weightmap image");
		return false;
	}
	OutSizeX = Wrapper->GetWidth();
	OutSizeY = Wrapper->GetHeight();
	if (!Wrapper->GetRaw(ERGBFormat::Gray, 8, OutData))
	{
		OutError = TEXT("weightmap is not 8-bit grayscale");
		return false;
	}
	return true;
}

FHephaestusLandscapeResult UHephaestusLandscapeSubsystem::ImportHeightmap(
	const FString& HeightmapPath,
	const FString& DestinationPath,
	const FString& LandscapeName,
	int32 SectionSize,
	int32 SectionsPerComponent,
	FVector Location,
	FVector Scale)
{
	FHephaestusLandscapeResult Result;

#if WITH_EDITOR
	if (GIsPlayInEditorWorld)
	{
		Result.Error = TEXT("landscape.import is disabled during PIE — stop Play and retry");
		return Result;
	}

	if (SectionSize <= 0)
	{
		SectionSize = 63;
	}
	if (SectionsPerComponent != 1 && SectionsPerComponent != 2)
	{
		SectionsPerComponent = 1;
	}
	if (Scale.IsNearlyZero())
	{
		Scale = FVector(100.0, 100.0, 100.0);
	}

	TArray<uint16> HeightData;
	int32 SizeX = 0, SizeY = 0;
	if (!DecodeHeightRaster(HeightmapPath, HeightData, SizeX, SizeY, Result.Error))
	{
		return Result;
	}
	if (HeightData.Num() != SizeX * SizeY)
	{
		Result.Error = FString::Printf(
			TEXT("decoded height sample count %d != %dx%d"), HeightData.Num(), SizeX, SizeY);
		return Result;
	}

	const int32 QuadsPerComponent = SectionSize * SectionsPerComponent;
	if (((SizeX - 1) % QuadsPerComponent) != 0 || ((SizeY - 1) % QuadsPerComponent) != 0)
	{
		Result.Error = FString::Printf(
			TEXT("heightmap %dx%d is not a valid landscape size for section %d x %d subsections "
				 "((size-1) must be divisible by %d)"),
			SizeX, SizeY, SectionSize, SectionsPerComponent, QuadsPerComponent);
		return Result;
	}

	UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
	if (!World)
	{
		Result.Error = TEXT("no editor world for landscape import");
		return Result;
	}

	ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator);
	if (!Landscape)
	{
		Result.Error = TEXT("failed to spawn ALandscape actor");
		return Result;
	}
	Landscape->SetActorScale3D(Scale);
	Landscape->bCanHaveLayersContent = true;
	const FGuid LandscapeGuid = FGuid::NewGuid();
	Landscape->SetLandscapeGuid(LandscapeGuid);
	if (!LandscapeName.IsEmpty())
	{
		Landscape->SetActorLabel(LandscapeName);
	}

	TMap<FGuid, TArray<uint16>> HeightDataPerLayer;
	HeightDataPerLayer.Add(FGuid(), MoveTemp(HeightData));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayer;
	MaterialLayerDataPerLayer.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());

	Landscape->Import(
		LandscapeGuid,
		0, 0,
		SizeX - 1, SizeY - 1,
		SectionsPerComponent,
		SectionSize,
		HeightDataPerLayer,
		nullptr,
		MaterialLayerDataPerLayer,
		ELandscapeImportAlphamapType::Additive);

	ULandscapeInfo* Info = Landscape->CreateLandscapeInfo();
	if (Info)
	{
		Info->UpdateLayerInfoMap(Landscape);
	}

	Result.bSuccess = true;
	Result.ActorPath = Landscape->GetPathName();
	Result.SizeX = SizeX;
	Result.SizeY = SizeY;
	return Result;
#else
	Result.Error = TEXT("landscape import requires an editor build of HephaestusBridge");
	return Result;
#endif
}

FHephaestusLandscapeResult UHephaestusLandscapeSubsystem::ImportWeightmap(
	const FString& LandscapePath,
	const FString& WeightmapPath,
	const FString& LayerName,
	const FString& DestinationPath,
	bool bCreateLayer)
{
	FHephaestusLandscapeResult Result;
	Result.LayerName = LayerName;

#if WITH_EDITOR
	if (GIsPlayInEditorWorld)
	{
		Result.Error = TEXT("landscape.import_weightmap is disabled during PIE — stop Play and retry");
		return Result;
	}
	if (LayerName.IsEmpty())
	{
		Result.Error = TEXT("layer_name required");
		return Result;
	}

	UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
	if (!World)
	{
		Result.Error = TEXT("no editor world for weightmap import");
		return Result;
	}

	// Resolve the target landscape actor by path (or first ALandscape in world).
	ALandscape* Landscape = nullptr;
	for (TActorIterator<ALandscape> It(World); It; ++It)
	{
		if (LandscapePath.IsEmpty() || It->GetPathName() == LandscapePath)
		{
			Landscape = *It;
			break;
		}
	}
	if (!Landscape)
	{
		Result.Error = FString::Printf(TEXT("landscape not found: %s"), *LandscapePath);
		return Result;
	}

	TArray<uint8> WeightData;
	int32 SizeX = 0, SizeY = 0;
	if (!DecodeWeightRaster(WeightmapPath, WeightData, SizeX, SizeY, Result.Error))
	{
		return Result;
	}
	Result.SizeX = SizeX;
	Result.SizeY = SizeY;

	// Create (or load) the layer info asset backing this paint layer.
	const FString Package = FString::Printf(
		TEXT("%s/LI_%s"),
		*(DestinationPath.IsEmpty() ? FString(TEXT("/Game/Hephaestus/Landscapes")) : DestinationPath),
		*LayerName);
	ULandscapeLayerInfoObject* LayerInfo = LoadObject<ULandscapeLayerInfoObject>(nullptr, *Package);
	if (!LayerInfo && bCreateLayer)
	{
		UPackage* Pkg = CreatePackage(*Package);
		if (Pkg)
		{
			LayerInfo = NewObject<ULandscapeLayerInfoObject>(
				Pkg, FName(*FString::Printf(TEXT("LI_%s"), *LayerName)), RF_Public | RF_Standalone);
			LayerInfo->LayerName = FName(*LayerName);
			FAssetRegistryModule::AssetCreated(LayerInfo);
			LayerInfo->MarkPackageDirty();
		}
	}
	if (!LayerInfo)
	{
		Result.Error = FString::Printf(TEXT("layer info asset missing: %s (set create_layer)"), *Package);
		return Result;
	}

	if (!LandscapeEditorUtils::SetWeightmapData(Landscape, LayerInfo, WeightData))
	{
		Result.Error = TEXT("SetWeightmapData failed (resolution mismatch with landscape?)");
		return Result;
	}

	Result.bSuccess = true;
	Result.ActorPath = Landscape->GetPathName();
	return Result;
#else
	Result.Error = TEXT("weightmap import requires an editor build of HephaestusBridge");
	return Result;
#endif
}
