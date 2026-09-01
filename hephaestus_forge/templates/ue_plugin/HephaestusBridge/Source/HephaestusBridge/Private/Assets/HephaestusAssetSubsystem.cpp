// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Assets/HephaestusAssetSubsystem.h"
#include "HephaestusBridge.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Modules/ModuleManager.h"
#include "UObject/SoftObjectPath.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimMontage.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

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
	FString BasePath = Desc.BaseMaterialPath;
	if (BasePath.IsEmpty())
	{
		BasePath = TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial");
	}
	UMaterial* Parent = LoadObject<UMaterial>(nullptr, *BasePath);
	if (!Parent)
	{
		Parent = LoadObject<UMaterial>(nullptr, TEXT("/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"));
	}
	if (!Parent)
	{
		return nullptr;
	}
	if (UMaterialInstanceDynamic* Instance = CreateMaterialInstance(Parent, Desc.Parameters))
	{
		UE_LOG(
			LogHephaestusBridge,
			Log,
			TEXT("CreateMaterial: %s using base %s (transient MID)"),
			*Desc.Name,
			*BasePath);
	}
	return Parent;
}

UObject* UHephaestusAssetSubsystem::ImportAsset(const FString& FilePath, const FString& DestinationPath, const FHephaestusImportOptions& Options)
{
	if (FilePath.IsEmpty())
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("ImportAsset: file_path required"));
		return nullptr;
	}
	if (!FPaths::FileExists(FilePath))
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("ImportAsset: file not found: %s"), *FilePath);
		return nullptr;
	}
	if (DestinationPath.IsEmpty())
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("ImportAsset: destination_path required"));
		return nullptr;
	}
	UE_LOG(
		LogHephaestusBridge,
		Warning,
		TEXT("ImportAsset: validated %s -> %s (editor import pipeline deferred)"),
		*FilePath,
		*DestinationPath);
	return nullptr;
}

bool UHephaestusAssetSubsystem::ReimportAsset(UObject* Asset)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("ReimportAsset stub"));
	return false;
}

bool UHephaestusAssetSubsystem::ExportAsset(UObject* Asset, const FString& FilePath, const FString& ExportOptions)
{
	if (!Asset)
	{
		return false;
	}
	UE_LOG(
		LogHephaestusBridge,
		Log,
		TEXT("ExportAsset: validated %s (disk export to %s deferred to editor tools)"),
		*Asset->GetPathName(),
		*FilePath);
	return true;
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

bool UHephaestusAssetSubsystem::SearchAssetsJson(
	const FString& Query,
	const FString& AssetClass,
	int32 Limit,
	FString& OutJson) const
{
	OutJson.Reset();
	if (Query.IsEmpty())
	{
		return false;
	}

	FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
	FARFilter Filter;
	Filter.PackagePaths.Add(TEXT("/Game"));
	Filter.bRecursivePaths = true;
	if (AssetClass.Equals(TEXT("StaticMesh"), ESearchCase::IgnoreCase))
	{
		Filter.ClassPaths.Add(UStaticMesh::StaticClass()->GetClassPathName());
	}
	else if (AssetClass.Equals(TEXT("SkeletalMesh"), ESearchCase::IgnoreCase))
	{
		Filter.ClassPaths.Add(USkeletalMesh::StaticClass()->GetClassPathName());
	}
	else if (AssetClass.Equals(TEXT("AnimSequence"), ESearchCase::IgnoreCase)
		|| AssetClass.Equals(TEXT("Animation"), ESearchCase::IgnoreCase))
	{
		Filter.ClassPaths.Add(UAnimSequence::StaticClass()->GetClassPathName());
	}
	else if (AssetClass.Equals(TEXT("AnimMontage"), ESearchCase::IgnoreCase)
		|| AssetClass.Equals(TEXT("Montage"), ESearchCase::IgnoreCase))
	{
		Filter.ClassPaths.Add(UAnimMontage::StaticClass()->GetClassPathName());
	}
	else
	{
		Filter.ClassPaths.Add(UStaticMesh::StaticClass()->GetClassPathName());
		Filter.ClassPaths.Add(USkeletalMesh::StaticClass()->GetClassPathName());
	}

	TArray<FAssetData> Assets;
	AssetRegistryModule.Get().GetAssets(Filter, Assets);

	TArray<FString> Tokens;
	Query.ParseIntoArray(Tokens, TEXT(" "), true);
	if (Tokens.Num() == 0)
	{
		Tokens.Add(Query);
	}

	struct FScoredAsset
	{
		FString Path;
		int32 Score = 0;
	};
	TArray<FScoredAsset> Scored;

	auto AppendMatches = [&](const TArray<FAssetData>& SourceAssets)
	{
		for (const FAssetData& Asset : SourceAssets)
		{
			const FString NameLower = Asset.AssetName.ToString().ToLower();
			const FString PathLower = Asset.GetObjectPathString().ToLower();
			int32 Score = 0;
			for (const FString& Token : Tokens)
			{
				const FString TokenLower = Token.ToLower();
				if (TokenLower.IsEmpty())
				{
					continue;
				}
				if (NameLower == TokenLower)
				{
					Score += 100;
				}
				else if (NameLower.Contains(TokenLower))
				{
					Score += 50;
				}
				else if (PathLower.Contains(TokenLower))
				{
					Score += 25;
				}
			}
			if (Score > 0)
			{
				Scored.Add({ Asset.GetObjectPathString(), Score });
			}
		}
	};

	AppendMatches(Assets);

	if (Scored.Num() < FMath::Max(Limit, 1))
	{
		FARFilter EngineFilter = Filter;
		EngineFilter.PackagePaths.Reset();
		EngineFilter.PackagePaths.Add(TEXT("/Engine/BasicShapes"));
		EngineFilter.bRecursivePaths = true;
		TArray<FAssetData> EngineAssets;
		AssetRegistryModule.Get().GetAssets(EngineFilter, EngineAssets);
		AppendMatches(EngineAssets);
	}

	Scored.Sort([](const FScoredAsset& A, const FScoredAsset& B) { return A.Score > B.Score; });

	TArray<FString> Matches;
	TSet<FString> Seen;
	for (const FScoredAsset& Item : Scored)
	{
		if (Seen.Contains(Item.Path))
		{
			continue;
		}
		Seen.Add(Item.Path);
		Matches.Add(Item.Path);
		if (Matches.Num() >= FMath::Max(Limit, 1))
		{
			break;
		}
	}

	TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
	TArray<TSharedPtr<FJsonValue>> Arr;
	for (const FString& Path : Matches)
	{
		Arr.Add(MakeShared<FJsonValueString>(Path));
	}
	ResultObj->SetArrayField(TEXT("assets"), Arr);
	ResultObj->SetStringField(TEXT("query"), Query);
	ResultObj->SetNumberField(TEXT("count"), Matches.Num());
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutJson);
	FJsonSerializer::Serialize(ResultObj, Writer);
	return true;
}
