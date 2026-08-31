// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusVisionSubsystem.h"
#include "Vision/HephaestusWebRTCStreamer.h"
#include "Vision/HephaestusFrameEncoder.h"

#include "Engine/GameInstance.h"
#include "Engine/Texture2D.h"
#include "RenderGraph.h"
#include "RenderGraphUtils.h"
#include "RHI.h"
#include "RHICommandList.h"
#include "RHIResources.h"
#include "RenderTargetPool.h"
#include "SceneView.h"
#include "SceneRenderer.h"
#include "DeferredShadingRenderer.h"
#include "PipelineStateCache.h"
#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "TextureResource.h"
#include "Engine/Engine.h"
#include "Async/Async.h"
#include "Misc/ScopeLock.h"
#include "HAL/PlatformTime.h"

#define LOCTEXT_NAMESPACE "HephaestusVision"

FName UHephaestusVisionSubsystem::CapturePassName = FName(TEXT("HephaestusCapturePass"));

void UHephaestusVisionSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Initializing..."));

    // Initialize frame encoder
    FrameEncoder = MakeUnique<FHephaestusFrameEncoder>();
    if (!FrameEncoder->Initialize())
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusVisionSubsystem: Frame encoder initialization failed"));
    }

    // Initialize WebRTC streamer
    WebRTCStreamer = MakeUnique<FHephaestusWebRTCStreamer>();
    if (!WebRTCStreamer->Initialize())
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusVisionSubsystem: WebRTC streamer initialization failed"));
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Initialized"));
}

void UHephaestusVisionSubsystem::Deinitialize()
{
    StopCapture();

    WebRTCStreamer.Reset();
    FrameEncoder.Reset();

    Super::Deinitialize();

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Deinitialized"));
}

bool UHephaestusVisionSubsystem::StartCapture(const FHephaestusVisionConfig& InConfig)
{
    if (bIsCapturing)
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusVisionSubsystem: Already capturing"));
        return false;
    }

    if (!InConfig.IsValid())
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusVisionSubsystem: Invalid config"));
        return false;
    }

    CurrentConfig = InConfig;
    FrameCounter = 0;
    bIsCapturing = true;
    LastStatsUpdateTime = FPlatformTime::Seconds();
    FramesSinceLastStats = 0;

    // Register render callback
    ENQUEUE_RENDER_COMMAND(HephaestusVision_RegisterCapture)(
        [this](FRHICommandListImmediate& RHICmdList)
        {
            // Register our capture pass with the renderer
            FSceneRenderer::OnPostRenderFrameDelegate.AddRaw(this, &UHephaestusVisionSubsystem::CaptureViewport_RenderThread);
        });

    // Configure WebRTC if enabled
    if (CurrentConfig.bEnableWebRTC && WebRTCStreamer)
    {
        FHephaestusWebRTCConfig WebRTCConfig;
        WebRTCConfig.SignalingURL = CurrentConfig.SignalingURL;
        WebRTCConfig.VideoCodec = [this]() -> EHephaestusVideoCodec
        {
            switch (CurrentConfig.StreamCodec)
            {
                case EHephaestusStreamCodec::H264: return EHephaestusVideoCodec::H264;
                case EHephaestusStreamCodec::HEVC: return EHephaestusVideoCodec::HEVC;
                case EHephaestusStreamCodec::AV1: return EHephaestusVideoCodec::AV1;
                case EHephaestusStreamCodec::VP9: return EHephaestusVideoCodec::VP9;
                default: return EHephaestusVideoCodec::H264;
            }
        }();
        WebRTCConfig.BitrateKbps = CurrentConfig.BitrateKbps;
        WebRTCConfig.Width = CurrentConfig.CaptureResolution.X;
        WebRTCConfig.Height = CurrentConfig.CaptureResolution.Y;
        WebRTCConfig.FPS = CurrentConfig.TargetFPS;

        WebRTCStreamer->Configure(WebRTCConfig);
        WebRTCStreamer->Connect();
    }

    // Configure frame encoder
    if (FrameEncoder)
    {
        FHephaestusEncoderConfig EncoderConfig;
        EncoderConfig.Codec = CurrentConfig.StreamCodec;
        EncoderConfig.Width = CurrentConfig.CaptureResolution.X;
        EncoderConfig.Height = CurrentConfig.CaptureResolution.Y;
        EncoderConfig.BitrateKbps = CurrentConfig.BitrateKbps;
        EncoderConfig.FPS = CurrentConfig.TargetFPS;
        EncoderConfig.bHardwareAccelerated = true; // Prefer NVENC/AMF

        FrameEncoder->Configure(EncoderConfig);
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Capture started at %dx%d @ %d FPS"),
        CurrentConfig.CaptureResolution.X, CurrentConfig.CaptureResolution.Y, CurrentConfig.TargetFPS);

    return true;
}

void UHephaestusVisionSubsystem::StopCapture()
{
    if (!bIsCapturing)
    {
        return;
    }

    bIsCapturing = false;

    // Unregister render callback
    ENQUEUE_RENDER_COMMAND(HephaestusVision_UnregisterCapture)(
        [this](FRHICommandListImmediate& RHICmdList)
        {
            FSceneRenderer::OnPostRenderFrameDelegate.RemoveAll(this);
        });

    // Stop WebRTC
    if (WebRTCStreamer)
    {
        WebRTCStreamer->Disconnect();
    }

    // Release render targets
    CaptureRenderTarget.SafeRelease();
    GBufferNormalDepth.SafeRelease();
    GBufferBaseColorRoughness.SafeRelease();
    GBufferVelocityDepth.SafeRelease();
    ReadbackTexture.SafeRelease();

    // Clear latest frame
    {
        FScopeLock Lock(&FrameDataLock);
        LatestFrameID = 0;
        LatestMetadata.Reset();
        LatestTexture = nullptr;
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusVisionSubsystem: Capture stopped"));
}

FHephaestusFrameMetadata UHephaestusVisionSubsystem::GetLatestFrameMetadata() const
{
    FScopeLock Lock(&FrameDataLock);
    if (LatestMetadata.IsValid())
    {
        return *LatestMetadata;
    }
    return FHephaestusFrameMetadata();
}

UTexture2D* UHephaestusVisionSubsystem::GetLatestFrameTexture() const
{
    FScopeLock Lock(&FrameDataLock);
    return LatestTexture.Get();
}

void UHephaestusVisionSubsystem::InjectDebugOverlay(const FHephaestusDebugOverlay& Overlay)
{
    FScopeLock Lock(&OverlayLock);
    PendingOverlay = Overlay;
}

bool UHephaestusVisionSubsystem::CaptureSingleFrame(FHephaestusFrameMetadata& OutMetadata, UTexture2D*& OutTexture)
{
    if (!bIsCapturing)
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusVisionSubsystem: Not capturing, cannot capture single frame"));
        return false;
    }

    // Trigger immediate capture on render thread
    bool bCaptured = false;
    ENQUEUE_RENDER_COMMAND(HephaestusVision_CaptureSingle)(
        [this, &bCaptured, &OutMetadata, &OutTexture](FRHICommandListImmediate& RHICmdList)
        {
            // This would need a synchronous readback implementation
            // For now, return latest available frame
            FScopeLock Lock(&FrameDataLock);
            if (LatestMetadata.IsValid() && LatestTexture.IsValid())
            {
                OutMetadata = *LatestMetadata;
                OutTexture = LatestTexture.Get();
                bCaptured = true;
            }
        });

    // Wait for render thread (with timeout)
    double StartTime = FPlatformTime::Seconds();
    while (!bCaptured && (FPlatformTime::Seconds() - StartTime) < 0.1)
    {
        FPlatformProcess::Sleep(0.001);
    }

    return bCaptured;
}

FHephaestusWebRTCStreamer* UHephaestusVisionSubsystem::GetWebRTCStreamer()
{
    return WebRTCStreamer.Get();
}

void UHephaestusVisionSubsystem::CaptureViewport_RenderThread(FRDGBuilder& GraphBuilder)
{
    if (!bIsCapturing)
    {
        return;
    }

    // Check FPS throttling
    double CurrentTime = FPlatformTime::Seconds();
    double FrameTime = 1.0 / CurrentConfig.TargetFPS;
    static double LastCaptureTime = 0.0;

    if ((CurrentTime - LastCaptureTime) < FrameTime)
    {
        return;
    }
    LastCaptureTime = CurrentTime;

    // Get the scene renderer
    FSceneRenderer* SceneRenderer = GraphBuilder.GetSceneRenderer();
    if (!SceneRenderer)
    {
        return;
    }

    // Get view info
    const FViewInfo* View = SceneRenderer->Views.Num() > 0 ? SceneRenderer->Views[0] : nullptr;
    if (!View)
    {
        return;
    }

    // Create or resize capture render target
    FIntPoint TargetSize = CurrentConfig.CaptureResolution;
    FIntPoint ViewSize = View->ViewRect.Size();

    if (!CaptureRenderTarget.IsValid() ||
        CaptureRenderTarget->GetDesc().Extent.X != TargetSize.X ||
        CaptureRenderTarget->GetDesc().Extent.Y != TargetSize.Y)
    {
        FRDGTextureDesc Desc = FRDGTextureDesc::Create2D(
            TargetSize,
            PF_FloatRGBA, // RGBA16F for HDR
            FClearValueBinding::Black,
            TexCreate_ShaderResource | TexCreate_RenderTargetable | TexCreate_UAV
        );
        CaptureRenderTarget = GraphBuilder.CreateTexture(Desc, TEXT("HephaestusCaptureRT"));
    }

    // Add capture pass
    GraphBuilder.AddPass(
        RDG_EVENT_NAME("HephaestusCapture_%dx%d", TargetSize.X, TargetSize.Y),
        [this, View, TargetSize, ViewSize](FRDGBuilder& Builder, const FSceneView& InView)
        {
            // Copy backbuffer to our render target
            FRHITexture* Backbuffer = InView.GetOutputTexture();

            if (CurrentConfig.CaptureFormat == EHephaestusCaptureFormat::RGBA8 ||
                CurrentConfig.CaptureFormat == EHephaestusCaptureFormat::RGBA16F)
            {
                // Simple backbuffer copy
                FRHICopyTextureInfo CopyInfo;
                CopyInfo.Size = FIntVector(TargetSize.X, TargetSize.Y, 1);
                Builder.RHICmdList.CopyTexture(Backbuffer, CaptureRenderTarget->GetRHI(), CopyInfo);
            }
            else if (CurrentConfig.bCaptureGBuffer)
            {
                // Capture G-Buffer passes
                CaptureGBuffer_RenderThread(Builder, InView, TargetSize);
            }

            // Schedule GPU readback
            ScheduleGPUReadback(CaptureRenderTarget->GetRHI(), ++FrameCounter);
        },
        [this, View](FRDGBuilder& Builder, const FSceneView& InView)
        {
            // Additional pass for debug overlay injection
            if (CurrentConfig.bEnableDebugOverlay)
            {
                InjectDebugOverlay_RenderThread(Builder, InView);
            }
        }
    );

    FramesSinceLastStats++;
    UpdateStreamStats();
}

void UHephaestusVisionSubsystem::CaptureGBuffer_RenderThread(FRDGBuilder& Builder, const FSceneView& View, FIntPoint TargetSize)
{
    // Access G-Buffer textures from the deferred renderer
    const FDeferredShadingSceneRenderer* DeferredRenderer = View.GetDeferredShadingSceneRenderer();
    if (!DeferredRenderer)
    {
        return;
    }

    // G-Buffer A: World Normal (RGB), Scene Depth (A) - PF_FloatRGBA
    // G-Buffer B: BaseColor (RGB), Roughness (A) - PF_FloatRGBA
    // G-Buffer C: Specular (R), Metallic (G), ShadingModel (B), AO (A) - PF_FloatRGBA
    // G-Buffer D: Custom Data / Velocity (RG), Depth (B) - PF_G16R16 or PF_FloatRG

    // Create G-Buffer render targets if needed
    auto CreateGBufferRT = [&](const TCHAR* Name) -> TRefCountPtr<IPooledRenderTarget>
    {
        FRDGTextureDesc Desc = FRDGTextureDesc::Create2D(
            TargetSize,
            PF_FloatRGBA,
            FClearValueBinding::Black,
            TexCreate_ShaderResource | TexCreate_RenderTargetable
        );
        return Builder.CreateTexture(Desc, Name);
    };

    GBufferNormalDepth = CreateGBufferRT(TEXT("HephaestusGBuffer_NormalDepth"));
    GBufferBaseColorRoughness = CreateGBufferRT(TEXT("HephaestusGBuffer_BaseColorRoughness"));
    GBufferVelocityDepth = CreateGBufferRT(TEXT("HephaestusGBuffer_VelocityDepth"));

    // Copy from actual G-Buffer
    // This requires access to the G-Buffer textures which are internal to the renderer
    // We'll use a custom resolve shader for this
    Builder.AddPass(
        RDG_EVENT_NAME("HephaestusGBufferCopy"),
        [this, &View, TargetSize](FRDGBuilder& PassBuilder, const FSceneView& InView)
        {
            // Get actual G-Buffer textures from the renderer
            const FSceneTextures& SceneTextures = InView.GetSceneTextures();
            FRHITexture* GBufferA = SceneTextures.GBufferA ? SceneTextures.GBufferA->GetRHI() : nullptr;
            FRHITexture* GBufferB = SceneTextures.GBufferB ? SceneTextures.GBufferB->GetRHI() : nullptr;
            FRHITexture* GBufferVelocity = SceneTextures.GBufferVelocity ? SceneTextures.GBufferVelocity->GetRHI() : nullptr;

            if (GBufferA)
            {
                FRHICopyTextureInfo CopyInfo;
                CopyInfo.Size = FIntVector(TargetSize.X, TargetSize.Y, 1);
                PassBuilder.RHICmdList.CopyTexture(GBufferA, GBufferNormalDepth->GetRHI(), CopyInfo);
            }
            if (GBufferB)
            {
                FRHICopyTextureInfo CopyInfo;
                CopyInfo.Size = FIntVector(TargetSize.X, TargetSize.Y, 1);
                PassBuilder.RHICmdList.CopyTexture(GBufferB, GBufferBaseColorRoughness->GetRHI(), CopyInfo);
            }
            if (GBufferVelocity)
            {
                FRHICopyTextureInfo CopyInfo;
                CopyInfo.Size = FIntVector(TargetSize.X, TargetSize.Y, 1);
                PassBuilder.RHICmdList.CopyTexture(GBufferVelocity, GBufferVelocityDepth->GetRHI(), CopyInfo);
            }
        }
    );
}

void UHephaestusVisionSubsystem::InjectDebugOverlay_RenderThread(FRDGBuilder& Builder, const FSceneView& View)
{
    FHephaestusDebugOverlay Overlay;
    {
        FScopeLock Lock(&OverlayLock);
        Overlay = PendingOverlay;
        PendingOverlay = FHephaestusDebugOverlay(); // Clear after reading
    }

    if (Overlay.BoundingBoxes.Num() == 0 && Overlay.TextLabels.Num() == 0 &&
        Overlay.Lines.Num() == 0 && Overlay.Markers.Num() == 0)
    {
        return; // Nothing to draw
    }

    // Add debug overlay pass - draws directly onto capture render target
    Builder.AddPass(
        RDG_EVENT_NAME("HephaestusDebugOverlay"),
        [this, Overlay, &View](FRDGBuilder& PassBuilder, const FSceneView& InView)
        {
            // This would use a custom debug drawing shader
            // For now, we'll use immediate drawing on the RHICmdList
            FRHICommandListImmediate& RHICmdList = PassBuilder.RHICmdList;

            // Set render target to our capture texture
            FRHIRenderTargetView RTV(CaptureRenderTarget->GetRHI()->GetTexture2D(), ERenderTargetLoadAction::ELoad);
            RHICmdList.SetRenderTarget(RTV, FExclusiveDepthStencil::DepthNop_StencilNop);

            // Draw bounding boxes
            for (int32 i = 0; i < Overlay.BoundingBoxes.Num(); i += 9)
            {
                if (i + 8 >= Overlay.BoundingBoxes.Num()) break;

                float x = Overlay.BoundingBoxes[i];
                float y = Overlay.BoundingBoxes[i + 1];
                float w = Overlay.BoundingBoxes[i + 2];
                float h = Overlay.BoundingBoxes[i + 3];
                float r = Overlay.BoundingBoxes[i + 4];
                float g = Overlay.BoundingBoxes[i + 5];
                float b = Overlay.BoundingBoxes[i + 6];
                float a = Overlay.BoundingBoxes[i + 7];

                // DrawRect would need a simple shader or immediate mode
                // This is a stub - actual implementation needs a debug draw shader
            }
        }
    );
}

void UHephaestusVisionSubsystem::ProcessCapturedTexture_RenderThread(FRDGBuilder& Builder, FRHITexture* SourceTexture)
{
    // This is called after capture to process the texture
    // (format conversion, scaling, etc. before readback)
}

void UHephaestusVisionSubsystem::ScheduleGPUReadback(FRHITexture* Texture, uint64 FrameID)
{
    if (!Texture || !bIsCapturing)
    {
        return;
    }

    // Create CPU-readable texture for readback
    FRHITexture2D* Texture2D = Texture->GetTexture2D();
    if (!Texture2D)
    {
        return;
    }

    FIntPoint Size = FIntPoint(Texture2D->GetSizeX(), Texture2D->GetSizeY());
    EPixelFormat Format = Texture2D->GetFormat();

    // Create readback texture if needed
    if (!ReadbackTexture.IsValid() ||
        ReadbackTexture->GetSizeX() != Size.X ||
        ReadbackTexture->GetSizeY() != Size.Y ||
        ReadbackTexture->GetFormat() != PF_B8G8R8A8) // Convert to CPU-friendly format
    {
        FRHIResourceCreateInfo CreateInfo(TEXT("HephaestusReadbackTexture"));
        ReadbackTexture = RHICmdList.CreateTexture2D(Size.X, Size.Y, PF_B8G8R8A8, 1, 1, TexCreate_CPUReadback, CreateInfo);
    }

    // Copy to readback texture
    FRHICopyTextureInfo CopyInfo;
    CopyInfo.Size = FIntVector(Size.X, Size.Y, 1);
    RHICmdList.CopyTexture(Texture, ReadbackTexture, CopyInfo);

    // Schedule async readback
    RHICmdList.ReadSurfaceData(
        ReadbackTexture,
        FIntRect(0, 0, Size.X, Size.Y),
        [this, FrameID, Size](TArray64<uint8>&& Data)
        {
            OnGPUReadbackComplete(FrameID, MoveTemp(Data));
        },
        FReadSurfaceDataFlags(RCM_UNorm, CubeFace_MAX)
    );
}

void UHephaestusVisionSubsystem::OnGPUReadbackComplete(uint64 FrameID, TArray64<uint8>&& Data)
{
    if (!bIsCapturing)
    {
        return;
    }

    FHephaestusFrameMetadata Metadata;
    Metadata.FrameID = FrameID;
    Metadata.CaptureTimestampUs = FPlatformTime::Cycles64() * 1000000 / FPlatformTime::GetCyclesPerSecond();
    Metadata.Resolution = CurrentConfig.CaptureResolution;
    Metadata.Format = CurrentConfig.CaptureFormat;
    Metadata.bHasGBuffer = CurrentConfig.bCaptureGBuffer && GBufferNormalDepth.IsValid();

    // Create UTexture2D from raw data (on game thread)
    AsyncTask(ENamedThreads::GameThread, [this, FrameID, Metadata, Data = MoveTemp(Data)]() mutable
    {
        UTexture2D* Texture = UTexture2D::CreateTransient(Metadata.Resolution.X, Metadata.Resolution.Y, PF_B8G8R8A8);
        if (Texture)
        {
            void* MipData = Texture->GetPlatformData()->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
            FMemory::Memcpy(MipData, Data.GetData(), Data.Num());
            Texture->GetPlatformData()->Mips[0].BulkData.Unlock();
            Texture->UpdateResource();

            // Store latest frame
            {
                FScopeLock Lock(&FrameDataLock);
                LatestFrameID = FrameID;
                LatestMetadata = MakeShared<FHephaestusFrameMetadata>(Metadata);
                LatestTexture = Texture;
            }

            // Broadcast event
            OnFrameCaptured.Broadcast(*LatestMetadata, Texture);

            // Encode and stream if WebRTC enabled
            if (CurrentConfig.bEnableWebRTC && WebRTCStreamer && FrameEncoder)
            {
                EncodeAndStreamFrame(FrameID, MoveTemp(Data), Metadata);
            }
        }
    });
}

void UHephaestusVisionSubsystem::EncodeAndStreamFrame(uint64 FrameID, const TArray64<uint8>& Data, const FHephaestusFrameMetadata& Metadata)
{
    if (!FrameEncoder || !WebRTCStreamer)
    {
        return;
    }

    // Encode frame
    TArray<uint8> EncodedData;
    if (FrameEncoder->EncodeFrame(Data, Metadata.Resolution.X, Metadata.Resolution.Y, EncodedData))
    {
        // Send via WebRTC
        WebRTCStreamer->SendVideoFrame(EncodedData, FrameID, Metadata.CaptureTimestampUs);
    }
}

void UHephaestusVisionSubsystem::UpdateStreamStats()
{
    double CurrentTime = FPlatformTime::Seconds();
    double Elapsed = CurrentTime - LastStatsUpdateTime;

    if (Elapsed >= 1.0) // Update every second
    {
        CurrentFPS = static_cast<int32>(FramesSinceLastStats / Elapsed);
        FramesSinceLastStats = 0;
        LastStatsUpdateTime = CurrentTime;

        // Get bitrate from encoder
        if (FrameEncoder)
        {
            CurrentBitrateKbps = FrameEncoder->GetCurrentBitrateKbps();
        }

        // Get latency from WebRTC
        if (WebRTCStreamer)
        {
            AverageLatencyMs = WebRTCStreamer->GetAverageLatencyMs();
        }

        // Broadcast stats
        OnStreamStats.Broadcast(CurrentFPS, CurrentBitrateKbps, AverageLatencyMs);
    }
}

#undef LOCTEXT_NAMESPACE