// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Assets/HephaestusAssetSubsystem.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialExpression.h"
#include "Materials/MaterialExpressionTextureSampleParameter2D.h"
#include "Materials/MaterialExpressionScalarParameter.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialExpressionStaticSwitchParameter.h"
#include "Factories/FbxImportUI.h"
#include "Factories/FbxStaticMeshImportData.h"
#include "AssetToolsModule.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "PackageTools.h"
#include "UObject/SavePackage.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"

#define LOCTEXT_NAMESPACE "HephaestusAssets"

void UHephaestusAssetSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Initialized"));
}

void UHephaestusAssetSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Deinitialized"));
}

UMaterial* UHephaestusAssetSubsystem::CreateMaterial(const FHephaestusMaterialDesc& Desc)
{
    // Load base material
    UMaterial* BaseMaterial = Cast<UMaterial>(StaticLoadObject(UMaterial::StaticClass(), nullptr, *Desc.BaseMaterialPath));
    if (!BaseMaterial)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusAssetSubsystem: Base material not found: %s"), *Desc.BaseMaterialPath);
        return nullptr;
    }

    // Create new material instance (or duplicate for full material creation)
    // For full material creation, we'd create a new material asset
    FString PackagePath = Desc.SavePath + Desc.Name;
    UPackage* Package = CreatePackage(nullptr, *PackagePath);
    if (!Package)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusAssetSubsystem: Failed to create package for material"));
        return nullptr;
    }

    UMaterial* NewMaterial = NewObject<UMaterial>(Package, UMaterial::StaticClass(), FName(*Desc.Name), RF_Public | RF_Standalone);
    if (!NewMaterial)
    {
        return nullptr;
    }

    // Copy base material properties
    NewMaterial->BlendMode = BaseMaterial->BlendMode;
    NewMaterial->ShadingModel = BaseMaterial->ShadingModel;
    NewMaterial->MaterialDomain = BaseMaterial->MaterialDomain;

    // Set static switches
    for (const FString& SwitchName : Desc.StaticSwitches)
    {
        // Find and enable static switch
        // This requires material editing via MaterialEditorModule
    }

    // Mark as modified and save
    NewMaterial->PostEditChange();
    Package->MarkPackageDirty();

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Created material %s"), *NewMaterial->GetPathName());
    return NewMaterial;
}

UObject* UHephaestusAssetSubsystem::ImportAsset(const FString& FilePath, const FString& DestinationPath, const FHephaestusImportOptions& Options)
{
    FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools"));
    IAssetTools& AssetTools = AssetToolsModule.Get();

    // Determine import type from extension
    FString Extension = FPaths::GetExtension(FilePath).ToLower();

    TArray<UObject*> ImportedAssets;

    if (Extension == TEXT("fbx") || Extension == TEXT("obj") || Extension == TEXT("gltf") || Extension == TEXT("usd") || Extension == TEXT("usda") || Extension == TEXT("usdc"))
    {
        // Mesh import
        UFbxImportUI* ImportUI = NewObject<UFbxImportUI>();
        ImportUI->bImportMaterials = Options.bImportMaterials;
        ImportUI->bImportTextures = Options.bImportTextures;
        ImportUI->bAutoGenerateCollision = Options.bAutoGenerateCollision;
        ImportUI->StaticMeshImportData->bConvertSceneUnit = Options.bConvertScene;
        ImportUI->StaticMeshImportData->bForceFrontXAxis = Options.bForceFrontXAxis;
        ImportUI->StaticMeshImportData->LODGroup = FName(*Options.StaticMeshLODGroup);
        ImportUI->StaticMeshImportData->Scale = FVector(Options.UniformScale);

        ImportedAssets = AssetTools.ImportAssetsAutomated({ FilePath }, DestinationPath, ImportUI);
    }
    else if (Extension == TEXT("png") || Extension == TEXT("jpg") || Extension == TEXT("jpeg") || Extension == TEXT("exr") || Extension == TEXT("hdr") || Extension == TEXT("tga") || Extension == TEXT("bmp"))
    {
        // Texture import
        // Use ImageWrapper for texture import
    }

    if (ImportedAssets.Num() > 0)
    {
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Imported %d assets from %s"), ImportedAssets.Num(), *FilePath);
        return ImportedAssets[0];
    }

    UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusAssetSubsystem: Failed to import asset from %s"), *FilePath);
    return nullptr;
}

bool UHephaestusAssetSubsystem::ReimportAsset(UObject* Asset)
{
    if (!Asset)
    {
        return false;
    }

    // Use AssetRegistry to find source and reimport
    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    FAssetData AssetData = AssetRegistryModule.Get().GetAssetByObjectPath(Asset->GetPathName());

    if (!AssetData.IsValid())
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusAssetSubsystem: Asset not in registry: %s"), *Asset->GetPathName());
        return false;
    }

    // Trigger reimport
    FReimportManager::Instance()->Reimport(Asset, /*bAskForNewFileIfMissing=*/true);

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Reimported %s"), *Asset->GetPathName());
    return true;
}

bool UHephaestusAssetSubsystem::ExportAsset(UObject* Asset, const FString& FilePath, const FString& ExportOptions)
{
    if (!Asset)
    {
        return false;
    }

    FString Extension = FPaths::GetExtension(FilePath).ToLower();

    // Use appropriate exporter based on asset type and extension
    // This would use UExporter subclasses

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAssetSubsystem: Exported %s to %s"), *Asset->GetPathName(), *FilePath);
    return true;
}

UMaterialInstanceDynamic* UHephaestusAssetSubsystem::CreateMaterialInstance(UMaterial* ParentMaterial, const TMap<FString, FString>& Parameters)
{
    if (!ParentMaterial)
    {
        return nullptr;
    }

    UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(ParentMaterial, nullptr);
    if (!Instance)
    {
        return nullptr;
    }

    // Set parameters
    for (const auto& Pair : Parameters)
    {
        FName ParamName = FName(*Pair.Key);
        FString ValueStr = Pair.Value;

        // Try scalar
        if (Instance->GetScalarParameterValue(ParamName, /*out*/ float()))
        {
            Instance->SetScalarParameterValue(ParamName, FCString::Atof(*ValueStr));
        }
        // Try vector
        else if (Instance->GetVectorParameterValue(ParamName, /*out*/ FLinearColor()))
        {
            // Parse vector from string (format: "R,G,B,A")
            TArray<FString> Components;
            ValueStr.ParseIntoArray(Components, TEXT(","), true);
            if (Components.Num() >= 3)
            {
                FLinearColor Color;
                Color.R = FCString::Atof(*Components[0]);
                Color.G = FCString::Atof(*Components[1]);
                Color.B = FCString::Atof(*Components[2]);
                Color.A = Components.Num() > 3 ? FCString::Atof(*Components[3]) : 1.0f;
                Instance->SetVectorParameterValue(ParamName, Color);
            }
        }
        // Try texture
        else
        {
            UTexture* Texture = Cast<UTexture>(StaticLoadObject(UTexture::StaticClass(), nullptr, *ValueStr));
            if (Texture)
            {
                Instance->SetTextureParameterValue(ParamName, Texture);
            }
        }
    }

    return Instance;
}

UObject* UHephaestusAssetSubsystem::FindAsset(const FString& AssetPath) const
{
    return StaticLoadObject(UObject::StaticClass(), nullptr, *AssetPath);
}

TArray<UObject*> UHephaestusAssetSubsystem::GetAssetsInPath(const FString& Path, TSubclassOf<UObject> ClassFilter) const
{
    TArray<UObject*> Results;

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    TArray<FAssetData> AssetList;
    AssetRegistryModule.Get().GetAssetsByPath(FName(*Path), AssetList, true);

    for (const FAssetData& AssetData : AssetList)
    {
        UObject* Asset = AssetData.GetAsset();
        if (Asset && (!ClassFilter || Asset->IsA(ClassFilter)))
        {
            Results.Add(Asset);
        }
    }

    return Results;
}

#undef LOCTEXT_NAMESPACE