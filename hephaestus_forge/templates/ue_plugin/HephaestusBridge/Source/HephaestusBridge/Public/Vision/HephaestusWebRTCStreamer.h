// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "HephaestusWebRTCStreamer.generated.h"

UENUM(BlueprintType)
enum class EHephaestusVideoCodec : uint8
{
	H264,
	HEVC,
	AV1,
	VP9,
};

USTRUCT(BlueprintType)
struct FHephaestusWebRTCConfig
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString SignalingURL = TEXT("ws://127.0.0.1:8081/signaling");

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	EHephaestusVideoCodec VideoCodec = EHephaestusVideoCodec::H264;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	int32 BitrateKbps = 8000;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	int32 Width = 1920;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	int32 Height = 1080;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	int32 FPS = 15;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TArray<FString> ICEServers;

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString DataChannelLabel = TEXT("hephaestus-control");

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	bool bUseUnreliableDataChannel = true;
};

UENUM(BlueprintType)
enum class EHephaestusWebRTCState : uint8
{
	Disconnected,
	Connecting,
	Connected,
	Failed,
	Closed,
};

class HEPHAESTUSBRIDGE_API FHephaestusWebRTCStreamer
{
public:
	FHephaestusWebRTCStreamer() = default;
	~FHephaestusWebRTCStreamer() { Shutdown(); }

	bool Initialize() { return true; }
	void Shutdown() { ConnectionState = EHephaestusWebRTCState::Disconnected; }
	void Configure(const FHephaestusWebRTCConfig& InConfig) { Config = InConfig; }
	bool Connect() { ConnectionState = EHephaestusWebRTCState::Connected; return true; }
	void Disconnect() { ConnectionState = EHephaestusWebRTCState::Disconnected; }
	EHephaestusWebRTCState GetState() const { return ConnectionState; }
	bool SendVideoFrame(const TArray<uint8>& EncodedData, uint64 FrameID, int64 TimestampUs) { return false; }
	bool SendDataChannelMessage(const FString& Message) { return false; }
	float GetAverageLatencyMs() const { return AverageLatencyMs; }

private:
	FHephaestusWebRTCConfig Config;
	EHephaestusWebRTCState ConnectionState = EHephaestusWebRTCState::Disconnected;
	float AverageLatencyMs = 0.0f;
};
