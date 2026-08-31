// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusFrameEncoder.h"
#include "HAL/PlatformProcess.h"
#include "Misc/ScopeLock.h"

#define LOCTEXT_NAMESPACE "HephaestusEncoder"

FHephaestusFrameEncoder::FHephaestusFrameEncoder()
{
}

FHephaestusFrameEncoder::~FHephaestusFrameEncoder()
{
    Shutdown();
}

bool FHephaestusFrameEncoder::Initialize()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusFrameEncoder: Initializing..."));
    bInitialized = true;
    return true;
}

void FHephaestusFrameEncoder::Shutdown()
{
    if (HardwareEncoder)
    {
        // In real impl: destroy NVENC encoder
        HardwareEncoder = nullptr;
    }
    if (SoftwareEncoder)
    {
        // In real impl: destroy software encoder
        SoftwareEncoder = nullptr;
    }
    bInitialized = false;
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusFrameEncoder: Shutdown"));
}

bool FHephaestusFrameEncoder::Configure(const FHephaestusEncoderConfig& InConfig)
{
    if (!InConfig.IsValid())
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusFrameEncoder: Invalid config"));
        return false;
    }

    Config = InConfig;

    // Try hardware encoder first
    if (Config.bHardwareAccelerated)
    {
        bUsingHardware = CreateHardwareEncoder();
        if (!bUsingHardware)
        {
            UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusFrameEncoder: Hardware encoder unavailable, falling back to software"));
            bUsingHardware = false;
            CreateSoftwareEncoder();
        }
    }
    else
    {
        bUsingHardware = false;
        CreateSoftwareEncoder();
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusFrameEncoder: Configured - %s, %dx%d @ %d fps, %d kbps, HW=%s"),
        *UEnum::GetValueAsString(Config.Codec), Config.Width, Config.Height, Config.FPS, Config.BitrateKbps,
        bUsingHardware ? TEXT("Yes") : TEXT("No"));

    return true;
}

bool FHephaestusFrameEncoder::EncodeFrame(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData)
{
    if (!bInitialized)
    {
        return false;
    }

    double StartTime = FPlatformTime::Seconds();

    bool bSuccess = false;
    if (bUsingHardware)
    {
        bSuccess = EncodeHardware(InData, Width, Height, OutEncodedData);
    }
    else
    {
        bSuccess = EncodeSoftware(InData, Width, Height, OutEncodedData);
    }

    double EncodeTimeMs = (FPlatformTime::Seconds() - StartTime) * 1000.0;

    // Update stats
    {
        FScopeLock Lock(&StatsLock);
        Stats.FramesEncoded++;
        Stats.TotalBytesEncoded += OutEncodedData.Num();
        Stats.AverageEncodeTimeMs = (Stats.AverageEncodeTimeMs * (Stats.FramesEncoded - 1) + EncodeTimeMs) / Stats.FramesEncoded;

        if (!bSuccess)
        {
            Stats.FramesFailed++;
        }

        // Update bitrate calculation
        BytesSinceLastUpdate += OutEncodedData.Num();
        double Now = FPlatformTime::Seconds();
        if (Now - LastBitrateUpdate >= 1.0)
        {
            CurrentBitrateKbps = static_cast<int32>((BytesSinceLastUpdate * 8 / 1000) / (Now - LastBitrateUpdate));
            Stats.CurrentBitrateKbps = CurrentBitrateKbps;
            BytesSinceLastUpdate = 0;
            LastBitrateUpdate = Now;
        }
    }

    FrameCounter++;
    return bSuccess;
}

void FHephaestusFrameEncoder::ForceKeyFrame()
{
    bForceKeyFrame = true;
}

FHephaestusFrameEncoder::FStats FHephaestusFrameEncoder::GetStats() const
{
    FScopeLock Lock(&StatsLock);
    FStats Result = Stats;
    Result.CurrentBitrateKbps = CurrentBitrateKbps;
    return Result;
}

bool FHephaestusFrameEncoder::CreateHardwareEncoder()
{
    // In real implementation:
    // 1. Load nvenc library (nvEncodeAPI)
    // 2. Create NVENC session
    // 3. Configure encoder parameters (H.264/HEVC/AV1, bitrate, GOP, etc.)
    // 4. Allocate input/output buffers
    // 5. Register CUDA resources for zero-copy

    // For Windows/NVENC:
    // HMODULE nvencLib = LoadLibrary(TEXT("nvEncodeAPI64.dll"));
    // ... initialize NVENC

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusFrameEncoder: Hardware encoder creation (stub)"));
    return false; // Return false to trigger software fallback in stub
}

bool FHephaestusFrameEncoder::CreateSoftwareEncoder()
{
    // In real implementation:
    // 1. Initialize libx264 / FFmpeg (avcodec)
    // 2. Configure encoder context
    // 3. Allocate frames and packets

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusFrameEncoder: Software encoder creation (stub)"));
    return true; // Stub always succeeds
}

bool FHephaestusFrameEncoder::EncodeHardware(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData)
{
    // In real implementation:
    // 1. Map input texture to CUDA resource
    // 2. Submit frame to NVENC (nvEncEncodePicture)
    // 3. Wait for completion (nvEncLockBitstream)
    // 4. Copy bitstream to output array
    // 5. Unlock bitstream

    // Stub: just copy input as "encoded" data
    OutEncodedData.Append(InData.GetData(), InData.Num());
    return true;
}

bool FHephaestusFrameEncoder::EncodeSoftware(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData)
{
    // In real implementation:
    // 1. Convert input to YUV420P (sws_scale)
    // 2. Encode with libx264 / avcodec_send_frame
    // 3. Receive packets (avcodec_receive_packet)
    // 4. Copy to output array

    // Stub: just copy input as "encoded" data
    OutEncodedData.Append(InData.GetData(), InData.Num());
    return true;
}

#undef LOCTEXT_NAMESPACE