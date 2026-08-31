// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "HephaestusFrameEncoder.generated.h"

/** Encoder codec options */
UENUM(BlueprintType)
enum class EHephaestusEncoderCodec : uint8
{
    H264,
    HEVC,
    AV1,
    VP9,
    /** Software fallback */
    Software_H264,
    Software_HEVC,
};

/** Encoder configuration */
USTRUCT(BlueprintType)
struct FHephaestusEncoderConfig
{
    GENERATED_BODY()

    /** Video codec */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    EHephaestusEncoderCodec Codec = EHephaestusEncoderCodec::H264;

    /** Frame width */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 Width = 1920;

    /** Frame height */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 Height = 1080;

    /** Target bitrate in kbps */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 BitrateKbps = 8000;

    /** Target FPS */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 FPS = 15;

    /** GOP size (keyframe interval) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 GOPSize = 30;

    /** Use hardware acceleration (NVENC/AMF/QuickSync) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bHardwareAccelerated = true;

    /** Rate control mode */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bConstantBitrate = true;

    /** Quality preset (0=fastest, 10=best quality) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 QualityPreset = 4;

    /** Enable B-frames */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bEnableBFrames = false;

    /** Validate configuration */
    bool IsValid() const
    {
        return Width > 0 && Height > 0 && BitrateKbps > 0 && FPS > 0 && GOPSize > 0;
    }
};

/**
 * FHephaestusFrameEncoder
 * 
 * Hardware-accelerated video encoding (NVENC/AMF/QuickSync/VAAPI) with software fallback.
 * Encodes raw RGBA/BGRA frames to H.264/HEVC/AV1 for WebRTC streaming.
 */
class HEPHAESTUSBRIDGE_API FHephaestusFrameEncoder
{
public:
    FHephaestusFrameEncoder();
    ~FHephaestusFrameEncoder();

    /** Initialize encoder */
    bool Initialize();

    /** Shutdown encoder */
    void Shutdown();

    /** Configure encoder */
    bool Configure(const FHephaestusEncoderConfig& InConfig);

    /** Encode a single frame
     * @param InData Raw frame data (BGRA8, top-down)
     * @param Width Frame width
     * @param Height Frame height
     * @param OutEncodedData Output encoded bitstream
     * @return true on success */
    bool EncodeFrame(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData);

    /** Force next frame to be a keyframe */
    void ForceKeyFrame();

    /** Get current bitrate in kbps */
    int32 GetCurrentBitrateKbps() const { return CurrentBitrateKbps; }

    /** Get encoder stats */
    struct FStats
    {
        int32 FramesEncoded = 0;
        int32 FramesFailed = 0;
        int64 TotalBytesEncoded = 0;
        float AverageEncodeTimeMs = 0.0f;
        int32 CurrentBitrateKbps = 0;
    };
    FStats GetStats() const;

private:
    /** Internal: Create hardware encoder (NVENC) */
    bool CreateHardwareEncoder();

    /** Internal: Create software encoder (libx264/FFmpeg) */
    bool CreateSoftwareEncoder();

    /** Internal: Encode with hardware encoder */
    bool EncodeHardware(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData);

    /** Internal: Encode with software encoder */
    bool EncodeSoftware(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData);

    /** Configuration */
    FHephaestusEncoderConfig Config;

    /** Encoder state */
    bool bInitialized = false;
    bool bUsingHardware = false;

    /** Opaque encoder handles */
    void* HardwareEncoder = nullptr;
    void* SoftwareEncoder = nullptr;

    /** Frame counter */
    uint64 FrameCounter = 0;
    bool bForceKeyFrame = false;

    /** Statistics */
    mutable FCriticalSection StatsLock;
    FStats Stats;
    int32 CurrentBitrateKbps = 0;
    double LastBitrateUpdate = 0.0;
    int64 BytesSinceLastUpdate = 0;
};