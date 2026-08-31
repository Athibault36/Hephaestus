// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Engine/Texture2D.h"
#include "RenderGraph.h"
#include "RHI.h"
#include "PixelStreaming.h"
#include "HephaestusVisionSubsystem.generated.h"

// Forward declarations
class FHephaestusWebRTCStreamer;
class FHephaestusFrameEncoder;
struct FHephaestusVisionConfig;

/** Capture format options */
UENUM(BlueprintType)
enum class EHephaestusCaptureFormat : uint8
{
    /** Standard RGBA8 backbuffer */
    RGBA8,
    /** High dynamic range RGBA16F */
    RGBA16F,
    /** G-Buffer: Normal (RGB), Depth (A) */
    GBuffer_NormalDepth,
    /** G-Buffer: BaseColor (RGB), Roughness (A) */
    GBuffer_BaseColorRoughness,
    /** G-Buffer: Velocity (RG), Depth (B) */
    GBuffer_VelocityDepth,
    /** Full G-Buffer pack (Multiple render targets) */
    GBuffer_Full,
};

/** Streaming codec options */
UENUM(BlueprintType)
enum class EHephaestusStreamCodec : uint8
{
    H264,
    HEVC,
    AV1,
    VP9,
    /** Uncompressed raw frames via DataChannel */
    Raw_RGBA8,
    Raw_RGBA16F,
};

/** Vision subsystem configuration */
USTRUCT(BlueprintType)
struct FHephaestusVisionConfig
{
    GENERATED_BODY()

    /** Target capture resolution (width/height) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    FIntPoint CaptureResolution = FIntPoint(1920, 1080);

    /** Capture format */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    EHephaestusCaptureFormat CaptureFormat = EHephaestusCaptureFormat::RGBA16F;

    /** Target streaming FPS */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    int32 TargetFPS = 15;

    /** Streaming codec */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    EHephaestusStreamCodec StreamCodec = EHephaestusStreamCodec::H264;

    /** Bitrate in kbps */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    int32 BitrateKbps = 8000;

    /** Enable G-Buffer capture (requires Deferred Rendering) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    bool bCaptureGBuffer = true;

    /** Enable WebRTC streaming */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    bool bEnableWebRTC = true;

    /** WebRTC signaling server URL */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    FString SignalingURL = TEXT("ws://127.0.0.1:8081/signaling");

    /** Enable debug overlay injection */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    bool bEnableDebugOverlay = true;

    /** GPU readback latency budget (ms) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vision")
    float ReadbackTimeoutMs = 5.0f;

    /** Validate configuration */
    bool IsValid() const
    {
        return CaptureResolution.X > 0 && CaptureResolution.Y > 0 && TargetFPS > 0 && BitrateKbps > 0;
    }
};

/** Frame metadata for synchronization */
USTRUCT(BlueprintType)
struct FHephaestusFrameMetadata
{
    GENERATED_BODY()

    /** Monotonically increasing frame ID */
    UPROPERTY(BlueprintReadOnly)
    uint64 FrameID = 0;

    /** CPU timestamp when capture started (microseconds) */
    UPROPERTY(BlueprintReadOnly)
    int64 CaptureTimestampUs = 0;

    /** GPU timestamp when frame was presented (microseconds) */
    UPROPERTY(BlueprintReadOnly)
    int64 GPUTimestampUs = 0;

    /** Frame resolution */
    UPROPERTY(BlueprintReadOnly)
    FIntPoint Resolution;

    /** Capture format used */
    UPROPERTY(BlueprintReadOnly)
    EHephaestusCaptureFormat Format;

    /** Viewport world origin (for spatial alignment) */
    UPROPERTY(BlueprintReadOnly)
    FVector WorldOrigin;

    /** Viewport rotation (for spatial alignment) */
    UPROPERTY(BlueprintReadOnly)
    FRotator WorldRotation;

    /** Camera projection matrix */
    UPROPERTY(BlueprintReadOnly)
    FMatrix ProjectionMatrix;

    /** View matrix */
    UPROPERTY(BlueprintReadOnly)
    FMatrix ViewMatrix;

    /** Near/Far clip planes */
    UPROPERTY(BlueprintReadOnly)
    FVector2D ClipPlanes;

    /** Whether G-Buffer data is available */
    UPROPERTY(BlueprintReadOnly)
    bool bHasGBuffer = false;
};

/** Debug overlay data for injection into captured frames */
USTRUCT(BlueprintType)
struct FHephaestusDebugOverlay
{
    GENERATED_BODY()

    /** Bounding boxes: [x, y, w, h, r, g, b, a, label_hash] */
    UPROPERTY(BlueprintReadWrite)
    TArray<float> BoundingBoxes;

    /** Text labels: [x, y, r, g, b, a, size, text_hash] */
    UPROPERTY(BlueprintReadWrite)
    TArray<float> TextLabels;

    /** Lines: [x1, y1, x2, y2, r, g, b, a, thickness] */
    UPROPERTY(BlueprintReadWrite)
    TArray<float> Lines;

    /** Crosshairs/markers: [x, y, r, g, b, a, size, type] */
    UPROPERTY(BlueprintReadWrite)
    TArray<float> Markers;
};

/** Delegate for frame capture events */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnFrameCaptured, const FHephaestusFrameMetadata&, Metadata, UTexture2D*, Texture);

/** Delegate for streaming statistics */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnStreamStats, int32, CurrentFPS, int32, CurrentBitrateKbps, float, LatencyMs);

/**
 * UHephaestusVisionSubsystem
 * 
 * Captures UE5.8 viewport/backbuffer and G-Buffer passes at configurable resolution/FPS.
 * Supports GPU readback via RDG, hardware encoding (NVENC/AMF/QuickSync), and WebRTC streaming.
 * Provides debug overlay injection for agent visualization.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusVisionSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    // ~ UGameInstanceSubsystem interface
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    // ~ End UGameInstanceSubsystem interface

    /** Start viewport capture and streaming */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    bool StartCapture(const FHephaestusVisionConfig& InConfig);

    /** Stop viewport capture and streaming */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    void StopCapture();

    /** Check if currently capturing */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    bool IsCapturing() const { return bIsCapturing; }

    /** Get current configuration */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    FHephaestusVisionConfig GetConfig() const { return CurrentConfig; }

    /** Get latest captured frame metadata */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    FHephaestusFrameMetadata GetLatestFrameMetadata() const;

    /** Get latest captured texture (CPU readable) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    UTexture2D* GetLatestFrameTexture() const;

    /** Inject debug overlay for next frame */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    void InjectDebugOverlay(const FHephaestusDebugOverlay& Overlay);

    /** Capture a single frame on demand (for vision inference) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    bool CaptureSingleFrame(FHephaestusFrameMetadata& OutMetadata, UTexture2D*& OutTexture);

    /** Events */
    UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Vision")
    FOnFrameCaptured OnFrameCaptured;

    UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Vision")
    FOnStreamStats OnStreamStats;

    /** Get WebRTC streamer for advanced control */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Vision")
    class FHephaestusWebRTCStreamer* GetWebRTCStreamer();

protected:
    /** Internal: Called every frame to capture viewport */
    void CaptureViewport_RenderThread(FRDGBuilder& GraphBuilder);

    /** Internal: Process captured texture on render thread */
    void ProcessCapturedTexture_RenderThread(FRDGBuilder& GraphBuilder, FRHITexture* SourceTexture);

    /** Internal: Schedule GPU readback */
    void ScheduleGPUReadback(FRHITexture* Texture, uint64 FrameID);

    /** Internal: Handle GPU readback completion */
    void OnGPUReadbackComplete(uint64 FrameID, TArray64<uint8>&& Data);

    /** Internal: Encode and send frame via WebRTC */
    void EncodeAndStreamFrame(uint64 FrameID, const TArray64<uint8>& Data, const FHephaestusFrameMetadata& Metadata);

    /** Internal: Update streaming statistics */
    void UpdateStreamStats();

private:
    /** Current configuration */
    FHephaestusVisionConfig CurrentConfig;

    /** Capture state */
    bool bIsCapturing = false;
    uint64 FrameCounter = 0;

    /** Render target for capture */
    TRefCountPtr<IPooledRenderTarget> CaptureRenderTarget;

    /** G-Buffer render targets */
    TRefCountPtr<IPooledRenderTarget> GBufferNormalDepth;
    TRefCountPtr<IPooledRenderTarget> GBufferBaseColorRoughness;
    TRefCountPtr<IPooledRenderTarget> GBufferVelocityDepth;

    /** CPU-readable texture for readback */
    TRefCountPtr<FRHITexture2D> ReadbackTexture;

    /** WebRTC streamer */
    TUniquePtr<FHephaestusWebRTCStreamer> WebRTCStreamer;

    /** Frame encoder (NVENC/Software) */
    TUniquePtr<FHephaestusFrameEncoder> FrameEncoder;

    /** Latest frame data (thread-safe) */
    mutable FCriticalSection FrameDataLock;
    uint64 LatestFrameID = 0;
    TSharedPtr<FHephaestusFrameMetadata> LatestMetadata;
    TObjectPtr<UTexture2D> LatestTexture;

    /** Debug overlay for next frame */
    mutable FCriticalSection OverlayLock;
    FHephaestusDebugOverlay PendingOverlay;

    /** Statistics */
    double LastStatsUpdateTime = 0.0;
    int32 FramesSinceLastStats = 0;
    int32 CurrentFPS = 0;
    int32 CurrentBitrateKbps = 0;
    float AverageLatencyMs = 0.0f;

    /** RDG pass name */
    static FName CapturePassName;
};