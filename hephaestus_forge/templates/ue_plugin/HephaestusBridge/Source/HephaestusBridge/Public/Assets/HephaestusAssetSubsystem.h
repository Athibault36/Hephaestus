// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusAssetSubsystem.generated.h"

class UMaterial;
class UMaterialInstanceDynamic;
class UObject;

/** Material creation description */
USTRUCT(BlueprintType)
struct FHephaestusMaterialDesc
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Name;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString BaseMaterialPath = TEXT("/Hephaestus/Materials/MF_Master_Base");

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> Parameters; // Parameter name -> value

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TMap<FString, FString> TextureParameters; // Parameter name -> texture path

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    TArray<FString> StaticSwitches; // Enabled static switches

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString SavePath = TEXT("/Game/Hephaestus/Materials/");
};

/** Import options */
USTRUCT(BlueprintType)
struct FHephaestusImportOptions
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bAutoGenerateCollision = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bImportMaterials = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bImportTextures = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    float UniformScale = 1.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bConvertScene = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    bool bForceFrontXAxis = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString StaticMeshLODGroup = TEXT("Default");
};

/**
 * UHephaestusAssetSubsystem
 * 
 * Asset creation, import, reimport, export, and material management.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusAssetSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Create a material from description */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    UMaterial* CreateMaterial(const FHephaestusMaterialDesc& Desc);

    /** Import asset from file */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    UObject* ImportAsset(const FString& FilePath, const FString& DestinationPath, const FHephaestusImportOptions& Options);

    /** Reimport an existing asset */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    bool ReimportAsset(UObject* Asset);

    /** Export asset to file */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    bool ExportAsset(UObject* Asset, const FString& FilePath, const FString& ExportOptions = TEXT(""));

    /** Create material instance from parent */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    UMaterialInstanceDynamic* CreateMaterialInstance(UMaterial* ParentMaterial, const TMap<FString, FString>& Parameters);

    /** Find asset by path */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    UObject* FindAsset(const FString& AssetPath) const;

    /** Get all assets in path */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Assets")
    TArray<UObject*> GetAssetsInPath(const FString& Path, TSubclassOf<UObject> ClassFilter = nullptr) const;
};