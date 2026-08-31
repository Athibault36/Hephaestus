// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusWebRTCStreamer.h"
#include "Vision/HephaestusFrameEncoder.h"
#include "Async/Async.h"
#include "HAL/PlatformProcess.h"
#include "Sockets.h"
#include "WebSocketsModule.h"
#include "IWebSocket.h"
#include "Json.h"

#define LOCTEXT_NAMESPACE "HephaestusWebRTC"

FHephaestusWebRTCStreamer::FHephaestusWebRTCStreamer()
{
}

FHephaestusWebRTCStreamer::~FHephaestusWebRTCStreamer()
{
    Shutdown();
}

bool FHephaestusWebRTCStreamer::Initialize()
{
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Initializing..."));

    // In a real implementation, this would:
    // 1. Initialize libwebrtc (PeerConnectionFactory)
    // 2. Set up audio/video tracks
    // 3. Configure ICE servers
    // 4. Create data channels

    // For now, we'll use a stub implementation that logs
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Initialized (stub)"));
    return true;
}

void FHephaestusWebRTCStreamer::Shutdown()
{
    Disconnect();

    if (WorkerThread)
    {
        WorkerThread->Kill(true);
        delete WorkerThread;
        WorkerThread = nullptr;
    }

    if (SignalingSocket)
    {
        delete SignalingSocket;
        SignalingSocket = nullptr;
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Shutdown"));
}

void FHephaestusWebRTCStreamer::Configure(const FHephaestusWebRTCConfig& InConfig)
{
    Config = InConfig;
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Configured - %s:%d @ %d fps, %d kbps"),
        *Config.SignalingURL, Config.Port, Config.FPS, Config.BitrateKbps);
}

bool FHephaestusWebRTCStreamer::Connect()
{
    if (ConnectionState == EHephaestusWebRTCState::Connected ||
        ConnectionState == EHephaestusWebRTCState::Connecting)
    {
        return true;
    }

    ConnectionState = EHephaestusWebRTCState::Connecting;

    // Start signaling WebSocket connection
    // In real implementation: connect to signaling server, exchange SDP, gather ICE candidates
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Connecting to %s"), *Config.SignalingURL);

    // Simulate connection for stub
    AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask, [this]()
    {
        FPlatformProcess::Sleep(1.0); // Simulate connection time
        AsyncTask(ENamedThreads::GameThread, [this]()
        {
            OnConnectionStateChanged(EHephaestusWebRTCState::Connected);
        });
    });

    return true;
}

void FHephaestusWebRTCStreamer::Disconnect()
{
    if (ConnectionState == EHephaestusWebRTCState::Disconnected ||
        ConnectionState == EHephaestusWebRTCState::Closed)
    {
        return;
    }

    ConnectionState = EHephaestusWebRTCState::Disconnected;

    // Flush pending frames
    FlushPendingFrames();

    // Close peer connection
    if (PeerConnection)
    {
        // In real impl: PeerConnection->Close()
        PeerConnection = nullptr;
    }

    // Close data channel
    if (DataChannel)
    {
        DataChannel = nullptr;
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: Disconnected"));
}

bool FHephaestusWebRTCStreamer::SendVideoFrame(const TArray<uint8>& EncodedData, uint64 FrameID, int64 TimestampUs)
{
    if (ConnectionState != EHephaestusWebRTCState::Connected)
    {
        return false;
    }

    // Queue frame for sending
    FHephaestusVideoFrame Frame;
    Frame.Data = EncodedData;
    Frame.FrameID = FrameID;
    Frame.TimestampUs = TimestampUs;
    Frame.bKeyFrame = (FrameID % Config.GOPSize == 0);

    PendingFrames.Enqueue(Frame);

    // Update stats
    {
        FScopeLock Lock(&StatsLock);
        Stats.FramesSent++;
        Stats.BytesSent += EncodedData.Num();
    }

    return true;
}

bool FHephaestusWebRTCStreamer::SendDataChannelMessage(const FString& Message)
{
    if (ConnectionState != EHephaestusWebRTCState::Connected || !DataChannel)
    {
        return false;
    }

    // In real impl: DataChannel->Send(Message)
    UE_LOG(LogHephaestusBridge, VeryVerbose, TEXT("HephaestusWebRTCStreamer: DataChannel send: %s"), *Message);
    return true;
}

void FHephaestusWebRTCStreamer::SetOnDataChannelMessage(FOnDataChannelMessage&& Handler)
{
    OnDataChannelMessageCallback = MoveTemp(Handler);
}

void FHephaestusWebRTCStreamer::SetOnStateChanged(FOnStateChanged&& Handler)
{
    OnStateChangedCallback = MoveTemp(Handler);
}

FHephaestusWebRTCStreamer::FStats FHephaestusWebRTCStreamer::GetStats() const
{
    FScopeLock Lock(&StatsLock);
    FStats Result = Stats;
    Result.AverageLatencyMs = AverageLatencyMs;
    return Result;
}

void FHephaestusWebRTCStreamer::ProcessSignalingMessage(const FString& Message)
{
    // Parse JSON signaling message
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
    if (FJsonSerializer::Deserialize(Reader, JsonObject))
    {
        FString Type = JsonObject->GetStringField(TEXT("type"));
        if (Type == TEXT("offer"))
        {
            // Handle SDP offer
        }
        else if (Type == TEXT("answer"))
        {
            // Handle SDP answer
        }
        else if (Type == TEXT("ice"))
        {
            // Handle ICE candidate
            FString Candidate = JsonObject->GetStringField(TEXT("candidate"));
            OnICECandidate(Candidate);
        }
    }
}

bool FHephaestusWebRTCStreamer::CreatePeerConnection()
{
    // In real impl: create PeerConnectionFactory, PeerConnection, set callbacks
    return true;
}

bool FHephaestusWebRTCStreamer::CreateDataChannel()
{
    // In real impl: create data channel with Config.DataChannelLabel
    return true;
}

void FHephaestusWebRTCStreamer::OnICECandidate(const FString& Candidate)
{
    // Send ICE candidate to signaling server
    TSharedPtr<FJsonObject> Json = MakeShareable(new FJsonObject());
    Json->SetStringField(TEXT("type"), TEXT("ice"));
    Json->SetStringField(TEXT("candidate"), Candidate);

    FString Output;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
    FJsonSerializer::Serialize(Json.ToSharedRef(), Writer);

    // Send via signaling socket
    // SignalingSocket->Send(Output);
}

void FHephaestusWebRTCStreamer::OnConnectionStateChanged(EHephaestusWebRTCState NewState)
{
    ConnectionState = NewState;

    if (OnStateChangedCallback)
    {
        OnStateChangedCallback(NewState);
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWebRTCStreamer: State changed to %d"), (int32)NewState);
}

void FHephaestusWebRTCStreamer::FlushPendingFrames()
{
    FHephaestusVideoFrame Frame;
    while (PendingFrames.Dequeue(Frame))
    {
        // Frames dropped
        FScopeLock Lock(&StatsLock);
        Stats.FramesDropped++;
    }
}

#undef LOCTEXT_NAMESPACE