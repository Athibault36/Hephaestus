// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#if WITH_EDITOR

#include "Command/HephaestusEditorRemoteSubsystem.h"

#include "HephaestusBridge.h"
#include "HephaestusVersion.h"

#include "Async/Async.h"
#include "AssetToolsModule.h"
#include "AssetImportTask.h"
#include "AutomatedAssetImportData.h"
#include "Containers/Ticker.h"
#include "Editor.h"
#include "Editor/UnrealEdEngine.h"
#include "HttpPath.h"
#include "HttpServerConstants.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealEdGlobals.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Factories/FbxImportUI.h"
#include "Factories/FbxFactory.h"
#include "Factories/FbxSkeletalMeshImportData.h"
#include "Factories/FbxTextureImportData.h"
#include "Factories/MaterialInstanceConstantFactoryNew.h"
#include "HAL/IConsoleManager.h"
#include "HAL/FileManager.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceConstant.h"
#include "FileHelpers.h"

namespace HephaestusFbxImport
{
	static bool IsImageExtension(const FString& Ext)
	{
		const FString Lower = Ext.ToLower();
		return Lower == TEXT("jpg") || Lower == TEXT("jpeg") || Lower == TEXT("png")
			|| Lower == TEXT("tga") || Lower == TEXT("bmp") || Lower == TEXT("exr");
	}

	/** Prefer Diffuse/Metallic .jpg over duplicate .png Normal sidecars when both exist. */
	static void CollectFbmTextureFiles(const FString& FbmDir, TArray<FString>& OutFiles)
	{
		TArray<FString> Candidates;
		IFileManager::Get().FindFiles(Candidates, *(FbmDir / TEXT("*.*")), true, false);
		TSet<FString> BasesWithJpg;
		for (const FString& Name : Candidates)
		{
			if (FPaths::GetExtension(Name).ToLower() == TEXT("jpg")
				|| FPaths::GetExtension(Name).ToLower() == TEXT("jpeg"))
			{
				BasesWithJpg.Add(FPaths::GetBaseFilename(Name));
			}
		}
		for (const FString& Name : Candidates)
		{
			if (!IsImageExtension(FPaths::GetExtension(Name)))
			{
				continue;
			}
			const FString Ext = FPaths::GetExtension(Name).ToLower();
			const FString Base = FPaths::GetBaseFilename(Name);
			if (Ext == TEXT("png") && BasesWithJpg.Contains(Base))
			{
				continue; // skip duplicate Normal.png when Normal.jpg exists
			}
			OutFiles.Add(FbmDir / Name);
		}
	}

	static int32 ImportFbmTextures(const FString& FbxPath, const FString& DestinationPath)
	{
		const FString FbmDir = FPaths::Combine(
			FPaths::GetPath(FbxPath),
			FPaths::GetBaseFilename(FbxPath) + TEXT(".fbm"));
		if (!FPaths::DirectoryExists(FbmDir))
		{
			return 0;
		}

		TArray<FString> Files;
		CollectFbmTextureFiles(FbmDir, Files);
		if (Files.Num() == 0)
		{
			return 0;
		}

		FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools");
		TArray<UAssetImportTask*> Tasks;
		for (const FString& File : Files)
		{
			UAssetImportTask* Task = NewObject<UAssetImportTask>();
			Task->Filename = File;
			Task->DestinationPath = DestinationPath;
			Task->DestinationName = FPaths::GetBaseFilename(File);
			Task->bAutomated = true;
			Task->bSave = true;
			Task->bReplaceExisting = true;
			Task->bReplaceExistingSettings = true;
			Tasks.Add(Task);
		}
		AssetToolsModule.Get().ImportAssetTasks(Tasks);

		int32 Imported = 0;
		for (UAssetImportTask* Task : Tasks)
		{
			Imported += Task ? Task->ImportedObjectPaths.Num() : 0;
		}
		UE_LOG(LogHephaestusBridge, Log,
			TEXT("editor.import_fbx: imported %d texture(s) from %s"), Imported, *FbmDir);
		return Imported;
	}

	static UTexture* LoadImportedTexture(const FString& DestinationPath, const FString& TextureName)
	{
		const FString ObjectPath = DestinationPath / TextureName + TEXT(".") + TextureName;
		return LoadObject<UTexture>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	static UMaterialInstanceConstant* CreateOrUpdateMic(
		const FString& DestinationPath,
		const FString& MicName,
		UMaterialInterface* Parent,
		UTexture* Diffuse,
		UTexture* Normal,
		UTexture* Opacity)
	{
		if (!Parent)
		{
			return nullptr;
		}

		const FString PackagePath = DestinationPath / MicName;
		UMaterialInstanceConstant* MIC = LoadObject<UMaterialInstanceConstant>(
			nullptr, *(PackagePath + TEXT(".") + MicName), nullptr, LOAD_NoWarn | LOAD_Quiet);

		if (!MIC)
		{
			UMaterialInstanceConstantFactoryNew* Factory = NewObject<UMaterialInstanceConstantFactoryNew>();
			Factory->InitialParent = Parent;
			UPackage* Package = CreatePackage(*PackagePath);
			MIC = Cast<UMaterialInstanceConstant>(Factory->FactoryCreateNew(
				UMaterialInstanceConstant::StaticClass(),
				Package,
				*MicName,
				RF_Public | RF_Standalone,
				nullptr,
				GWarn));
			if (MIC)
			{
				FAssetRegistryModule::AssetCreated(MIC);
			}
		}
		else
		{
			MIC->SetParentEditorOnly(Parent);
		}

		if (!MIC)
		{
			return nullptr;
		}

		if (Diffuse)
		{
			MIC->SetTextureParameterValueEditorOnly(FName(TEXT("DiffuseColorMap")), Diffuse);
			MIC->SetScalarParameterValueEditorOnly(FName(TEXT("DiffuseColorMapWeight")), 1.0f);
			MIC->SetVectorParameterValueEditorOnly(FName(TEXT("DiffuseColor")), FLinearColor::White);
		}
		if (Normal)
		{
			MIC->SetTextureParameterValueEditorOnly(FName(TEXT("NormalMap")), Normal);
			MIC->SetScalarParameterValueEditorOnly(FName(TEXT("NormalMapWeight")), 1.0f);
		}
		if (Opacity)
		{
			MIC->SetTextureParameterValueEditorOnly(FName(TEXT("OpacityMap")), Opacity);
			MIC->SetTextureParameterValueEditorOnly(FName(TEXT("OpacityMaskMap")), Opacity);
			MIC->SetScalarParameterValueEditorOnly(FName(TEXT("OpacityMapWeight")), 1.0f);
			MIC->SetScalarParameterValueEditorOnly(FName(TEXT("OpacityMaskMapWeight")), 1.0f);
		}

		MIC->PostEditChange();
		MIC->MarkPackageDirty();
		return MIC;
	}

	static UMaterialInterface* LoadPhongParent(bool bMasked)
	{
		const TCHAR* Candidates[] = {
			bMasked
				? TEXT("/InterchangeAssets/Materials/PhongSurfaceMaskMaterial.PhongSurfaceMaskMaterial")
				: TEXT("/InterchangeAssets/Materials/FBXLegacyPhongSurfaceMaterial.FBXLegacyPhongSurfaceMaterial"),
			bMasked
				? TEXT("/Interchange/Materials/PhongSurfaceMaskMaterial.PhongSurfaceMaskMaterial")
				: TEXT("/Interchange/Materials/FBXLegacyPhongSurfaceMaterial.FBXLegacyPhongSurfaceMaterial"),
			bMasked
				? TEXT("/InterchangeAssets/Materials/PhongSurfaceTranslucentMaterial.PhongSurfaceTranslucentMaterial")
				: TEXT("/InterchangeAssets/Materials/PhongSurfaceMaterial.PhongSurfaceMaterial"),
		};
		for (const TCHAR* Path : Candidates)
		{
			if (UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, Path, nullptr, LOAD_None, nullptr))
			{
				return Mat;
			}
		}

		// Fallback: AssetRegistry lookup by short name.
		const FName Wanted = bMasked
			? FName(TEXT("PhongSurfaceMaskMaterial"))
			: FName(TEXT("FBXLegacyPhongSurfaceMaterial"));
		FAssetRegistryModule& AssetRegistryModule =
			FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
		TArray<FAssetData> Assets;
		AssetRegistryModule.Get().GetAssetsByClass(
			UMaterialInterface::StaticClass()->GetClassPathName(), Assets, true);
		for (const FAssetData& Asset : Assets)
		{
			if (Asset.AssetName == Wanted)
			{
				if (UMaterialInterface* Mat = Cast<UMaterialInterface>(Asset.GetAsset()))
				{
					return Mat;
				}
			}
		}
		return nullptr;
	}

	/**
	 * CC5/Reallusion FBX often ships Diffuse maps only in the sibling .fbm folder and
	 * does not link them as FBX material textures (normals may still be linked). Rebuild
	 * slot materials as Phong MICs wired by naming convention.
	 */
	static int32 BindFbmTexturesToSkeletalMesh(USkeletalMesh* Mesh, const FString& DestinationPath)
	{
		if (!Mesh)
		{
			return 0;
		}

		UMaterialInterface* ParentOpaque = LoadPhongParent(false);
		UMaterialInterface* ParentMasked = LoadPhongParent(true);
		if (!ParentOpaque)
		{
			UE_LOG(LogHephaestusBridge, Warning,
				TEXT("editor.import_fbx: Phong parent material missing — cannot bind CC5 textures"));
			return 0;
		}
		UE_LOG(LogHephaestusBridge, Log,
			TEXT("editor.import_fbx: Phong parent=%s masked=%s"),
			*ParentOpaque->GetPathName(),
			ParentMasked ? *ParentMasked->GetPathName() : TEXT("(none)"));

		TArray<FSkeletalMaterial>& Materials = Mesh->GetMaterials();
		int32 Bound = 0;
		for (int32 Index = 0; Index < Materials.Num(); ++Index)
		{
			FString MatName;
			if (Materials[Index].MaterialInterface)
			{
				MatName = Materials[Index].MaterialInterface->GetName();
			}
			if (MatName.IsEmpty() && !Materials[Index].MaterialSlotName.IsNone())
			{
				MatName = Materials[Index].MaterialSlotName.ToString();
			}
			if (MatName.IsEmpty())
			{
				continue;
			}
			// Strip accidental _MI suffix if re-binding.
			if (MatName.EndsWith(TEXT("_MI")))
			{
				MatName.LeftChopInline(3);
			}

			UTexture* Diffuse = LoadImportedTexture(DestinationPath, MatName + TEXT("_Diffuse"));
			UTexture* Normal = LoadImportedTexture(DestinationPath, MatName + TEXT("_Normal"));
			UTexture* Opacity = LoadImportedTexture(DestinationPath, MatName + TEXT("_Opacity"));
			if (!Diffuse && !Normal && !Opacity)
			{
				continue;
			}

			UMaterialInterface* Parent = (Opacity && ParentMasked) ? ParentMasked : ParentOpaque;
			const FString MicName = MatName + TEXT("_MI");
			UMaterialInstanceConstant* MIC = CreateOrUpdateMic(
				DestinationPath, MicName, Parent, Diffuse, Normal, Opacity);
			if (!MIC)
			{
				continue;
			}

			Materials[Index].MaterialInterface = MIC;
			UE_LOG(LogHephaestusBridge, Log,
				TEXT("editor.import_fbx: slot %d '%s' -> %s (diffuse=%s normal=%s opacity=%s)"),
				Index, *MatName, *MIC->GetName(),
				Diffuse ? *Diffuse->GetName() : TEXT("-"),
				Normal ? *Normal->GetName() : TEXT("-"),
				Opacity ? *Opacity->GetName() : TEXT("-"));
			++Bound;
		}

		if (Bound > 0)
		{
			Mesh->Modify();
			Mesh->SetMaterials(Materials);
			Mesh->PostEditChange();
			Mesh->MarkPackageDirty();

			TArray<UPackage*> PackagesToSave;
			PackagesToSave.Add(Mesh->GetOutermost());
			for (const FSkeletalMaterial& Slot : Materials)
			{
				if (Slot.MaterialInterface)
				{
					PackagesToSave.AddUnique(Slot.MaterialInterface->GetOutermost());
				}
			}
			UEditorLoadingAndSavingUtils::SavePackages(PackagesToSave, /*bOnlyDirty=*/true);

			UE_LOG(LogHephaestusBridge, Log,
				TEXT("editor.import_fbx: bound FBM textures on %d/%d material slot(s) for %s"),
				Bound, Materials.Num(), *Mesh->GetName());
		}
		return Bound;
	}
} // namespace HephaestusFbxImport


void UHephaestusEditorRemoteSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	int32 PortOverride = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("HephaestusEditorPort="), PortOverride) && PortOverride > 0)
	{
		ListenPort = PortOverride;
	}

	if (StartHttpServer())
	{
		UE_LOG(LogHephaestusBridge, Log,
			TEXT("HephaestusEditorRemote: listening on http://127.0.0.1:%d  (editor.play / editor.stop / editor.import_fbx)"),
			ListenPort);
	}
	else
	{
		UE_LOG(LogHephaestusBridge, Error,
			TEXT("HephaestusEditorRemote: failed to bind port %d"), ListenPort);
	}
}

void UHephaestusEditorRemoteSubsystem::Deinitialize()
{
	StopHttpServer();
	Super::Deinitialize();
}

bool UHephaestusEditorRemoteSubsystem::StartHttpServer()
{
	if (!FHttpServerModule::IsAvailable())
	{
		FModuleManager::LoadModuleChecked<FHttpServerModule>(TEXT("HTTPServer"));
	}

	HttpRouter = FHttpServerModule::Get().GetHttpRouter(static_cast<uint32>(ListenPort), /*bFailOnBindFailure=*/true);
	if (!HttpRouter.IsValid())
	{
		return false;
	}

	HealthRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/health")),
		EHttpServerRequestVerbs::VERB_GET,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleHealth));

	CommandRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/command")),
		EHttpServerRequestVerbs::VERB_POST,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCommand));

	CorsHealthRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/health")),
		EHttpServerRequestVerbs::VERB_OPTIONS,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCors));

	CorsCommandRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/command")),
		EHttpServerRequestVerbs::VERB_OPTIONS,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCors));

	if (!HealthRoute.IsValid() || !CommandRoute.IsValid())
	{
		StopHttpServer();
		return false;
	}

	FHttpServerModule::Get().StartAllListeners();
	bIsListening = true;
	return true;
}

void UHephaestusEditorRemoteSubsystem::StopHttpServer()
{
	if (HttpRouter.IsValid())
	{
		auto Unbind = [this](FHttpRouteHandle& Handle)
		{
			if (Handle.IsValid())
			{
				HttpRouter->UnbindRoute(Handle);
				Handle.Reset();
			}
		};
		Unbind(HealthRoute);
		Unbind(CommandRoute);
		Unbind(CorsHealthRoute);
		Unbind(CorsCommandRoute);
		HttpRouter.Reset();
	}
	bIsListening = false;
}

void UHephaestusEditorRemoteSubsystem::ApplyCors(TUniquePtr<FHttpServerResponse>& Response)
{
	if (!Response.IsValid())
	{
		return;
	}
	Response->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });
	Response->Headers.Add(TEXT("Access-Control-Allow-Methods"), { TEXT("GET, POST, OPTIONS") });
	Response->Headers.Add(TEXT("Access-Control-Allow-Headers"), { TEXT("Content-Type") });
}

bool UHephaestusEditorRemoteSubsystem::HandleCors(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(TEXT(""), TEXT("text/plain"));
	Response->Code = EHttpServerResponseCodes::NoContent;
	ApplyCors(Response);
	OnComplete(MoveTemp(Response));
	return true;
}

bool UHephaestusEditorRemoteSubsystem::IsPieActive()
{
	return GEditor != nullptr && GEditor->PlayWorld != nullptr;
}

bool UHephaestusEditorRemoteSubsystem::RequestPlay()
{
	if (!GUnrealEd)
	{
		return false;
	}
	if (IsPieActive())
	{
		return true;
	}
	FRequestPlaySessionParams Params;
	GUnrealEd->RequestPlaySession(Params);
	return true;
}

bool UHephaestusEditorRemoteSubsystem::RequestStop()
{
	if (!GUnrealEd)
	{
		return false;
	}
	if (!IsPieActive())
	{
		return true;
	}
	GUnrealEd->RequestEndPlayMap();
	return true;
}

bool UHephaestusEditorRemoteSubsystem::RequestImportFbx(
	const TSharedPtr<FJsonObject>& Params,
	FString& OutAssetPath,
	FString& OutError,
	bool& OutSkeletal,
	TArray<FString>& OutAssetPaths)
{
	OutAssetPath.Reset();
	OutError.Reset();
	OutSkeletal = false;
	OutAssetPaths.Reset();

	if (IsPieActive())
	{
		OutError = TEXT("editor.import_fbx refused while PIE is active — stop Play first");
		return false;
	}

	FString FilePath;
	FString DestinationPath = TEXT("/Game/Hephaestus/DccImports");
	FString DestinationName;
	bool bImportAsSkeletal = false;
	if (Params.IsValid())
	{
		Params->TryGetStringField(TEXT("source_path"), FilePath);
		if (FilePath.IsEmpty())
		{
			Params->TryGetStringField(TEXT("file_path"), FilePath);
		}
		FString Dest;
		if (Params->TryGetStringField(TEXT("destination_path"), Dest) && !Dest.IsEmpty())
		{
			DestinationPath = Dest;
		}
		Params->TryGetStringField(TEXT("destination_name"), DestinationName);
		Params->TryGetBoolField(TEXT("import_as_skeletal"), bImportAsSkeletal);
		if (!bImportAsSkeletal)
		{
			Params->TryGetBoolField(TEXT("skeletal"), bImportAsSkeletal);
		}
	}
	if (FilePath.IsEmpty())
	{
		OutError = TEXT("editor.import_fbx requires params.source_path or params.file_path");
		return false;
	}
	if (!FPaths::FileExists(FilePath))
	{
		OutError = FString::Printf(TEXT("editor.import_fbx: file not found: %s"), *FilePath);
		return false;
	}
	if (DestinationName.IsEmpty())
	{
		DestinationName = FPaths::GetBaseFilename(FilePath);
	}

	FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools");

	UAssetImportTask* ImportTask = NewObject<UAssetImportTask>();
	ImportTask->Filename = FilePath;
	ImportTask->DestinationPath = DestinationPath;
	ImportTask->DestinationName = DestinationName;
	ImportTask->bAutomated = true;
	ImportTask->bSave = true;
	ImportTask->bReplaceExisting = true;
	ImportTask->bReplaceExistingSettings = true;

	// UE 5.5+ routes FBX through Interchange by default, which often imports the
	// skeletal mesh without creating materials/textures from the sibling .fbm
	// folder (CC5/Reallusion exports). Force the legacy FbxFactory path for
	// Hephaestus imports so ImportUI material/texture flags are honored.
	IConsoleVariable* InterchangeFbxCVar = IConsoleManager::Get().FindConsoleVariable(
		TEXT("Interchange.FeatureFlags.Import.FBX"));
	const int32 PreviousInterchangeFbx = InterchangeFbxCVar ? InterchangeFbxCVar->GetInt() : 1;
	if (InterchangeFbxCVar)
	{
		InterchangeFbxCVar->Set(0, ECVF_SetByCode);
	}

	if (bImportAsSkeletal)
	{
		UFbxImportUI* ImportUI = NewObject<UFbxImportUI>();
		ImportUI->bImportAsSkeletal = true;
		ImportUI->bImportMesh = true;
		ImportUI->bImportAnimations = false;
		ImportUI->bImportMaterials = true;
		ImportUI->bImportTextures = true;
		ImportUI->bAutomatedImportShouldDetectType = false;
		ImportUI->MeshTypeToImport = FBXIT_SkeletalMesh;
		if (ImportUI->SkeletalMeshImportData)
		{
			ImportUI->SkeletalMeshImportData->bImportMorphTargets = true;
		}
		if (ImportUI->TextureImportData)
		{
			ImportUI->TextureImportData->MaterialSearchLocation = EMaterialSearchLocation::Local;
			ImportUI->TextureImportData->bInvertNormalMaps = true;
		}
		UFbxFactory* FbxFactory = NewObject<UFbxFactory>();
		FbxFactory->ImportUI = ImportUI;
		ImportTask->Options = ImportUI;
		ImportTask->Factory = FbxFactory;
	}

	TArray<UAssetImportTask*> Tasks;
	Tasks.Add(ImportTask);
	AssetToolsModule.Get().ImportAssetTasks(Tasks);

	TArray<UObject*> Imported;
	for (const FString& Path : ImportTask->ImportedObjectPaths)
	{
		if (UObject* Obj = FSoftObjectPath(Path).TryLoad())
		{
			Imported.Add(Obj);
			OutAssetPaths.Add(Obj->GetPathName());
		}
	}

	if (Imported.Num() == 0)
	{
		UAutomatedAssetImportData* ImportData = NewObject<UAutomatedAssetImportData>();
		ImportData->Filenames.Add(FilePath);
		ImportData->DestinationPath = DestinationPath;
		ImportData->bReplaceExisting = true;
		ImportData->bSkipReadOnly = true;
		ImportData->GroupName = TEXT("HephaestusEditorImport");
		Imported = AssetToolsModule.Get().ImportAssetsAutomated(ImportData);
		for (UObject* Obj : Imported)
		{
			if (Obj)
			{
				OutAssetPaths.Add(Obj->GetPathName());
			}
		}
	}

	if (InterchangeFbxCVar)
	{
		InterchangeFbxCVar->Set(PreviousInterchangeFbx, ECVF_SetByCode);
	}

	if (Imported.Num() == 0)
	{
		OutError = TEXT("editor.import_fbx: AssetTools produced no assets");
		return false;
	}

	// Prefer SkeletalMesh matching destination_name, then any SkeletalMesh, then StaticMesh.
	UObject* Chosen = nullptr;
	auto NameMatches = [&DestinationName](UObject* Obj) -> bool
	{
		if (!Obj || DestinationName.IsEmpty())
		{
			return false;
		}
		return Obj->GetName().Equals(DestinationName, ESearchCase::IgnoreCase);
	};
	for (UObject* Obj : Imported)
	{
		if (Cast<USkeletalMesh>(Obj) && NameMatches(Obj))
		{
			Chosen = Obj;
			OutSkeletal = true;
			break;
		}
	}
	if (!Chosen)
	{
		for (UObject* Obj : Imported)
		{
			if (Cast<USkeletalMesh>(Obj))
			{
				Chosen = Obj;
				OutSkeletal = true;
				break;
			}
		}
	}
	if (!Chosen)
	{
		for (UObject* Obj : Imported)
		{
			if (Cast<UStaticMesh>(Obj) && NameMatches(Obj))
			{
				Chosen = Obj;
				break;
			}
		}
	}
	if (!Chosen)
	{
		for (UObject* Obj : Imported)
		{
			if (Cast<UStaticMesh>(Obj))
			{
				Chosen = Obj;
				break;
			}
		}
	}
	if (!Chosen)
	{
		Chosen = Imported[0];
		OutSkeletal = Cast<USkeletalMesh>(Chosen) != nullptr;
	}
	else
	{
		OutSkeletal = Cast<USkeletalMesh>(Chosen) != nullptr;
	}

	// CC5: import sibling .fbm textures and wire Phong MICs onto skeletal slots.
	if (USkeletalMesh* SkelMesh = Cast<USkeletalMesh>(Chosen))
	{
		HephaestusFbxImport::ImportFbmTextures(FilePath, DestinationPath);
		HephaestusFbxImport::BindFbmTexturesToSkeletalMesh(SkelMesh, DestinationPath);
	}

	OutAssetPath = Chosen->GetPathName();
	UE_LOG(LogHephaestusBridge, Log, TEXT("editor.import_fbx: %s -> %s (skeletal=%s)"),
		*FilePath, *OutAssetPath, OutSkeletal ? TEXT("true") : TEXT("false"));
	return true;
}

bool UHephaestusEditorRemoteSubsystem::HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("ok"), true);
	Root->SetStringField(TEXT("service"), TEXT("hephaestus-editor"));
	Root->SetNumberField(TEXT("port"), ListenPort);
	Root->SetNumberField(TEXT("pie_port"), 8765);
	Root->SetBoolField(TEXT("pie_active"), IsPieActive());
	Root->SetStringField(TEXT("plugin_version"), HEPHAESTUS_BRIDGE_VERSION);
	Root->SetStringField(TEXT("project_name"), FApp::GetProjectName());
	Root->SetStringField(TEXT("project_dir"), FPaths::ConvertRelativePathToFull(FPaths::ProjectDir()));

	FString Body;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
	FJsonSerializer::Serialize(Root, Writer);

	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(Body, TEXT("application/json"));
	Response->Code = EHttpServerResponseCodes::Ok;
	ApplyCors(Response);
	OnComplete(MoveTemp(Response));
	return true;
}

bool UHephaestusEditorRemoteSubsystem::HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	const FString CommandJSON = BodyToString(Request.Body);
	if (CommandJSON.IsEmpty())
	{
		TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Error(
			EHttpServerResponseCodes::BadRequest, TEXT("empty_body"), TEXT("POST body must be command JSON"));
		ApplyCors(Response);
		OnComplete(MoveTemp(Response));
		return true;
	}

	TWeakObjectPtr<UHephaestusEditorRemoteSubsystem> WeakThis(this);
	AsyncTask(ENamedThreads::GameThread, [WeakThis, CommandJSON, OnComplete]()
	{
		bool bSuccess = false;
		FString Error;
		FString Action;
		FString ResultJson = TEXT("{}");

		TSharedPtr<FJsonObject> JsonObject;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(CommandJSON);
		if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
		{
			Error = TEXT("Invalid JSON");
		}
		else
		{
			Action = JsonObject->GetStringField(TEXT("command"));
			const TSharedPtr<FJsonObject>* ParamsPtr = nullptr;
			TSharedPtr<FJsonObject> Params;
			if (JsonObject->TryGetObjectField(TEXT("params"), ParamsPtr) && ParamsPtr)
			{
				Params = *ParamsPtr;
			}
			else if (JsonObject->TryGetObjectField(TEXT("args"), ParamsPtr) && ParamsPtr)
			{
				Params = *ParamsPtr;
			}

			if (Action.Equals(TEXT("editor.play"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.start"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.play"), ESearchCase::IgnoreCase))
			{
				bSuccess = WeakThis.IsValid() && RequestPlay();
				if (!bSuccess)
				{
					Error = TEXT("Failed to request Play session (is UnrealEd available?)");
				}
				else
				{
					ResultJson = FString::Printf(
						TEXT("{\"action\":\"%s\",\"pie_active\":%s}"),
						*Action, IsPieActive() ? TEXT("true") : TEXT("false"));
				}
			}
			else if (Action.Equals(TEXT("editor.stop"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.stop"), ESearchCase::IgnoreCase))
			{
				bSuccess = WeakThis.IsValid() && RequestStop();
				if (!bSuccess)
				{
					Error = TEXT("Failed to request End Play (is UnrealEd available?)");
				}
				else
				{
					ResultJson = FString::Printf(
						TEXT("{\"action\":\"%s\",\"pie_active\":%s}"),
						*Action, IsPieActive() ? TEXT("true") : TEXT("false"));
				}
			}
			else if (Action.Equals(TEXT("editor.import_fbx"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("editor.import"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("asset.import_fbx"), ESearchCase::IgnoreCase))
			{
				// Defer AssetTools off this TaskGraph task — Interchange WaitUntilDone nested
				// inside AsyncTask(GameThread) trips RecursionGuard and crashes the editor.
				TSharedPtr<FJsonObject> ParamsCopy = Params;
				const FString ActionCopy = Action;
				FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda(
					[WeakThis, ParamsCopy, ActionCopy, OnComplete](float)
					{
						bool bImportOk = false;
						FString ImportError;
						FString ImportResultJson = TEXT("{}");
						FString AssetPath;
						bool bSkeletal = false;
						TArray<FString> AssetPaths;
						bImportOk = WeakThis.IsValid()
							&& RequestImportFbx(ParamsCopy, AssetPath, ImportError, bSkeletal, AssetPaths);
						if (bImportOk)
						{
							FString Escaped = AssetPath;
							Escaped.ReplaceInline(TEXT("\\"), TEXT("/"));
							FString PathsJson = TEXT("[");
							for (int32 i = 0; i < AssetPaths.Num(); ++i)
							{
								FString P = AssetPaths[i];
								P.ReplaceInline(TEXT("\\"), TEXT("/"));
								if (i > 0)
								{
									PathsJson += TEXT(",");
								}
								PathsJson += FString::Printf(TEXT("\"%s\""), *P);
							}
							PathsJson += TEXT("]");
							ImportResultJson = FString::Printf(
								TEXT("{\"action\":\"editor.import_fbx\",\"asset_path\":\"%s\",\"skeletal\":%s,\"asset_paths\":%s,\"pie_active\":%s}"),
								*Escaped,
								bSkeletal ? TEXT("true") : TEXT("false"),
								*PathsJson,
								IsPieActive() ? TEXT("true") : TEXT("false"));
						}

						TSharedRef<FJsonObject> ImportOut = MakeShared<FJsonObject>();
						ImportOut->SetBoolField(TEXT("success"), bImportOk);
						ImportOut->SetStringField(TEXT("error"), ImportError);
						ImportOut->SetStringField(TEXT("command"), ActionCopy);
						ImportOut->SetBoolField(TEXT("pie_active"), IsPieActive());
						ImportOut->SetStringField(TEXT("result_json"), bImportOk ? ImportResultJson : TEXT("{}"));

						FString ImportBody;
						TSharedRef<TJsonWriter<>> ImportWriter = TJsonWriterFactory<>::Create(&ImportBody);
						FJsonSerializer::Serialize(ImportOut, ImportWriter);

						TUniquePtr<FHttpServerResponse> ImportResponse =
							FHttpServerResponse::Create(ImportBody, TEXT("application/json"));
						ImportResponse->Code = bImportOk
							? EHttpServerResponseCodes::Ok
							: EHttpServerResponseCodes::BadRequest;
						ApplyCors(ImportResponse);
						OnComplete(MoveTemp(ImportResponse));
						return false;
					}));
				return;
			}
			else
			{
				Error = FString::Printf(
					TEXT("Unknown editor command '%s' (use editor.play, editor.stop, or editor.import_fbx)"),
					*Action);
			}
		}

		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetBoolField(TEXT("success"), bSuccess);
		Out->SetStringField(TEXT("error"), Error);
		Out->SetStringField(TEXT("command"), Action);
		Out->SetBoolField(TEXT("pie_active"), IsPieActive());
		Out->SetStringField(TEXT("result_json"), bSuccess ? ResultJson : TEXT("{}"));

		FString ResponseBody;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResponseBody);
		FJsonSerializer::Serialize(Out, Writer);

		TUniquePtr<FHttpServerResponse> Response =
			FHttpServerResponse::Create(ResponseBody, TEXT("application/json"));
		Response->Code = bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest;
		ApplyCors(Response);
		OnComplete(MoveTemp(Response));
	});

	return true;
}

FString UHephaestusEditorRemoteSubsystem::BodyToString(const TArray<uint8>& Body)
{
	if (Body.Num() == 0)
	{
		return FString();
	}
	TArray<uint8> NullTerminated = Body;
	NullTerminated.Add(0);
	return FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(NullTerminated.GetData())));
}

#endif // WITH_EDITOR
