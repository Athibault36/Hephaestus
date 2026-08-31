// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Engine/Texture2D.h"
#include "HephaestusVisionSubsystem.generated.h"

class FHephaestusWebRTCStreamer;
class FHephaestusFrameEncoder;

UENUM(BlueprintType)
enum class EHephaestusCaptureFormat : uint8
{
	RGBA8,
	RGBA16F,
	GBuffer_NormalDepth,
	GBuffer_BaseColorRoughness,
	GBuffer_VelocityDepth,
	GBuffer_Full,
};

UENUM(BlueprintType)
enum class EHephaestusStreamCodec : uint8
{
	H264,
	HEVC,
	AV1,
	VP9,
	Raw_RGBA8,
	Raw_RGBA16F,
};

USTRUCT(BlueprintType)
struct FHephaestusVisionConfig
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	FIntPoint CaptureResolution = FIntPoint(1920, 1080);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	EHephaestusCaptureFormat CaptureFormat = EHephaestusCaptureFormat::RGBA16F;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	int32 TargetFPS = 15;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	EHephaestusStreamCodec StreamCodec = EHephaestusStreamCodec::H264;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	int32 BitrateKbps = 8000;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	bool bCaptureGBuffer = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	bool bEnableWebRTC = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	FString SignalingURL = TEXT("ws://127.0.0.1:8081/signaling");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	bool bEnableDebugOverlay = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
	float ReadbackTimeoutMs = 5.0f;

	bool IsValid() const
	{
		return CaptureResolution.X > 0 && CaptureResolution.Y > 0 && TargetFPS > 0 && BitrateKbps > 0;
	}
};

USTRUCT(BlueprintType)
struct FHephaestusFrameMetadata
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly)
	int64 FrameID = 0;

	UPROPERTY(BlueprintReadOnly)
	int64 CaptureTimestampUs = 0;

	UPROPERTY(BlueprintReadOnly)
	int64 GPUTimestampUs = 0;

	UPROPERTY(BlueprintReadOnly)
	FIntPoint Resolution = FIntPoint(0, 0);

	UPROPERTY(BlueprintReadOnly)
	EHephaestusCaptureFormat Format = EHephaestusCaptureFormat::RGBA8;

	UPROPERTY(BlueprintReadOnly)
	FVector WorldOrigin = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly)
	FRotator WorldRotation = FRotator::ZeroRotator;

	UPROPERTY(BlueprintReadOnly)
	FVector2D ClipPlanes = FVector2D(0.1f, 10000.f);

	UPROPERTY(BlueprintReadOnly)
	bool bHasGBuffer = false;

	FMatrix ProjectionMatrix = FMatrix::Identity;
	FMatrix ViewMatrix = FMatrix::Identity;
};

USTRUCT(BlueprintType)
struct FHephaestusDebugOverlay
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString Label;

	UPROPERTY(BlueprintReadWrite)
	FLinearColor Color = FLinearColor::Green;

	UPROPERTY(BlueprintReadWrite)
	TArray<FVector2D> Points;

	UPROPERTY(BlueprintReadWrite)
	bool bEnabled = true;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnFrameCaptured, const FHephaestusFrameMetadata&, Metadata, UTexture2D*, Texture);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnStreamStats, int32, CurrentFPS, int32, CurrentBitrateKbps, float, LatencyMs);

UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusVisionSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	bool StartCapture(const FHephaestusVisionConfig& InConfig);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	void StopCapture();

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	bool IsCapturing() const { return bIsCapturing; }

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	FHephaestusVisionConfig GetConfig() const { return CurrentConfig; }

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	FHephaestusFrameMetadata GetLatestFrameMetadata() const;

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	UTexture2D* GetLatestFrameTexture() const;

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	void InjectDebugOverlay(const FHephaestusDebugOverlay& Overlay);

	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	bool CaptureSingleFrame(FHephaestusFrameMetadata& OutMetadata, UTexture2D*& OutTexture);

	/** Absolute path of the last PNG written by CaptureSingleFrame (empty if none). */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
	FString GetLatestFramePath() const;

	/** Raw PNG bytes of the latest capture (for HTTP /v1/frame). */
	const TArray64<uint8>& GetLatestFramePng() const { return LatestFramePng; }

	UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Vision")
	FOnFrameCaptured OnFrameCaptured;

	UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Vision")
	FOnStreamStats OnStreamStats;

	FHephaestusWebRTCStreamer* GetWebRTCStreamer();

private:
	FHephaestusVisionConfig CurrentConfig;
	bool bIsCapturing = false;
	int64 FrameCounter = 0;

	TUniquePtr<FHephaestusWebRTCStreamer> WebRTCStreamer;
	TUniquePtr<FHephaestusFrameEncoder> FrameEncoder;

	mutable FCriticalSection FrameDataLock;
	FHephaestusFrameMetadata LatestMetadata;
	TObjectPtr<UTexture2D> LatestTexture;
	FString LatestFramePath;
	TArray64<uint8> LatestFramePng;

	mutable FCriticalSection OverlayLock;
	FHephaestusDebugOverlay PendingOverlay;
};
