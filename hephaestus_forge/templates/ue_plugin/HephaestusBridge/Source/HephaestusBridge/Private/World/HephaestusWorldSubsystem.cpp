// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "World/HephaestusWorldSubsystem.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "GameFramework/Actor.h"
#include "UObject/Class.h"
#include "UObject/Package.h"
#include "AssetRegistry/AssetRegistryModule.h"

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

AActor* UHephaestusWorldSubsystem::SpawnActor(const FString& ClassPath, const FTransform& Transform, const FActorSpawnParameters& SpawnParams)
{
    UClass* ActorClass = ResolveClass(ClassPath);
    if (!ActorClass)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusWorldSubsystem: Failed to resolve class: %s"), *ClassPath);
        return nullptr;
    }

    UWorld* World = GetWorld();
    if (!World)
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusWorldSubsystem: No world available"));
        return nullptr;
    }

    FActorSpawnParameters Params = SpawnParams;
    Params.bNoFail = true;

    // UWorld::SpawnActor takes the transform by pointer.
    AActor* Actor = World->SpawnActor(ActorClass, &Transform, Params);
    if (Actor)
    {
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusWorldSubsystem: Spawned actor %s at %s"), *Actor->GetName(), *Transform.GetLocation().ToString());
    }

    return Actor;
}

bool UHephaestusWorldSubsystem::DestroyActor(const FString& ActorPath, bool bNetForce)
{
    AActor* Actor = FindActorByPath(ActorPath);
    if (!Actor)
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusWorldSubsystem: Actor not found: %s"), *ActorPath);
        return false;
    }

    if (Actor->IsPendingKill())
    {
        return true;
    }

    Actor->DestroyNetworkActorHandled();
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
    UWorld* World = GetWorld();
    if (!World)
    {
        return Results;
    }

    // Use world's actor iterator with bounds check
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
    UWorld* World = GetWorld();
    if (!World)
    {
        return nullptr;
    }

    // Try to find by path name
    UObject* Obj = StaticFindObject(AActor::StaticClass(), nullptr, *ActorPath);
    return Cast<AActor>(Obj);
}

TArray<AActor*> UHephaestusWorldSubsystem::GetAllActorsOfClass(TSubclassOf<AActor> ActorClass) const
{
    TArray<AActor*> Results;
    UWorld* World = GetWorld();
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

UClass* UHephaestusWorldSubsystem::ResolveClass(const FString& ClassPath) const
{
    // Try direct load
    UClass* Class = LoadClass<AActor>(nullptr, *ClassPath);
    if (Class)
    {
        return Class;
    }

    // Try finding in asset registry
    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    FAssetData AssetData = AssetRegistryModule.Get().GetAssetByObjectPath(FName(*ClassPath));
    if (AssetData.IsValid())
    {
        return Cast<UClass>(AssetData.GetAsset());
    }

    return nullptr;
}

#undef LOCTEXT_NAMESPACE