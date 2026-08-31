// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Assets/HephaestusAssetSubsystem.h"
#include "HephaestusBridge.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Modules/ModuleManager.h"
#include "UObject/SoftObjectPath.h"

void UHephaestusAssetSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Initialized (stub)"));
}

void UHephaestusAssetSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

UMaterial* UHephaestusAssetSubsystem::CreateMaterial(const FHephaestusMaterialDesc& Desc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateMaterial stub: %s"), *Desc.Name);
	return nullptr;
}

UObject* UHephaestusAssetSubsystem::ImportAsset(const FString& FilePath, const FString& DestinationPath, const FHephaestusImportOptions& Options)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("ImportAsset stub: %s -> %s"), *FilePath, *DestinationPath);
	return nullptr;
}

bool UHephaestusAssetSubsystem::ReimportAsset(UObject* Asset)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("ReimportAsset stub"));
	return false;
}

bool UHephaestusAssetSubsystem::ExportAsset(UObject* Asset, const FString& FilePath, const FString& ExportOptions)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("ExportAsset stub: %s"), *FilePath);
	return false;
}

UMaterialInstanceDynamic* UHephaestusAssetSubsystem::CreateMaterialInstance(UMaterial* ParentMaterial, const TMap<FString, FString>& Parameters)
{
	if (!ParentMaterial)
	{
		return nullptr;
	}

	UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(ParentMaterial, GetTransientPackage());
	if (!Instance)
	{
		return nullptr;
	}

	for (const TPair<FString, FString>& Pair : Parameters)
	{
		const FName ParamName(*Pair.Key);
		float Scalar = 0.f;
		if (Instance->GetScalarParameterValue(ParamName, Scalar))
		{
			Instance->SetScalarParameterValue(ParamName, FCString::Atof(*Pair.Value));
			continue;
		}

		FLinearColor Color;
		if (Instance->GetVectorParameterValue(ParamName, Color))
		{
			TArray<FString> Components;
			Pair.Value.ParseIntoArray(Components, TEXT(","), true);
			if (Components.Num() >= 3)
			{
				Color.R = FCString::Atof(*Components[0]);
				Color.G = FCString::Atof(*Components[1]);
				Color.B = FCString::Atof(*Components[2]);
				Color.A = Components.Num() > 3 ? FCString::Atof(*Components[3]) : 1.0f;
				Instance->SetVectorParameterValue(ParamName, Color);
			}
		}
	}

	return Instance;
}

UObject* UHephaestusAssetSubsystem::FindAsset(const FString& AssetPath) const
{
	return FSoftObjectPath(AssetPath).TryLoad();
}

TArray<UObject*> UHephaestusAssetSubsystem::GetAssetsInPath(const FString& Path, TSubclassOf<UObject> ClassFilter) const
{
	TArray<UObject*> Results;
	FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
	TArray<FAssetData> Assets;
	AssetRegistryModule.Get().GetAssetsByPath(FName(*Path), Assets, true);

	for (const FAssetData& Asset : Assets)
	{
		UObject* Obj = Asset.GetAsset();
		if (!Obj)
		{
			continue;
		}
		if (ClassFilter && !Obj->IsA(ClassFilter))
		{
			continue;
		}
		Results.Add(Obj);
	}
	return Results;
}
