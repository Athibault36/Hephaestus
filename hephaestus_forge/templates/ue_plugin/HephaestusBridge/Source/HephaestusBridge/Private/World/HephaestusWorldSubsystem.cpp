// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "World/HephaestusWorldSubsystem.h"
#include "HephaestusBridge.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/Blueprint.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/PointLight.h"
#include "Components/StaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Actor.h"
#include "UObject/Class.h"
#include "UObject/Package.h"
#include "UObject/SoftObjectPath.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Modules/ModuleManager.h"

#define LOCTEXT_NAMESPACE "HephaestusWorld"

void UHephaestusWorldSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWorldSubsystem: Initialized"));
}

void UHephaestusWorldSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWorldSubsystem: Deinitialized"));
}

UWorld* UHephaestusWorldSubsystem::ResolveWorld() const
{
    UWorld* World = GetWorld();
    if (!World && GEngine)
    {
        for (const FWorldContext& Context : GEngine->GetWorldContexts())
        {
            if (Context.World() &&
                (Context.WorldType == EWorldType::PIE ||
                 Context.WorldType == EWorldType::Game ||
                 Context.WorldType == EWorldType::Editor))
            {
                World = Context.World();
                if (Context.WorldType == EWorldType::PIE || Context.WorldType == EWorldType::Game)
                {
                    break;
                }
            }
        }
    }
    return World;
}

AActor* UHephaestusWorldSubsystem::SpawnActor(const FString& ClassPath, const FTransform& Transform)
{
    UClass* ActorClass = ResolveClass(ClassPath);
    if (!ActorClass)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusWorldSubsystem: Failed to resolve class: %s"), *ClassPath);
        return nullptr;
    }

    if (!IsSpawnClassAllowed(ClassPath, ActorClass))
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusWorldSubsystem: Class not on spawn allowlist: %s"), *ClassPath);
        return nullptr;
    }

    UWorld* World = ResolveWorld();
    if (!World)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusWorldSubsystem: No world available"));
        return nullptr;
    }

    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

    const FVector Location = Transform.GetLocation();
    const FRotator Rotation = Transform.Rotator();
    AActor* Actor = World->SpawnActor(ActorClass, &Location, &Rotation, Params);
    if (Actor)
    {
        Actor->SetActorScale3D(Transform.GetScale3D());
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWorldSubsystem: Spawned actor %s at %s"),
            *Actor->GetName(), *Transform.GetLocation().ToString());
    }

    return Actor;
}

AActor* UHephaestusWorldSubsystem::SpawnStaticMeshActor(const FString& MeshPath, const FTransform& Transform)
{
    AActor* Actor = SpawnActor(TEXT("/Script/Engine.StaticMeshActor"), Transform);
    AStaticMeshActor* MeshActor = Cast<AStaticMeshActor>(Actor);
    if (!MeshActor)
    {
        return Actor;
    }

    const TArray<FString> Candidates = {
        MeshPath.IsEmpty() ? FString(TEXT("/Engine/BasicShapes/Cube.Cube")) : MeshPath,
        TEXT("/Engine/BasicShapes/Cube.Cube"),
        TEXT("/Engine/EngineMeshes/Cube.Cube"),
        TEXT("/Engine/BasicShapes/Shape_Cube.Shape_Cube"),
    };

    UStaticMeshComponent* Comp = MeshActor->GetStaticMeshComponent();
    if (!Comp)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("SpawnStaticMeshActor: no StaticMeshComponent"));
        return MeshActor;
    }

    // Runtime mesh assignment requires Movable mobility
    Comp->SetMobility(EComponentMobility::Movable);
    Comp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Comp->SetVisibility(true, true);
    Comp->SetHiddenInGame(false);
    MeshActor->SetActorHiddenInGame(false);

    UStaticMesh* Mesh = nullptr;
    FString UsedPath;
    for (const FString& Candidate : Candidates)
    {
        if (Candidate.IsEmpty())
        {
            continue;
        }
        Mesh = LoadObject<UStaticMesh>(nullptr, *Candidate);
        if (!Mesh)
        {
            Mesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *Candidate));
        }
        if (Mesh)
        {
            UsedPath = Candidate;
            break;
        }
    }

    if (!Mesh)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("SpawnStaticMeshActor: failed to load any cube mesh"));
        return MeshActor;
    }

    Comp->SetStaticMesh(Mesh);
    Comp->MarkRenderStateDirty();
    MeshActor->MarkComponentsRenderStateDirty();
    UE_LOG(LogHephaestusBridge, Log, TEXT("SpawnStaticMeshActor: mesh=%s at %s scale=%s"),
        *UsedPath, *MeshActor->GetActorLocation().ToString(), *MeshActor->GetActorScale3D().ToString());

    return MeshActor;
}

bool UHephaestusWorldSubsystem::DestroyActor(const FString& ActorPath, bool bNetForce)
{
    AActor* Actor = FindActorByPath(ActorPath);
    if (!Actor)
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusWorldSubsystem: Actor not found: %s"), *ActorPath);
        return false;
    }

    if (!IsValid(Actor) || Actor->IsActorBeingDestroyed())
    {
        return true;
    }

    Actor->Destroy(bNetForce);
    return true;
}

int32 UHephaestusWorldSubsystem::BatchEditActors(const TArray<FString>& ActorPaths, const TMap<FString, FString>& PropertyEdits)
{
    int32 EditedCount = 0;

    for (const FString& ActorPath : ActorPaths)
    {
        AActor* Actor = FindActorByPath(ActorPath);
        if (!Actor)
        {
            continue;
        }

        for (const auto& Pair : PropertyEdits)
        {
            FProperty* Property = Actor->GetClass()->FindPropertyByName(FName(*Pair.Key));
            if (Property)
            {
                // Parse value from string and set property
                // This is a simplified implementation
                FString ValueStr = Pair.Value;
                bool bSuccess = false;

                if (FNumericProperty* NumericProp = CastField<FNumericProperty>(Property))
                {
                    // Handle numeric types
                    void* ValuePtr = Property->ContainerPtrToValuePtr<void>(Actor);
                    if (FIntProperty* IntProp = CastField<FIntProperty>(Property))
                    {
                        *static_cast<int32*>(ValuePtr) = FCString::Atoi(*ValueStr);
                        bSuccess = true;
                    }
                    else if (FFloatProperty* FloatProp = CastField<FFloatProperty>(Property))
                    {
                        *static_cast<float*>(ValuePtr) = FCString::Atof(*ValueStr);
                        bSuccess = true;
                    }
                }
                else if (FStrProperty* StrProp = CastField<FStrProperty>(Property))
                {
                    *static_cast<FString*>(Property->ContainerPtrToValuePtr<void>(Actor)) = ValueStr;
                    bSuccess = true;
                }
                else if (FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
                {
                    *static_cast<bool*>(Property->ContainerPtrToValuePtr<void>(Actor)) = (ValueStr == TEXT("true") || ValueStr == TEXT("1"));
                    bSuccess = true;
                }
                else if (FObjectProperty* ObjProp = CastField<FObjectProperty>(Property))
                {
                    // Handle object references
                    UObject* Obj = StaticLoadObject(ObjProp->PropertyClass, nullptr, *ValueStr);
                    if (Obj)
                    {
                        *static_cast<UObject**>(Property->ContainerPtrToValuePtr<void>(Actor)) = Obj;
                        bSuccess = true;
                    }
                }

                if (bSuccess)
                {
                    Actor->PostEditChange();
                    EditedCount++;
                }
            }
        }
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWorldSubsystem: Batch edited %d properties on %d actors"), EditedCount, ActorPaths.Num());
    return EditedCount;
}

TArray<AActor*> UHephaestusWorldSubsystem::QuerySpatial(const FBox& Bounds, TSubclassOf<AActor> FilterClass)
{
    TArray<AActor*> Results;
    UWorld* World = ResolveWorld();
    if (!World)
    {
        return Results;
    }

    for (TActorIterator<AActor> It(World, FilterClass); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor && Bounds.IsInside(Actor->GetActorLocation()))
        {
            Results.Add(Actor);
        }
    }

    return Results;
}

IAssetRegistry& UHephaestusWorldSubsystem::GetAssetRegistry()
{
    return FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
}

AActor* UHephaestusWorldSubsystem::FindActorByPath(const FString& ActorPath) const
{
    UWorld* World = ResolveWorld();
    if (!World || ActorPath.IsEmpty())
    {
        return nullptr;
    }

    if (UObject* Obj = StaticFindObject(AActor::StaticClass(), nullptr, *ActorPath))
    {
        if (AActor* Actor = Cast<AActor>(Obj))
        {
            return Actor;
        }
    }

    if (AActor* Soft = Cast<AActor>(FSoftObjectPath(ActorPath).ResolveObject()))
    {
        return Soft;
    }

    FString ShortName = ActorPath;
    int32 DotIdx = INDEX_NONE;
    if (ActorPath.FindLastChar(TEXT('.'), DotIdx))
    {
        ShortName = ActorPath.Mid(DotIdx + 1);
    }

    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->GetName() == ShortName || It->GetPathName() == ActorPath)
        {
            return *It;
        }
    }

    return nullptr;
}

TArray<AActor*> UHephaestusWorldSubsystem::GetAllActorsOfClass(TSubclassOf<AActor> ActorClass) const
{
    TArray<AActor*> Results;
    UWorld* World = ResolveWorld();
    if (!World)
    {
        return Results;
    }

    for (TActorIterator<AActor> It(World, ActorClass); It; ++It)
    {
        Results.Add(*It);
    }

    return Results;
}

TArray<FString> UHephaestusWorldSubsystem::ListActors(const FString& ClassPathFilter) const
{
    TArray<FString> Paths;
    UWorld* World = ResolveWorld();
    if (!World)
    {
        return Paths;
    }

    UClass* FilterClass = nullptr;
    if (!ClassPathFilter.IsEmpty())
    {
        FilterClass = ResolveClass(ClassPathFilter);
    }

    for (TActorIterator<AActor> It(World, FilterClass ? FilterClass : AActor::StaticClass()); It; ++It)
    {
        if (AActor* Actor = *It)
        {
            Paths.Add(Actor->GetPathName());
        }
    }

    return Paths;
}

UClass* UHephaestusWorldSubsystem::ResolveClass(const FString& ClassPath) const
{
    if (ClassPath.IsEmpty())
    {
        return nullptr;
    }

    // Direct load (e.g. /Script/Engine.PointLight)
    if (UClass* Class = LoadClass<AActor>(nullptr, *ClassPath))
    {
        return Class;
    }

    // Short name → /Script/Engine.Name
    if (!ClassPath.Contains(TEXT("/")) && !ClassPath.Contains(TEXT(".")))
    {
        const FString EnginePath = FString::Printf(TEXT("/Script/Engine.%s"), *ClassPath);
        if (UClass* Class = LoadClass<AActor>(nullptr, *EnginePath))
        {
            return Class;
        }
    }

    // Soft object path / asset registry
    if (UObject* Obj = FSoftObjectPath(ClassPath).TryLoad())
    {
        if (UClass* AsClass = Cast<UClass>(Obj))
        {
            return AsClass;
        }
        if (UBlueprint* BP = Cast<UBlueprint>(Obj))
        {
            return BP->GeneratedClass;
        }
    }

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    FAssetData AssetData = AssetRegistryModule.Get().GetAssetByObjectPath(FSoftObjectPath(ClassPath));
    if (AssetData.IsValid())
    {
        if (UObject* Asset = AssetData.GetAsset())
        {
            if (UClass* AsClass = Cast<UClass>(Asset))
            {
                return AsClass;
            }
            if (UBlueprint* BP = Cast<UBlueprint>(Asset))
            {
                return BP->GeneratedClass;
            }
        }
    }

    return nullptr;
}


bool UHephaestusWorldSubsystem::IsSpawnClassAllowed(const FString& ClassPath, UClass* Resolved) const
{
    static const TArray<FString> AllowedExact = {
        TEXT("/Script/Engine.PointLight"),
        TEXT("/Script/Engine.SpotLight"),
        TEXT("/Script/Engine.DirectionalLight"),
        TEXT("/Script/Engine.RectLight"),
        TEXT("/Script/Engine.StaticMeshActor"),
        TEXT("PointLight"),
        TEXT("SpotLight"),
        TEXT("DirectionalLight"),
        TEXT("RectLight"),
        TEXT("StaticMeshActor"),
    };

    for (const FString& Allowed : AllowedExact)
    {
        if (ClassPath.Equals(Allowed, ESearchCase::IgnoreCase))
        {
            return true;
        }
    }

    if (!Resolved)
    {
        return false;
    }

    return Resolved->IsChildOf(APointLight::StaticClass()) ||
        Resolved->IsChildOf(AStaticMeshActor::StaticClass()) ||
        Resolved->GetName().Contains(TEXT("Light"));
}

bool UHephaestusWorldSubsystem::SetActorTransform(const FString& ActorPath, const FTransform& Transform)
{
    AActor* Actor = FindActorByPath(ActorPath);
    if (!Actor)
    {
        return false;
    }
    Actor->SetActorTransform(Transform, false, nullptr, ETeleportType::TeleportPhysics);
    return true;
}

bool UHephaestusWorldSubsystem::SetPointLightProperties(
    const FString& ActorPath,
    float Intensity,
    const FLinearColor& Color,
    float AttenuationRadius)
{
    AActor* Actor = FindActorByPath(ActorPath);
    APointLight* Light = Cast<APointLight>(Actor);
    if (!Light || !Light->PointLightComponent)
    {
        return false;
    }

    UPointLightComponent* Comp = Light->PointLightComponent;
    Comp->SetIntensity(Intensity);
    Comp->SetLightColor(Color);
    if (AttenuationRadius > 0.f)
    {
        Comp->SetAttenuationRadius(AttenuationRadius);
    }
    return true;
}


bool UHephaestusWorldSubsystem::GetView(FVector& OutLocation, FRotator& OutRotation, FVector& OutForward) const
{
    OutLocation = FVector::ZeroVector;
    OutRotation = FRotator::ZeroRotator;
    OutForward = FVector::ForwardVector;

    UWorld* World = ResolveWorld();
    if (!World)
    {
        return false;
    }

    if (APlayerController* PC = World->GetFirstPlayerController())
    {
        PC->GetPlayerViewPoint(OutLocation, OutRotation);
        OutForward = OutRotation.Vector();
        return true;
    }

    if (APlayerCameraManager* CamMgr = UGameplayStatics::GetPlayerCameraManager(World, 0))
    {
        OutLocation = CamMgr->GetCameraLocation();
        OutRotation = CamMgr->GetCameraRotation();
        OutForward = OutRotation.Vector();
        return true;
    }

    return false;
}

#undef LOCTEXT_NAMESPACE