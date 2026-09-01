// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Vision/HephaestusFrameEncoder.h"
#include "HephaestusBridge.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Modules/ModuleManager.h"

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
	if (Width <= 0 || Height <= 0 || InData.Num() < static_cast<int64>(Width) * Height * 4)
	{
		return false;
	}

	IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	const EImageFormat Format = EImageFormat::PNG;
	TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(Format);
	if (!Wrapper.IsValid())
	{
		return false;
	}
	if (!Wrapper->SetRaw(InData.GetData(), InData.Num(), ERGBFormat::BGRA, 8))
	{
		return false;
	}
	OutEncodedData = Wrapper->GetCompressed();
	return OutEncodedData.Num() > 0;
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
