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
#include "Engine/Blueprint.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimMontage.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#if WITH_EDITOR
#include "AssetImportTask.h"
#include "AssetToolsModule.h"
#include "AutomatedAssetImportData.h"
#include "IAssetTools.h"
#endif

void UHephaestusAssetSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Initialized"));
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

#if WITH_EDITOR
	// AssetTools FBX import from the remote-API game-thread callback is unsafe during PIE:
	// it can reset the HTTP listener / stall the editor. Validate only; import offline or
	// via editor Python (asset.import_fbx when not playing).
	const bool bInPIE = GIsPlayInEditorWorld;
	if (bInPIE)
	{
		UE_LOG(
			LogHephaestusBridge,
			Warning,
			TEXT("ImportAsset: refused during PIE (file ok: %s -> %s). Stop Play and retry, or use editor import."),
			*FilePath,
			*DestinationPath);
		return nullptr;
	}

	UAutomatedAssetImportData* ImportData = NewObject<UAutomatedAssetImportData>();
	ImportData->Filenames.Add(FilePath);
	ImportData->DestinationPath = DestinationPath;
	ImportData->bReplaceExisting = true;
	ImportData->bSkipReadOnly = true;
	ImportData->GroupName = TEXT("HephaestusImport");

	FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools");
	TArray<UObject*> Imported = AssetToolsModule.Get().ImportAssetsAutomated(ImportData);

	if (Imported.Num() == 0)
	{
		UAssetImportTask* ImportTask = NewObject<UAssetImportTask>();
		ImportTask->Filename = FilePath;
		ImportTask->DestinationPath = DestinationPath;
		ImportTask->bAutomated = true;
		ImportTask->bSave = true;
		ImportTask->bReplaceExisting = true;
		ImportTask->bReplaceExistingSettings = true;
		TArray<UAssetImportTask*> Tasks;
		Tasks.Add(ImportTask);
		AssetToolsModule.Get().ImportAssetTasks(Tasks);
		for (const FString& Path : ImportTask->ImportedObjectPaths)
		{
			if (UObject* Obj = FSoftObjectPath(Path).TryLoad())
			{
				Imported.Add(Obj);
			}
		}
	}

	if (Imported.Num() > 0)
	{
		UObject* Primary = Imported[0];
		UE_LOG(
			LogHephaestusBridge,
			Log,
			TEXT("ImportAsset: imported %s -> %s (count=%d, scale=%.3f)"),
			*FilePath,
			*Primary->GetPathName(),
			Imported.Num(),
			Options.UniformScale);
		return Primary;
	}

	UE_LOG(LogHephaestusBridge, Warning, TEXT("ImportAsset: no assets produced for %s"), *FilePath);
	return nullptr;
#else
	UE_LOG(
		LogHephaestusBridge,
		Warning,
		TEXT("ImportAsset: editor-only — cannot import %s outside editor builds"),
		*FilePath);
	return nullptr;
#endif
}

bool UHephaestusAssetSubsystem::ReimportAsset(UObject* Asset)
{
	if (!Asset)
	{
		return false;
	}
	UE_LOG(
		LogHephaestusBridge,
		Log,
		TEXT("ReimportAsset: validated %s (editor reimport pipeline deferred)"),
		*Asset->GetPathName());
	return true;
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
		Filter.ClassPaths.Add(UAnimSequence::StaticClass()->GetClassPathName());
		Filter.ClassPaths.Add(UBlueprint::StaticClass()->GetClassPathName());
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
		// BasicShapes covers Cube/etc. Broader Engine roots cover mannequin/SK fallbacks on blank projects.
		EngineFilter.PackagePaths.Add(TEXT("/Engine/BasicShapes"));
		EngineFilter.PackagePaths.Add(TEXT("/Engine/EngineMeshes"));
		EngineFilter.PackagePaths.Add(TEXT("/Engine/EditorMeshes"));
		EngineFilter.PackagePaths.Add(TEXT("/Engine/Animation"));
		EngineFilter.PackagePaths.Add(TEXT("/Engine/Characters"));
		EngineFilter.PackagePaths.Add(TEXT("/Engine/ArtTools"));
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
