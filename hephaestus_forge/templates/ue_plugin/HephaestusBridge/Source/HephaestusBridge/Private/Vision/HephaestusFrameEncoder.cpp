// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusFrameEncoder.h"
#include "HephaestusBridge.h"

FHephaestusFrameEncoder::FHephaestusFrameEncoder() = default;
FHephaestusFrameEncoder::~FHephaestusFrameEncoder() { Shutdown(); }

bool FHephaestusFrameEncoder::Initialize()
{
	bInitialized = true;
	return true;
}

void FHephaestusFrameEncoder::Shutdown()
{
	bInitialized = false;
}

bool FHephaestusFrameEncoder::Configure(const FHephaestusEncoderConfig& InConfig)
{
	Config = InConfig;
	return Config.IsValid();
}

bool FHephaestusFrameEncoder::EncodeFrame(const TArray64<uint8>& InData, int32 Width, int32 Height, TArray<uint8>& OutEncodedData)
{
	OutEncodedData.Reset();
	UE_LOG(LogHephaestusBridge, Verbose, TEXT("EncodeFrame stub %dx%d (%lld bytes)"), Width, Height, InData.Num());
	return false;
}

void FHephaestusFrameEncoder::ForceKeyFrame()
{
	bForceKeyFrame = true;
}

FHephaestusFrameEncoder::FStats FHephaestusFrameEncoder::GetStats() const
{
	FScopeLock Lock(&StatsLock);
	return Stats;
}

bool FHephaestusFrameEncoder::CreateHardwareEncoder() { return false; }
bool FHephaestusFrameEncoder::CreateSoftwareEncoder() { return false; }
bool FHephaestusFrameEncoder::EncodeHardware(const TArray64<uint8>&, int32, int32, TArray<uint8>&) { return false; }
bool FHephaestusFrameEncoder::EncodeSoftware(const TArray64<uint8>&, int32, int32, TArray<uint8>&) { return false; }
