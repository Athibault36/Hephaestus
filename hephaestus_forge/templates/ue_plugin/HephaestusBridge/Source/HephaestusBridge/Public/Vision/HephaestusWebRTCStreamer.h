// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Containers/Queue.h"
#include "HephaestusWebRTCStreamer.generated.h"

/** Video codec for WebRTC */
UENUM(BlueprintType)
enum class EHephaestusVideoCodec : uint8
{
    H264,
    HEVC,
    AV1,
    VP9,
};

/** WebRTC configuration */
USTRUCT(BlueprintType)
struct FHephaestusWebRTCConfig
{
    GENERATED_BODY()

    /** Signaling server WebSocket URL */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString SignalingURL = TEXT("ws://127.0.0.1:8081/signaling");

    /** Video codec */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    EHephaestusVideoCodec VideoCodec = EHephaestusVideoCodec::H264;

    /** Target bitrate in kbps */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 BitrateKbps = 8000;

    /** Frame width */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 Width = 1920;

    /** Frame height */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 Height = 1080;

    /** Target FPS */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 FPS = 15;

    /** ICE servers (STUN/TURN) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> ICEServers = {
        TEXT("stun:stun.l.google.com:19302"),
        TEXT("stun:stun1.l.google.com:19302")
    };

    /** Data channel label for command/control */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString DataChannelLabel = TEXT("hephaestus-control");

    /** Enable unreliable data channel for low-latency frames */
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bUseUnreliableDataChannel = true;
};

/** WebRTC connection state */
UENUM(BlueprintType)
enum class EHephaestusWebRTCState : uint8
{
    Disconnected,
    Connecting,
    Connected,
    Failed,
    Closed,
};

/** Video frame data for encoding */
struct FHephaestusVideoFrame
{
    TArray<uint8> Data;
    uint64 FrameID = 0;
    int64 TimestampUs = 0;
    bool bKeyFrame = false;
};

/**
 * FHephaestusWebRTCStreamer
 * 
 * Manages WebRTC peer connection for streaming viewport to Mission Control.
 * Uses libwebrtc via PixelStreaming module or standalone integration.
 * Supports both reliable (data channel) and unreliable (media track) transport.
 */
class HEPHAESTUSBRIDGE_API FHephaestusWebRTCStreamer
{
public:
    FHephaestusWebRTCStreamer();
    ~FHephaestusWebRTCStreamer();

    /** Initialize WebRTC subsystem */
    bool Initialize();

    /** Shutdown and cleanup */
    void Shutdown();

    /** Configure streamer */
    void Configure(const FHephaestusWebRTCConfig& InConfig);

    /** Connect to signaling server */
    bool Connect();

    /** Disconnect from peer */
    void Disconnect();

    /** Get current connection state */
    EHephaestusWebRTCState GetState() const { return ConnectionState; }

    /** Send encoded video frame */
    bool SendVideoFrame(const TArray<uint8>& EncodedData, uint64 FrameID, int64 TimestampUs);

    /** Send data channel message (JSON commands) */
    bool SendDataChannelMessage(const FString& Message);

    /** Set data channel message handler */
    using FOnDataChannelMessage = TFunction<void(const FString&)>;
    void SetOnDataChannelMessage(FOnDataChannelMessage&& Handler);

    /** Set connection state change handler */
    using FOnStateChanged = TFunction<void(EHephaestusWebRTCState)>;
    void SetOnStateChanged(FOnStateChanged&& Handler);

    /** Get average round-trip latency in milliseconds */
    float GetAverageLatencyMs() const { return AverageLatencyMs; }

    /** Get statistics */
    struct FStats
    {
        int32 FramesSent = 0;
        int32 FramesDropped = 0;
        int64 BytesSent = 0;
        float CurrentBitrateKbps = 0.0f;
        float AverageLatencyMs = 0.0f;
        float PacketLossPercent = 0.0f;
    };
    FStats GetStats() const;

private:
    /** Internal: Process signaling messages */
    void ProcessSignalingMessage(const FString& Message);

    /** Internal: Create peer connection */
    bool CreatePeerConnection();

    /** Internal: Create data channel */
    bool CreateDataChannel();

    /** Internal: Handle ICE candidate */
    void OnICECandidate(const FString& Candidate);

    /** Internal: Handle connection state change */
    void OnConnectionStateChanged(EHephaestusWebRTCState NewState);

    /** Internal: Send pending frames */
    void FlushPendingFrames();

    /** Configuration */
    FHephaestusWebRTCConfig Config;

    /** Connection state */
    EHephaestusWebRTCState ConnectionState = EHephaestusWebRTCState::Disconnected;

    /** WebRTC peer connection (opaque handle to libwebrtc) */
    void* PeerConnection = nullptr;

    /** Data channel for commands */
    void* DataChannel = nullptr;

    /** Pending video frames queue */
    TQueue<FHephaestusVideoFrame, EQueueMode::Mpsc> PendingFrames;

    /** Callbacks */
    FOnDataChannelMessage OnDataChannelMessageCallback;
    FOnStateChanged OnStateChangedCallback;

    /** Statistics */
    mutable FCriticalSection StatsLock;
    FStats Stats;
    float AverageLatencyMs = 0.0f;
    double LastStatsTime = 0.0;

    /** Signaling WebSocket (placeholder - uses PixelStreaming or custom) */
    class FHephaestusSignalingSocket* SignalingSocket = nullptr;

    /** Worker thread for WebRTC processing */
    FRunnableThread* WorkerThread = nullptr;
    class FHephaestusWebRTCWorker* Worker = nullptr;
};