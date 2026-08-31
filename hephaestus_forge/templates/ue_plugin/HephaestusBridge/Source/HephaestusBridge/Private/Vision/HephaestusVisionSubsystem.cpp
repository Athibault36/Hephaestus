// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusVisionSubsystem.h"
#include "Vision/HephaestusWebRTCStreamer.h"
#include "Vision/HephaestusFrameEncoder.h"
#include "HephaestusBridge.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Texture2D.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Modules/ModuleManager.h"
#include "TextureResource.h"
#include "UnrealClient.h"

void UHephaestusVisionSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	WebRTCStreamer = MakeUnique<FHephaestusWebRTCStreamer>();
	FrameEncoder = MakeUnique<FHephaestusFrameEncoder>();
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Initialized"));
}

void UHephaestusVisionSubsystem::Deinitialize()
{
	StopCapture();
	WebRTCStreamer.Reset();
	FrameEncoder.Reset();
	Super::Deinitialize();
}

bool UHephaestusVisionSubsystem::StartCapture(const FHephaestusVisionConfig& InConfig)
{
	if (!InConfig.IsValid())
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("StartCapture: invalid config"));
		return false;
	}

	CurrentConfig = InConfig;
	bIsCapturing = true;
	UE_LOG(LogHephaestusBridge, Log, TEXT("StartCapture @ %dx%d %dfps"),
		InConfig.CaptureResolution.X, InConfig.CaptureResolution.Y, InConfig.TargetFPS);
	return true;
}

void UHephaestusVisionSubsystem::StopCapture()
{
	bIsCapturing = false;
}

FHephaestusFrameMetadata UHephaestusVisionSubsystem::GetLatestFrameMetadata() const
{
	FScopeLock Lock(&FrameDataLock);
	return LatestMetadata;
}

UTexture2D* UHephaestusVisionSubsystem::GetLatestFrameTexture() const
{
	FScopeLock Lock(&FrameDataLock);
	return LatestTexture;
}

FString UHephaestusVisionSubsystem::GetLatestFramePath() const
{
	FScopeLock Lock(&FrameDataLock);
	return LatestFramePath;
}

void UHephaestusVisionSubsystem::InjectDebugOverlay(const FHephaestusDebugOverlay& Overlay)
{
	FScopeLock Lock(&OverlayLock);
	PendingOverlay = Overlay;
}

bool UHephaestusVisionSubsystem::CaptureSingleFrame(FHephaestusFrameMetadata& OutMetadata, UTexture2D*& OutTexture)
{
	OutTexture = nullptr;

	if (!GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport)
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("CaptureSingleFrame: no GameViewport"));
		return false;
	}

	FViewport* Viewport = GEngine->GameViewport->Viewport;
	TArray<FColor> Bitmap;
	if (!Viewport->ReadPixels(Bitmap) || Bitmap.Num() == 0)
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("CaptureSingleFrame: ReadPixels failed"));
		return false;
	}

	const FIntPoint Size = Viewport->GetSizeXY();
	if (Size.X <= 0 || Size.Y <= 0 || Bitmap.Num() < Size.X * Size.Y)
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("CaptureSingleFrame: invalid size %dx%d"), Size.X, Size.Y);
		return false;
	}

	// Flip vertically — ReadPixels is often bottom-up
	TArray<FColor> Flipped;
	Flipped.SetNumUninitialized(Bitmap.Num());
	for (int32 Y = 0; Y < Size.Y; ++Y)
	{
		const int32 SrcRow = (Size.Y - 1 - Y) * Size.X;
		const int32 DstRow = Y * Size.X;
		FMemory::Memcpy(Flipped.GetData() + DstRow, Bitmap.GetData() + SrcRow, Size.X * sizeof(FColor));
	}

	IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	TSharedPtr<IImageWrapper> PngWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
	if (!PngWrapper.IsValid() ||
		!PngWrapper->SetRaw(Flipped.GetData(), Flipped.Num() * sizeof(FColor), Size.X, Size.Y, ERGBFormat::BGRA, 8))
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("CaptureSingleFrame: PNG encode failed"));
		return false;
	}

	const TArray64<uint8> Compressed = PngWrapper->GetCompressed(100);
	const FString Dir = FPaths::ProjectSavedDir() / TEXT("Hephaestus");
	IFileManager::Get().MakeDirectory(*Dir, true);
	const FString Path = Dir / FString::Printf(TEXT("frame_%lld.png"), FrameCounter);

	if (!FFileHelper::SaveArrayToFile(Compressed, *Path))
	{
		UE_LOG(LogHephaestusBridge, Error, TEXT("CaptureSingleFrame: failed to write %s"), *Path);
		return false;
	}

	UTexture2D* Texture = UTexture2D::CreateTransient(Size.X, Size.Y, PF_B8G8R8A8);
	if (Texture)
	{
		Texture->SRGB = true;
		FTexture2DMipMap& Mip = Texture->GetPlatformData()->Mips[0];
		void* Data = Mip.BulkData.Lock(LOCK_READ_WRITE);
		FMemory::Memcpy(Data, Flipped.GetData(), Flipped.Num() * sizeof(FColor));
		Mip.BulkData.Unlock();
		Texture->UpdateResource();
	}

	FHephaestusFrameMetadata Meta;
	Meta.FrameID = FrameCounter;
	Meta.Resolution = FIntPoint(Size.X, Size.Y);
	Meta.CaptureTimestampUs = static_cast<int64>(FPlatformTime::Seconds() * 1e6);

	{
		FScopeLock Lock(&FrameDataLock);
		LatestMetadata = Meta;
		LatestTexture = Texture;
		LatestFramePath = Path;
		LatestFramePng = Compressed;
	}

	++FrameCounter;
	OutMetadata = Meta;
	OutTexture = Texture;

	OnFrameCaptured.Broadcast(Meta, Texture);
	UE_LOG(LogHephaestusBridge, Log, TEXT("CaptureSingleFrame: wrote %s (%dx%d)"), *Path, Size.X, Size.Y);
	return true;
}

FHephaestusWebRTCStreamer* UHephaestusVisionSubsystem::GetWebRTCStreamer()
{
	return WebRTCStreamer.Get();
}
