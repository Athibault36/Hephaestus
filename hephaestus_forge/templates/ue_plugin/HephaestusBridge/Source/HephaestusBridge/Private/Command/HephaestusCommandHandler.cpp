// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Command/HephaestusCommandHandler.h"
#include "HephaestusBridge.h"
#include "World/HephaestusWorldSubsystem.h"
#include "Assets/HephaestusAssetSubsystem.h"
#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "Rendering/HephaestusRenderingSubsystem.h"
#include "PCG/HephaestusPCGSubsystem.h"
#include "Animation/HephaestusAnimationSubsystem.h"
#include "Audio/HephaestusAudioSubsystem.h"
#include "Sequence/HephaestusSequenceSubsystem.h"
#include "Vision/HephaestusVisionSubsystem.h"

#include "Async/Async.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "Json.h"
#include "JsonObjectConverter.h"
#include "Misc/ScopeLock.h"
#include "HAL/PlatformTime.h"

#define LOCTEXT_NAMESPACE "HephaestusCommand"

void UHephaestusCommandHandler::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusCommandHandler: Initializing..."));

    // Get subsystem references
    UGameInstance* GameInstance = GetGameInstance();
    if (GameInstance)
    {
        WorldSubsystem = GameInstance->GetSubsystem<UHephaestusWorldSubsystem>();
        AssetSubsystem = GameInstance->GetSubsystem<UHephaestusAssetSubsystem>();
        BlueprintSubsystem = GameInstance->GetSubsystem<UHephaestusBlueprintSubsystem>();
        RenderingSubsystem = GameInstance->GetSubsystem<UHephaestusRenderingSubsystem>();
        PCGSubsystem = GameInstance->GetSubsystem<UHephaestusPCGSubsystem>();
        AnimationSubsystem = GameInstance->GetSubsystem<UHephaestusAnimationSubsystem>();
        SequenceSubsystem = GameInstance->GetSubsystem<UHephaestusSequenceSubsystem>();
        AudioSubsystem = GameInstance->GetSubsystem<UHephaestusAudioSubsystem>();
    }

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusCommandHandler: Initialized"));
}

void UHephaestusCommandHandler::Deinitialize()
{
    CustomCommands.Empty();
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusCommandHandler: Deinitialized"));
}

void UHephaestusCommandHandler::ExecuteCommandAsync(const FString& CommandJSON, TFunction<void(const FHephaestusCommandResult&)> Callback)
{
    AsyncTask(ENamedThreads::GameThread, [this, CommandJSON, Callback = MoveTemp(Callback)]()
    {
        FHephaestusCommandResult Result = ExecuteCommand_GameThread(CommandJSON);
        if (Callback)
        {
            Callback(Result);
        }
    });
}

FHephaestusCommandResult UHephaestusCommandHandler::ExecuteCommand(const FString& CommandJSON)
{
    // Ensure we're on game thread
    check(IsInGameThread());
    return ExecuteCommand_GameThread(CommandJSON);
}

FHephaestusCommandResult UHephaestusCommandHandler::ExecuteCommandForWorld(const UObject* WorldContextObject, const FString& CommandJSON)
{
    UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
    if (!World && GEngine)
    {
        for (const FWorldContext& Context : GEngine->GetWorldContexts())
        {
            if (Context.World() &&
                (Context.WorldType == EWorldType::PIE || Context.WorldType == EWorldType::Game))
            {
                World = Context.World();
                break;
            }
        }
    }
    if (!World)
    {
        FHephaestusCommandResult Error;
        Error.bSuccess = false;
        Error.ErrorMessage = TEXT("No PIE/game world (press Play first)");
        return Error;
    }

    UGameInstance* GI = World->GetGameInstance();
    if (!GI)
    {
        FHephaestusCommandResult Error;
        Error.bSuccess = false;
        Error.ErrorMessage = TEXT("No GameInstance on world");
        return Error;
    }

    UHephaestusCommandHandler* Handler = GI->GetSubsystem<UHephaestusCommandHandler>();
    if (!Handler)
    {
        FHephaestusCommandResult Error;
        Error.bSuccess = false;
        Error.ErrorMessage = TEXT("HephaestusCommandHandler not found");
        return Error;
    }

    return Handler->ExecuteCommand(CommandJSON);
}

void UHephaestusCommandHandler::ExecuteBatchAsync(const TArray<FString>& CommandsJSON, TFunction<void(const FHephaestusBatchCommandResult&)> Callback)
{
    AsyncTask(ENamedThreads::GameThread, [this, CommandsJSON, Callback = MoveTemp(Callback)]()
    {
        FHephaestusBatchCommandResult BatchResult;
        BatchResult.bOverallSuccess = true;
        BatchResult.TotalTimeMs = 0.0f;

        double StartTime = FPlatformTime::Seconds();

        for (const FString& CommandJSON : CommandsJSON)
        {
            FHephaestusCommandResult Result = ExecuteCommand_GameThread(CommandJSON);
            BatchResult.Results.Add(Result);

            if (!Result.bSuccess)
            {
                BatchResult.bOverallSuccess = false;
            }
        }

        BatchResult.TotalTimeMs = static_cast<float>((FPlatformTime::Seconds() - StartTime) * 1000.0);

        if (Callback)
        {
            Callback(BatchResult);
        }
    });
}

FHephaestusBatchCommandResult UHephaestusCommandHandler::ExecuteBatch(const TArray<FString>& CommandsJSON)
{
    check(IsInGameThread());

    FHephaestusBatchCommandResult BatchResult;
    BatchResult.bOverallSuccess = true;
    BatchResult.TotalTimeMs = 0.0f;

    double StartTime = FPlatformTime::Seconds();

    for (const FString& CommandJSON : CommandsJSON)
    {
        FHephaestusCommandResult Result = ExecuteCommand_GameThread(CommandJSON);
        BatchResult.Results.Add(Result);

        if (!Result.bSuccess)
        {
            BatchResult.bOverallSuccess = false;
        }
    }

    BatchResult.TotalTimeMs = static_cast<float>((FPlatformTime::Seconds() - StartTime) * 1000.0);
    return BatchResult;
}

bool UHephaestusCommandHandler::RegisterCustomCommand(const FString& CommandName, const FHephaestusCustomCommandDelegate& Handler)
{
    FScopeLock Lock(&CustomCommandsLock);
    if (CustomCommands.Contains(CommandName))
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusCommandHandler: Command '%s' already registered"), *CommandName);
        return false;
    }

    CustomCommands.Add(CommandName, Handler);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusCommandHandler: Registered custom command '%s'"), *CommandName);
    return true;
}

bool UHephaestusCommandHandler::UnregisterCustomCommand(const FString& CommandName)
{
    FScopeLock Lock(&CustomCommandsLock);
    bool bRemoved = CustomCommands.Remove(CommandName) > 0;
    if (bRemoved)
    {
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusCommandHandler: Unregistered custom command '%s'"), *CommandName);
    }
    return bRemoved;
}

TArray<FString> UHephaestusCommandHandler::GetAvailableCommands() const
{
    TArray<FString> Commands = {
        TEXT("world.spawn_actor"),
        TEXT("world.spawn_mesh"),
        TEXT("world.destroy_actor"),
        TEXT("world.destroy"),
        TEXT("world.list_actors"),
        TEXT("world.set_transform"),
        TEXT("world.set_light"),
        TEXT("world.get_view"),
        TEXT("world.set_view"),
        TEXT("world.get_actor"),
        TEXT("world.set_mesh_color"),
        TEXT("world.apply_move_input"),
        TEXT("world.get_pawn_state"),
        TEXT("world.batch_edit"),
        TEXT("world.query_spatial"),
        TEXT("asset.create_material"),
        TEXT("asset.import"),
        TEXT("asset.reimport"),
        TEXT("asset.export"),
        TEXT("asset.create_instance"),
        TEXT("asset.search"),
        TEXT("blueprint.compile"),
        TEXT("blueprint.add_function"),
        TEXT("blueprint.set_property"),
        TEXT("blueprint.diff"),
        TEXT("rendering.add_pass"),
        TEXT("rendering.create_shader_params"),
        TEXT("rendering.dispatch_compute"),
        TEXT("pcg.mutate_graph"),
        TEXT("pcg.set_metadata"),
        TEXT("pcg.query_spatial"),
        TEXT("animation.create_control_rig"),
        TEXT("animation.retarget"),
        TEXT("animation.edit_sequence"),
        TEXT("animation.livelink_connect"),
        TEXT("animation.spawn_skeletal_mesh"),
        TEXT("animation.spawn_character"),
        TEXT("animation.play_sequence"),
        TEXT("animation.play_locomotion"),
        TEXT("animation.play_transform_sequence"),
        TEXT("animation.play_montage"),
        TEXT("animation.stop"),
        TEXT("sequence.play"),
        TEXT("sequence.stop"),
        TEXT("sequence.create_shot"),
        TEXT("audio.create_metasound"),
        TEXT("audio.play_quartz"),
        TEXT("audio.synthesize"),
        TEXT("vision.capture_frame"),
        TEXT("vision.start_stream"),
        TEXT("vision.stop_stream"),
        TEXT("vision.inject_overlay"),
    };

    // Add custom commands
    FScopeLock Lock(&CustomCommandsLock);
    TArray<FString> CustomKeys;
    CustomCommands.GenerateKeyArray(CustomKeys);
    Commands.Append(CustomKeys);

    return Commands;
}

bool UHephaestusCommandHandler::ValidateCommand(const FString& CommandJSON, FString& OutErrorMessage) const
{
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(CommandJSON);
    if (!FJsonSerializer::Deserialize(Reader, JsonObject))
    {
        OutErrorMessage = TEXT("Invalid JSON");
        return false;
    }

    if (!JsonObject->HasField(TEXT("command")))
    {
        OutErrorMessage = TEXT("Missing 'command' field");
        return false;
    }

    FString Command = JsonObject->GetStringField(TEXT("command"));
    TArray<FString> Available = GetAvailableCommands();
    if (!Available.Contains(Command))
    {
        OutErrorMessage = FString::Printf(TEXT("Unknown command: %s"), *Command);
        return false;
    }

    return true;
}

FHephaestusCommandResult UHephaestusCommandHandler::ExecuteCommand_GameThread(const FString& CommandJSON)
{
    double StartTime = FPlatformTime::Seconds();

    // Generate command ID
    FString CommandID = FString::Printf(TEXT("cmd_%llu"), ++CommandCounter);

    // Parse JSON
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(CommandJSON);
    if (!FJsonSerializer::Deserialize(Reader, JsonObject))
    {
        FHephaestusCommandResult ErrorResult = MakeErrorResult(CommandID, TEXT("Invalid JSON"));
        ErrorResult.ExecutionTimeMs = static_cast<float>((FPlatformTime::Seconds() - StartTime) * 1000.0);
        OnCommandFailed.Broadcast(CommandID, TEXT("Invalid JSON"));
        TotalCommandsFailed++;
        return ErrorResult;
    }

    // Route command
    FHephaestusCommandResult Result = RouteCommand(JsonObject);
    Result.CommandID = CommandID;
    Result.ExecutionTimeMs = static_cast<float>((FPlatformTime::Seconds() - StartTime) * 1000.0);

    // Update stats
    TotalCommandsExecuted++;
    TotalExecutionTimeMs += Result.ExecutionTimeMs;
    if (!Result.bSuccess)
    {
        TotalCommandsFailed++;
        OnCommandFailed.Broadcast(CommandID, Result.ErrorMessage);
    }
    else
    {
        OnCommandExecuted.Broadcast(Result);
    }

    return Result;
}

FHephaestusCommandResult UHephaestusCommandHandler::RouteCommand(const TSharedPtr<FJsonObject>& CommandObject)
{
    FString Command = CommandObject->GetStringField(TEXT("command"));
    // Prefer "params"; fall back to "args". Do NOT use GetObjectField — missing keys
    // return a valid empty object, which would swallow the args alias.
    TSharedPtr<FJsonObject> Params;
    const TSharedPtr<FJsonObject>* ParamsObj = nullptr;
    if (CommandObject->TryGetObjectField(TEXT("params"), ParamsObj) && ParamsObj && ParamsObj->IsValid())
    {
        Params = *ParamsObj;
    }
    else if (CommandObject->TryGetObjectField(TEXT("args"), ParamsObj) && ParamsObj && ParamsObj->IsValid())
    {
        Params = *ParamsObj;
    }

    // Check custom commands first
    {
        FScopeLock Lock(&CustomCommandsLock);
        if (CustomCommands.Contains(Command))
        {
            FHephaestusCommandResult Result;
            bool bSuccess = CustomCommands[Command].Execute(CommandObject->GetStringField(TEXT("command")), Result);
            return bSuccess ? Result : MakeErrorResult(TEXT(""), TEXT("Custom command handler failed"));
        }
    }

    // Route to subsystem handlers
    if (Command.StartsWith(TEXT("world.")))
    {
        return HandleWorldCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("asset.")))
    {
        return HandleAssetCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("blueprint.")))
    {
        return HandleBlueprintCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("rendering.")))
    {
        return HandleRenderingCommand(Params);
    }
    else if (Command.StartsWith(TEXT("pcg.")))
    {
        return HandlePCGCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("animation.")))
    {
        return HandleAnimationCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("sequence.")))
    {
        return HandleSequenceCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("audio.")))
    {
        return HandleAudioCommand(Command, Params);
    }
    else if (Command.StartsWith(TEXT("vision.")))
    {
        return HandleVisionCommand(Command, Params);
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown command category: %s"), *Command));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleWorldCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!WorldSubsystem)
    {
        if (UGameInstance* GI = GetGameInstance())
        {
            WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
        }
    }
    if (!WorldSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("World subsystem not available (start PIE)"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        // world.spawn_actor -> spawn_actor
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("spawn_actor"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.spawn_actor"));
        }

        FString ClassPath;
        if (!Params->TryGetStringField(TEXT("class_path"), ClassPath) || ClassPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("class"), ClassPath);
        }
        if (ClassPath.IsEmpty())
        {
            ClassPath = TEXT("/Script/Engine.PointLight");
        }

        FTransform Transform = FTransform::Identity;
        if (!ParseTransformParams(Params, Transform))
        {
            return MakeErrorResult(TEXT(""), TEXT("Invalid transform"));
        }
        // Identity / missing transform → spawn in front of the player camera
        if (Transform.Equals(FTransform::Identity) || Transform.GetLocation().IsNearlyZero())
        {
            FVector Loc, Forward;
            FRotator Rot;
            if (WorldSubsystem->GetView(Loc, Rot, Forward))
            {
                Transform.SetLocation(Loc + Forward * 400.f + FVector(0.f, 0.f, 80.f));
                Transform.SetRotation(Rot.Quaternion());
            }
        }

        AActor* Actor = WorldSubsystem->SpawnActor(ClassPath, Transform);
        if (Actor)
        {
            TArray<FString> Actors = { Actor->GetPathName() };
            FString ResultJSON = FString::Printf(
                TEXT("{\"actor_path\":\"%s\",\"class\":\"%s\"}"),
                *Actor->GetPathName(),
                *ClassPath);
            return MakeSuccessResult(TEXT(""), ResultJSON, {}, Actors);
        }
        return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Failed to spawn actor: %s"), *ClassPath));
    }
    else if (Action == TEXT("spawn_mesh"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.spawn_mesh"));
        }

        FString MeshPath;
        if (!Params->TryGetStringField(TEXT("mesh_path"), MeshPath) || MeshPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("mesh"), MeshPath);
        }

        FTransform Transform = FTransform::Identity;
        if (!ParseTransformParams(Params, Transform))
        {
            return MakeErrorResult(TEXT(""), TEXT("Invalid transform"));
        }
        if (Transform.Equals(FTransform::Identity) || Transform.GetLocation().IsNearlyZero())
        {
            FVector Loc, Forward;
            FRotator Rot;
            if (WorldSubsystem->GetView(Loc, Rot, Forward))
            {
                Transform.SetLocation(Loc + Forward * 400.f + FVector(0.f, 0.f, 50.f));
                Transform.SetScale3D(FVector(2.f));
            }
            else
            {
                Transform.SetLocation(FVector(0.f, 0.f, 100.f));
                Transform.SetScale3D(FVector(2.f));
            }
        }

        AActor* Actor = WorldSubsystem->SpawnStaticMeshActor(MeshPath, Transform);
        if (Actor)
        {
            TArray<FString> Actors = { Actor->GetPathName() };
            const FString ResolvedMesh = MeshPath.IsEmpty() ? TEXT("/Engine/BasicShapes/Cube.Cube") : MeshPath;
            FString ResultJSON = FString::Printf(
                TEXT("{\"actor_path\":\"%s\",\"mesh_path\":\"%s\"}"),
                *Actor->GetPathName(),
                *ResolvedMesh);
            return MakeSuccessResult(TEXT(""), ResultJSON, {}, Actors);
        }
        return MakeErrorResult(TEXT(""), TEXT("Failed to spawn static mesh actor"));
    }
    else if (Action == TEXT("destroy_actor") || Action == TEXT("destroy"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.destroy_actor"));
        }
        FString ActorPath;
        if (!Params->TryGetStringField(TEXT("actor_path"), ActorPath) || ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        const bool bSuccess = WorldSubsystem->DestroyActor(ActorPath);
        return bSuccess
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"destroyed\":\"%s\"}"), *ActorPath), {}, { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to destroy actor"));
    }
    else if (Action == TEXT("set_transform"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.set_transform"));
        }
        FString ActorPath;
        if (!Params->TryGetStringField(TEXT("actor_path"), ActorPath) || ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        FTransform Transform = FTransform::Identity;
        if (!ParseTransformParams(Params, Transform))
        {
            return MakeErrorResult(TEXT(""), TEXT("Invalid transform"));
        }
        const bool bOk = WorldSubsystem->SetActorTransform(ActorPath, Transform);
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"actor_path\":\"%s\"}"), *ActorPath), {}, { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to set transform"));
    }
    else if (Action == TEXT("set_light"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.set_light"));
        }
        FString ActorPath;
        if (!Params->TryGetStringField(TEXT("actor_path"), ActorPath) || ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        double Intensity = 5000.0;
        Params->TryGetNumberField(TEXT("intensity"), Intensity);
        double Radius = 1000.0;
        Params->TryGetNumberField(TEXT("attenuation_radius"), Radius);
        FLinearColor Color = FLinearColor::White;
        const TSharedPtr<FJsonObject>* ColorObj = nullptr;
        if (Params->TryGetObjectField(TEXT("color"), ColorObj) && ColorObj && ColorObj->IsValid())
        {
            double R = 1, G = 1, B = 1, A = 1;
            (*ColorObj)->TryGetNumberField(TEXT("r"), R);
            (*ColorObj)->TryGetNumberField(TEXT("g"), G);
            (*ColorObj)->TryGetNumberField(TEXT("b"), B);
            (*ColorObj)->TryGetNumberField(TEXT("a"), A);
            Color = FLinearColor(static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
        }
        else
        {
            const TArray<TSharedPtr<FJsonValue>>* ColorArr = nullptr;
            if (Params->TryGetArrayField(TEXT("color"), ColorArr) && ColorArr && ColorArr->Num() >= 3)
            {
                Color = FLinearColor(
                    static_cast<float>((*ColorArr)[0]->AsNumber()),
                    static_cast<float>((*ColorArr)[1]->AsNumber()),
                    static_cast<float>((*ColorArr)[2]->AsNumber()),
                    ColorArr->Num() >= 4 ? static_cast<float>((*ColorArr)[3]->AsNumber()) : 1.f);
            }
        }
        const bool bOk = WorldSubsystem->SetPointLightProperties(
            ActorPath, static_cast<float>(Intensity), Color, static_cast<float>(Radius));
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"actor_path\":\"%s\",\"intensity\":%.1f}"), *ActorPath, Intensity), {}, { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to set light (actor not a PointLight?)"));
    }
    else if (Action == TEXT("get_view"))
    {
        FVector Loc, Forward;
        FRotator Rot;
        if (!WorldSubsystem->GetView(Loc, Rot, Forward))
        {
            return MakeErrorResult(TEXT(""), TEXT("No player view (is PIE running?)"));
        }
        const FString ResultJSON = FString::Printf(
            TEXT("{\"location\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},\"rotation\":{\"pitch\":%.3f,\"yaw\":%.3f,\"roll\":%.3f},\"forward\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}}"),
            Loc.X, Loc.Y, Loc.Z, Rot.Pitch, Rot.Yaw, Rot.Roll, Forward.X, Forward.Y, Forward.Z);
        return MakeSuccessResult(TEXT(""), ResultJSON);
    }
    else if (Action == TEXT("set_view"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.set_view"));
        }
        FVector Loc = FVector::ZeroVector;
        FRotator Rot = FRotator::ZeroRotator;
        FTransform Transform = FTransform::Identity;
        if (ParseTransformParams(Params, Transform))
        {
            Loc = Transform.GetLocation();
            Rot = Transform.Rotator();
        }
        else
        {
            ParseVectorField(Params, TEXT("location"), Loc);
            ParseRotatorField(Params, TEXT("rotation"), Rot);
        }
        if (!WorldSubsystem->SetView(Loc, Rot))
        {
            return MakeErrorResult(TEXT(""), TEXT("Failed to set view (is PIE running?)"));
        }
        const FString ResultJSON = FString::Printf(
            TEXT("{\"location\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},\"rotation\":{\"pitch\":%.3f,\"yaw\":%.3f,\"roll\":%.3f}}"),
            Loc.X, Loc.Y, Loc.Z, Rot.Pitch, Rot.Yaw, Rot.Roll);
        return MakeSuccessResult(TEXT(""), ResultJSON);
    }
    else if (Action == TEXT("get_actor"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.get_actor"));
        }
        FString ActorPath;
        if (!Params->TryGetStringField(TEXT("actor_path"), ActorPath) || ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        FString ResultJSON;
        if (!WorldSubsystem->DescribeActor(ActorPath, ResultJSON))
        {
            return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Actor not found: %s"), *ActorPath));
        }
        return MakeSuccessResult(TEXT(""), ResultJSON, {}, { ActorPath });
    }
    else if (Action == TEXT("set_mesh_color"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.set_mesh_color"));
        }
        FString ActorPath;
        if (!Params->TryGetStringField(TEXT("actor_path"), ActorPath) || ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        FLinearColor Color = FLinearColor::White;
        const TSharedPtr<FJsonObject>* ColorObj = nullptr;
        if (Params->TryGetObjectField(TEXT("color"), ColorObj) && ColorObj && ColorObj->IsValid())
        {
            double R = 1, G = 1, B = 1, A = 1;
            (*ColorObj)->TryGetNumberField(TEXT("r"), R);
            (*ColorObj)->TryGetNumberField(TEXT("g"), G);
            (*ColorObj)->TryGetNumberField(TEXT("b"), B);
            (*ColorObj)->TryGetNumberField(TEXT("a"), A);
            Color = FLinearColor(static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
        }
        const bool bOk = WorldSubsystem->SetStaticMeshColor(ActorPath, Color);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"actor_path\":\"%s\",\"color\":{\"r\":%.3f,\"g\":%.3f,\"b\":%.3f}}"),
                      *ActorPath, Color.R, Color.G, Color.B),
                  {},
                  { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to set mesh color (need StaticMeshActor path)"));
    }
    else if (Action == TEXT("apply_move_input") || Action == TEXT("move_input"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.apply_move_input"));
        }
        double Forward = 1.0;
        double Right = 0.0;
        double Duration = 2.0;
        Params->TryGetNumberField(TEXT("forward"), Forward);
        Params->TryGetNumberField(TEXT("right"), Right);
        Params->TryGetNumberField(TEXT("duration"), Duration);
        if (!WorldSubsystem->ApplyMoveInput(static_cast<float>(Forward), static_cast<float>(Right), static_cast<float>(Duration)))
        {
            return MakeErrorResult(TEXT(""), TEXT("Failed to apply move input (no possessed pawn?)"));
        }
        return MakeSuccessResult(
            TEXT(""),
            FString::Printf(TEXT("{\"forward\":%.2f,\"right\":%.2f,\"duration\":%.2f}"), Forward, Right, Duration));
    }
    else if (Action == TEXT("get_pawn_state"))
    {
        FString ResultJSON;
        if (!WorldSubsystem->GetPawnStateJson(ResultJSON))
        {
            return MakeErrorResult(TEXT(""), TEXT("No possessed pawn (is PIE running?)"));
        }
        return MakeSuccessResult(TEXT(""), ResultJSON);
    }
    else if (Action == TEXT("list_actors"))
    {
        FString ClassFilter;
        bool bIncludeDetails = false;
        int32 DetailLimit = 12;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("class_path"), ClassFilter);
            Params->TryGetBoolField(TEXT("include_details"), bIncludeDetails);
            double LimitNum = 12.0;
            if (Params->TryGetNumberField(TEXT("detail_limit"), LimitNum))
            {
                DetailLimit = FMath::Clamp(static_cast<int32>(LimitNum), 1, 40);
            }
        }
        TArray<FString> Paths = WorldSubsystem->ListActors(ClassFilter);
        TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
        TArray<TSharedPtr<FJsonValue>> Arr;
        for (const FString& Path : Paths)
        {
            Arr.Add(MakeShared<FJsonValueString>(Path));
        }
        ResultObj->SetArrayField(TEXT("actors"), Arr);
        ResultObj->SetNumberField(TEXT("count"), Paths.Num());
        if (bIncludeDetails)
        {
            TArray<TSharedPtr<FJsonValue>> DetailArr;
            int32 Added = 0;
            for (const FString& Path : Paths)
            {
                if (Added >= DetailLimit)
                {
                    break;
                }
                FString DetailJson;
                if (WorldSubsystem->DescribeActor(Path, DetailJson) && !DetailJson.IsEmpty())
                {
                    TSharedPtr<FJsonObject> DetailObj;
                    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(DetailJson);
                    if (FJsonSerializer::Deserialize(Reader, DetailObj) && DetailObj.IsValid())
                    {
                        DetailArr.Add(MakeShared<FJsonValueObject>(DetailObj));
                        ++Added;
                    }
                }
            }
            ResultObj->SetArrayField(TEXT("actor_details"), DetailArr);
        }
        FString ResultJSON;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultJSON);
        FJsonSerializer::Serialize(ResultObj, Writer);
        return MakeSuccessResult(TEXT(""), ResultJSON, {}, Paths);
    }
    else if (Action == TEXT("batch_edit"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for world.batch_edit"));
        }

        TArray<FString> ActorPaths;
        const TArray<TSharedPtr<FJsonValue>>* ActorsArr = nullptr;
        if (Params->TryGetArrayField(TEXT("actor_paths"), ActorsArr) && ActorsArr)
        {
            for (const TSharedPtr<FJsonValue>& Val : *ActorsArr)
            {
                ActorPaths.Add(Val->AsString());
            }
        }

        TMap<FString, FString> PropertyEdits;
        const TSharedPtr<FJsonObject>* EditsObj = nullptr;
        if (Params->TryGetObjectField(TEXT("property_edits"), EditsObj) && EditsObj && EditsObj->IsValid())
        {
            for (const auto& Pair : (*EditsObj)->Values)
            {
                PropertyEdits.Add(FString(Pair.Key), Pair.Value->AsString());
            }
        }

        const int32 Edited = WorldSubsystem->BatchEditActors(ActorPaths, PropertyEdits);
        FString ResultJSON = FString::Printf(TEXT("{\"edited\":%d}"), Edited);
        return MakeSuccessResult(TEXT(""), ResultJSON, {}, ActorPaths);
    }
    else if (Action == TEXT("query_spatial"))
    {
        if (!Params.IsValid() || !Params->HasField(TEXT("bounds")))
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing bounds for world.query_spatial"));
        }

        const TSharedPtr<FJsonObject> BoundsObj = Params->GetObjectField(TEXT("bounds"));
        FVector MinV(0), MaxV(0);
        if (BoundsObj->HasField(TEXT("min")))
        {
            ParseVector(BoundsObj->GetObjectField(TEXT("min")), MinV);
        }
        if (BoundsObj->HasField(TEXT("max")))
        {
            ParseVector(BoundsObj->GetObjectField(TEXT("max")), MaxV);
        }

        FString FilterClassPath;
        Params->TryGetStringField(TEXT("filter_class"), FilterClassPath);
        TSubclassOf<AActor> FilterClass = nullptr;
        if (!FilterClassPath.IsEmpty())
        {
            FilterClass = LoadClass<AActor>(nullptr, *FilterClassPath);
            if (!FilterClass && !FilterClassPath.Contains(TEXT("/")))
            {
                FilterClass = LoadClass<AActor>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *FilterClassPath));
            }
        }

        TArray<AActor*> Found = WorldSubsystem->QuerySpatial(FBox(MinV, MaxV), FilterClass);
        TArray<FString> Paths;
        TArray<TSharedPtr<FJsonValue>> Arr;
        for (AActor* Actor : Found)
        {
            if (Actor)
            {
                Paths.Add(Actor->GetPathName());
                Arr.Add(MakeShared<FJsonValueString>(Actor->GetPathName()));
            }
        }
        TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
        ResultObj->SetArrayField(TEXT("actors"), Arr);
        ResultObj->SetNumberField(TEXT("count"), Paths.Num());
        FString ResultJSON;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultJSON);
        FJsonSerializer::Serialize(ResultObj, Writer);
        return MakeSuccessResult(TEXT(""), ResultJSON, {}, Paths);
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown world action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAssetCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!AssetSubsystem)
    {
        if (UGameInstance* GI = GetGameInstance())
        {
            AssetSubsystem = GI->GetSubsystem<UHephaestusAssetSubsystem>();
        }
    }
    if (!AssetSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Asset subsystem not available (start PIE)"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("search"))
    {
        FString Query;
        FString AssetClass;
        int32 Limit = 12;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("query"), Query);
            Params->TryGetStringField(TEXT("class"), AssetClass);
            double LimitNum = 12.0;
            if (Params->TryGetNumberField(TEXT("limit"), LimitNum))
            {
                Limit = static_cast<int32>(LimitNum);
            }
        }
        FString ResultJSON;
        if (!AssetSubsystem->SearchAssetsJson(Query, AssetClass, Limit, ResultJSON))
        {
            return MakeErrorResult(TEXT(""), TEXT("asset.search requires non-empty query"));
        }
        return MakeSuccessResult(TEXT(""), ResultJSON);
    }
    else if (Action == TEXT("create_material"))
    {
        FHephaestusMaterialDesc Desc;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("name"), Desc.Name);
            Params->TryGetStringField(TEXT("base_material_path"), Desc.BaseMaterialPath);
            const TSharedPtr<FJsonObject>* ParamsObj = nullptr;
            if (Params->TryGetObjectField(TEXT("parameters"), ParamsObj) && ParamsObj && ParamsObj->IsValid())
            {
                for (const auto& Pair : (*ParamsObj)->Values)
                {
                    FString Val;
                    if (Pair.Value->TryGetString(Val))
                    {
                        Desc.Parameters.Add(Pair.Key, Val);
                    }
                }
            }
        }
        if (Desc.Name.IsEmpty())
        {
            Desc.Name = TEXT("HephaestusMaterial");
        }
        UMaterial* Material = AssetSubsystem->CreateMaterial(Desc);
        return Material
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(
                      TEXT("{\"material_path\":\"%s\",\"base\":\"%s\"}"),
                      *Desc.Name,
                      *Material->GetPathName()))
            : MakeErrorResult(TEXT(""), TEXT("create_material failed"));
    }
    else if (Action == TEXT("import"))
    {
        // Params: file_path, destination_path, import_options
        return MakeSuccessResult(TEXT(""), TEXT("{\"asset_path\":\"\"}"));
    }
    else if (Action == TEXT("reimport"))
    {
        // Params: asset_path
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("export"))
    {
        FString AssetPath;
        FString FilePath;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("asset_path"), AssetPath);
            Params->TryGetStringField(TEXT("file_path"), FilePath);
        }
        UObject* Asset = AssetSubsystem->FindAsset(AssetPath);
        if (!Asset)
        {
            return MakeErrorResult(TEXT(""), TEXT("export: asset_path not found"));
        }
        const bool bOk = AssetSubsystem->ExportAsset(Asset, FilePath, TEXT(""));
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"asset_path\":\"%s\",\"validated\":true}"), *AssetPath))
            : MakeErrorResult(TEXT(""), TEXT("export failed"));
    }
    else if (Action == TEXT("create_instance"))
    {
        // Params: parent_material, parameters
        return MakeSuccessResult(TEXT(""), TEXT("{\"instance_path\":\"\"}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown asset action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleBlueprintCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!BlueprintSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Blueprint subsystem not available"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("compile"))
    {
        FString BlueprintPath;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
            if (BlueprintPath.IsEmpty())
            {
                Params->TryGetStringField(TEXT("path"), BlueprintPath);
            }
        }
        UBlueprint* Blueprint = BlueprintPath.IsEmpty()
            ? nullptr
            : LoadObject<UBlueprint>(nullptr, *BlueprintPath);
        const bool bOk = BlueprintSubsystem->CompileBlueprint(Blueprint);
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"compiled\":true,\"path\":\"%s\"}"), *BlueprintPath))
            : MakeErrorResult(TEXT(""), TEXT("Blueprint compile failed — check blueprint_path and editor build"));
    }
    else if (Action == TEXT("add_function"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("set_property"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("diff"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{\"diff\":\"\"}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown blueprint action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleRenderingCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!RenderingSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Rendering subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("add_pass"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("create_shader_params"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("dispatch_compute"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown rendering action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandlePCGCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!PCGSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("PCG subsystem not available"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("mutate_graph"))
    {
        FString GraphPath;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("graph_path"), GraphPath);
            if (GraphPath.IsEmpty())
            {
                Params->TryGetStringField(TEXT("path"), GraphPath);
            }
        }
        UObject* Graph = GraphPath.IsEmpty() ? nullptr : LoadObject<UObject>(nullptr, *GraphPath);
        TArray<FHephaestusPCGMutation> Mutations;
        const bool bOk = PCGSubsystem->MutatePCGGraph(Graph, Mutations);
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"graph_path\":\"%s\",\"mutations\":0}"), *GraphPath))
            : MakeErrorResult(TEXT(""), TEXT("mutate_graph failed — provide graph_path to an existing PCG graph asset"));
    }
    else if (Action == TEXT("set_metadata"))
    {
        TMap<FString, FString> Meta;
        PCGSubsystem->SetMetadataParams(nullptr, Meta);
        return MakeSuccessResult(TEXT(""), TEXT("{\"metadata\":true}"));
    }
    else if (Action == TEXT("query_spatial"))
    {
        FHephaestusPCGSpatialQuery Query;
        if (Params.IsValid())
        {
            FVector MinV, MaxV;
            ParseVectorField(Params, TEXT("min"), MinV);
            ParseVectorField(Params, TEXT("max"), MaxV);
            if (!MinV.IsNearlyZero() || !MaxV.IsNearlyZero())
            {
                Query.Bounds = FBox(MinV, MaxV);
            }
        }
        const FHephaestusPCGSpatialDataResult Result = PCGSubsystem->QuerySpatialData(Query);
        return MakeSuccessResult(
            TEXT(""),
            FString::Printf(TEXT("{\"points\":%d}"), Result.Points.Num()));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown PCG action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAnimationCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!AnimationSubsystem)
    {
        if (UGameInstance* GI = GetGameInstance())
        {
            AnimationSubsystem = GI->GetSubsystem<UHephaestusAnimationSubsystem>();
        }
    }
    if (!AnimationSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Animation subsystem not available (start PIE)"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("create_control_rig"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.create_control_rig"));
        }
        FString RigPath;
        FString MeshPath;
        Params->TryGetStringField(TEXT("rig_path"), RigPath);
        Params->TryGetStringField(TEXT("mesh_path"), MeshPath);
        USkeletalMesh* Mesh = MeshPath.IsEmpty() ? nullptr : LoadObject<USkeletalMesh>(nullptr, *MeshPath);
        FHephaestusControlRigDesc Desc;
        Desc.Name = RigPath;
        Desc.SkeletalMesh = Mesh;
        UObject* Rig = AnimationSubsystem->CreateControlRig(Mesh, Desc);
        return Rig
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"rig_path\":\"%s\"}"), *RigPath))
            : MakeErrorResult(TEXT(""), TEXT("create_control_rig failed — provide rig_path to an existing asset"));
    }
    else if (Action == TEXT("retarget"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{\"stub\":true}"));
    }
    else if (Action == TEXT("edit_sequence"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.edit_sequence"));
        }
        FString ActorPath;
        FString AnimPath;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        if (ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        Params->TryGetStringField(TEXT("anim_path"), AnimPath);
        if (AnimPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("animation"), AnimPath);
        }
        double Duration = 3.0;
        Params->TryGetNumberField(TEXT("duration"), Duration);
        if (!ActorPath.IsEmpty() && !AnimPath.IsEmpty())
        {
            const bool bOk = AnimationSubsystem->PlayAnimSequence(ActorPath, AnimPath, false);
            return bOk
                ? MakeSuccessResult(
                      TEXT(""),
                      FString::Printf(TEXT("{\"actor_path\":\"%s\",\"anim_path\":\"%s\",\"mode\":\"play_anim\"}"),
                          *ActorPath, *AnimPath),
                      {},
                      { ActorPath })
                : MakeErrorResult(TEXT(""), TEXT("edit_sequence: failed to play animation"));
        }
        FVector TargetLocation = FVector::ZeroVector;
        ParseVectorField(Params, TEXT("target_location"), TargetLocation);
        if (!ActorPath.IsEmpty() && !TargetLocation.IsNearlyZero())
        {
            const bool bOk = AnimationSubsystem->PlayTransformSequence(
                ActorPath, TargetLocation, static_cast<float>(Duration));
            return bOk
                ? MakeSuccessResult(
                      TEXT(""),
                      FString::Printf(TEXT("{\"actor_path\":\"%s\",\"mode\":\"transform_sequence\",\"duration\":%.2f}"),
                          *ActorPath, Duration),
                      {},
                      { ActorPath })
                : MakeErrorResult(TEXT(""), TEXT("edit_sequence: failed to play transform sequence"));
        }
        return MakeErrorResult(TEXT(""), TEXT("edit_sequence requires actor_path + anim_path OR target_location"));
    }
    else if (Action == TEXT("livelink_connect"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.livelink_connect"));
        }
        FString Subject;
        FString Config;
        Params->TryGetStringField(TEXT("subject"), Subject);
        if (Subject.IsEmpty())
        {
            Params->TryGetStringField(TEXT("subject_name"), Subject);
        }
        Params->TryGetStringField(TEXT("config"), Config);
        const bool bOk = AnimationSubsystem->LiveLinkConnect(Subject, Config);
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"subject\":\"%s\",\"connected\":true}"), *Subject))
            : MakeErrorResult(TEXT(""), TEXT("livelink_connect requires subject"));
    }
    else if (Action == TEXT("spawn_skeletal_mesh"))
    {
        if (!WorldSubsystem)
        {
            if (UGameInstance* GI = GetGameInstance())
            {
                WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
            }
        }
        FString MeshPath;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("mesh_path"), MeshPath);
            if (MeshPath.IsEmpty())
            {
                Params->TryGetStringField(TEXT("mesh"), MeshPath);
            }
        }
        FTransform Transform = FTransform::Identity;
        if (Params.IsValid())
        {
            ParseTransformParams(Params, Transform);
        }
        if (Transform.Equals(FTransform::Identity) && WorldSubsystem)
        {
            FVector Loc, Forward;
            FRotator Rot;
            if (WorldSubsystem->GetView(Loc, Rot, Forward))
            {
                const FVector SpawnLoc = Loc + Forward * 400.f;
                Transform.SetLocation(SpawnLoc);
                Transform.SetRotation(Rot.Quaternion());
            }
        }
        FString AnimBP;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("anim_blueprint_path"), AnimBP);
            if (AnimBP.IsEmpty())
            {
                Params->TryGetStringField(TEXT("anim_bp_path"), AnimBP);
            }
        }
        AActor* Actor = AnimationSubsystem->SpawnSkeletalMeshActor(MeshPath, Transform, AnimBP);
        if (!Actor)
        {
            return MakeErrorResult(TEXT(""), TEXT("Failed to spawn skeletal mesh actor"));
        }
        const FString ActorPath = Actor->GetPathName();
        return MakeSuccessResult(
            TEXT(""),
            FString::Printf(TEXT("{\"actor_path\":\"%s\"}"), *ActorPath),
            {},
            { ActorPath });
    }
    else if (Action == TEXT("spawn_character") || Action == TEXT("spawn_locomotion_character"))
    {
        if (!WorldSubsystem)
        {
            if (UGameInstance* GI = GetGameInstance())
            {
                WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
            }
        }
        FString MeshPath;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("mesh_path"), MeshPath);
            if (MeshPath.IsEmpty())
            {
                Params->TryGetStringField(TEXT("mesh"), MeshPath);
            }
        }
        FTransform Transform = FTransform::Identity;
        if (Params.IsValid())
        {
            ParseTransformParams(Params, Transform);
        }
        if (Transform.Equals(FTransform::Identity) && WorldSubsystem)
        {
            FVector Loc, Forward;
            FRotator Rot;
            if (WorldSubsystem->GetView(Loc, Rot, Forward))
            {
                const FVector SpawnLoc = Loc + Forward * 400.f;
                Transform.SetLocation(SpawnLoc);
                Transform.SetRotation(Rot.Quaternion());
            }
        }
        FString AnimBP;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("anim_blueprint_path"), AnimBP);
            if (AnimBP.IsEmpty())
            {
                Params->TryGetStringField(TEXT("anim_bp_path"), AnimBP);
            }
        }
        AActor* Actor = AnimationSubsystem->SpawnLocomotionCharacter(MeshPath, Transform, AnimBP);
        if (!Actor)
        {
            return MakeErrorResult(TEXT(""), TEXT("Failed to spawn locomotion character"));
        }
        const FString ActorPath = Actor->GetPathName();
        return MakeSuccessResult(
            TEXT(""),
            FString::Printf(TEXT("{\"actor_path\":\"%s\",\"class\":\"Character\"}"), *ActorPath),
            {},
            { ActorPath });
    }
    else if (Action == TEXT("play_sequence") || Action == TEXT("play_anim"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.play_sequence"));
        }
        FString ActorPath;
        FString AnimPath;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        if (ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        Params->TryGetStringField(TEXT("anim_path"), AnimPath);
        if (AnimPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("animation"), AnimPath);
        }
        bool bLoop = true;
        Params->TryGetBoolField(TEXT("loop"), bLoop);
        if (ActorPath.IsEmpty() || AnimPath.IsEmpty())
        {
            return MakeErrorResult(TEXT(""), TEXT("actor_path and anim_path required"));
        }
        const bool bOk = AnimationSubsystem->PlayAnimSequence(ActorPath, AnimPath, bLoop);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"actor_path\":\"%s\",\"anim_path\":\"%s\",\"loop\":%s}"),
                      *ActorPath, *AnimPath, bLoop ? TEXT("true") : TEXT("false")),
                  {},
                  { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to play animation (check skeletal mesh + anim paths)"));
    }
    else if (Action == TEXT("play_locomotion") || Action == TEXT("locomotion"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.play_locomotion"));
        }
        FString ActorPath;
        FString Mode = TEXT("idle");
        bool bLoop = true;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        if (ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        Params->TryGetStringField(TEXT("mode"), Mode);
        if (Mode.IsEmpty())
        {
            Params->TryGetStringField(TEXT("locomotion"), Mode);
        }
        Params->TryGetBoolField(TEXT("loop"), bLoop);
        if (ActorPath.IsEmpty())
        {
            return MakeErrorResult(TEXT(""), TEXT("actor_path required"));
        }
        const bool bOk = AnimationSubsystem->PlayLocomotionFallback(ActorPath, Mode, bLoop);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"actor_path\":\"%s\",\"mode\":\"%s\",\"loop\":%s}"),
                      *ActorPath, *Mode, bLoop ? TEXT("true") : TEXT("false")),
                  {},
                  { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to play locomotion fallback (no mannequin anims loaded)"));
    }
    else if (Action == TEXT("play_transform_sequence") || Action == TEXT("move_actor"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.play_transform_sequence"));
        }
        FString ActorPath;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        if (ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        FVector TargetLocation = FVector::ZeroVector;
        ParseVectorField(Params, TEXT("target_location"), TargetLocation);
        if (TargetLocation.IsNearlyZero())
        {
            double Tx = 0, Ty = 0, Tz = 0;
            Params->TryGetNumberField(TEXT("x"), Tx);
            Params->TryGetNumberField(TEXT("y"), Ty);
            Params->TryGetNumberField(TEXT("z"), Tz);
            TargetLocation = FVector(Tx, Ty, Tz);
        }
        double Duration = 3.0;
        Params->TryGetNumberField(TEXT("duration"), Duration);
        if (ActorPath.IsEmpty() || TargetLocation.IsNearlyZero())
        {
            return MakeErrorResult(TEXT(""), TEXT("actor_path and target location required"));
        }
        const bool bOk = AnimationSubsystem->PlayTransformSequence(
            ActorPath, TargetLocation, static_cast<float>(Duration));
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"actor_path\":\"%s\",\"duration\":%.2f}"), *ActorPath, Duration),
                  {},
                  { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to play transform sequence"));
    }
    else if (Action == TEXT("play_montage") || Action == TEXT("montage"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.play_montage"));
        }
        FString ActorPath;
        FString MontagePath;
        bool bLoop = false;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        Params->TryGetStringField(TEXT("montage_path"), MontagePath);
        Params->TryGetBoolField(TEXT("loop"), bLoop);
        if (ActorPath.IsEmpty() || MontagePath.IsEmpty())
        {
            return MakeErrorResult(TEXT(""), TEXT("actor_path and montage_path required"));
        }
        const bool bOk = AnimationSubsystem->PlayMontage(ActorPath, MontagePath, bLoop);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"actor_path\":\"%s\",\"montage_path\":\"%s\"}"), *ActorPath, *MontagePath),
                  {},
                  { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to play montage"));
    }
    else if (Action == TEXT("stop") || Action == TEXT("stop_animation"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for animation.stop"));
        }
        FString ActorPath;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        if (ActorPath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("actor"), ActorPath);
        }
        if (ActorPath.IsEmpty())
        {
            return MakeErrorResult(TEXT(""), TEXT("actor_path required"));
        }
        const bool bOk = AnimationSubsystem->StopAnimation(ActorPath);
        return bOk
            ? MakeSuccessResult(TEXT(""), FString::Printf(TEXT("{\"actor_path\":\"%s\",\"stopped\":true}"), *ActorPath), {}, { ActorPath })
            : MakeErrorResult(TEXT(""), TEXT("Failed to stop animation"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown animation action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleSequenceCommand(
    const FString& Command,
    const TSharedPtr<FJsonObject>& Params)
{
    if (!SequenceSubsystem)
    {
        if (UGameInstance* GI = GetGameInstance())
        {
            SequenceSubsystem = GI->GetSubsystem<UHephaestusSequenceSubsystem>();
        }
    }
    if (!SequenceSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Sequence subsystem not available (start PIE)"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("play"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for sequence.play"));
        }
        FString SequencePath;
        Params->TryGetStringField(TEXT("sequence_path"), SequencePath);
        if (SequencePath.IsEmpty())
        {
            Params->TryGetStringField(TEXT("path"), SequencePath);
        }
        bool bLoop = false;
        Params->TryGetBoolField(TEXT("loop"), bLoop);
        if (SequencePath.IsEmpty())
        {
            return MakeErrorResult(TEXT(""), TEXT("sequence_path required"));
        }
        const bool bOk = SequenceSubsystem->PlayLevelSequence(SequencePath, bLoop);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(TEXT("{\"sequence_path\":\"%s\",\"playing\":true}"), *SequencePath))
            : MakeErrorResult(TEXT(""), TEXT("Failed to play level sequence (check asset path)"));
    }

    if (Action == TEXT("stop"))
    {
        const bool bOk = SequenceSubsystem->StopLevelSequence();
        return bOk
            ? MakeSuccessResult(TEXT(""), TEXT("{\"stopped\":true}"))
            : MakeSuccessResult(TEXT(""), TEXT("{\"stopped\":false}"));
    }

    if (Action == TEXT("create_shot") || Action == TEXT("create"))
    {
        if (!Params.IsValid())
        {
            return MakeErrorResult(TEXT(""), TEXT("Missing params for sequence.create_shot"));
        }
        FVector TargetLocation = FVector::ZeroVector;
        FRotator TargetRotation = FRotator::ZeroRotator;
        ParseVectorField(Params, TEXT("location"), TargetLocation);
        ParseRotatorField(Params, TEXT("rotation"), TargetRotation);
        if (TargetLocation.IsNearlyZero())
        {
            double Tx = 0, Ty = 0, Tz = 0;
            Params->TryGetNumberField(TEXT("x"), Tx);
            Params->TryGetNumberField(TEXT("y"), Ty);
            Params->TryGetNumberField(TEXT("z"), Tz);
            TargetLocation = FVector(Tx, Ty, Tz);
        }
        if (TargetRotation.IsNearlyZero())
        {
            double Pitch = 0, Yaw = 0, Roll = 0;
            Params->TryGetNumberField(TEXT("pitch"), Pitch);
            Params->TryGetNumberField(TEXT("yaw"), Yaw);
            Params->TryGetNumberField(TEXT("roll"), Roll);
            TargetRotation = FRotator(Pitch, Yaw, Roll);
        }
        double Duration = 4.0;
        Params->TryGetNumberField(TEXT("duration"), Duration);
        bool bEaseInOut = true;
        if (Params->HasField(TEXT("ease_in_out")))
        {
            bEaseInOut = Params->GetBoolField(TEXT("ease_in_out"));
        }
        else if (Params->HasField(TEXT("easing")))
        {
            const FString Easing = Params->GetStringField(TEXT("easing")).ToLower();
            bEaseInOut = Easing != TEXT("linear");
        }
        FString ActorPath;
        Params->TryGetStringField(TEXT("actor_path"), ActorPath);
        FString LookAtActor;
        Params->TryGetStringField(TEXT("look_at_actor"), LookAtActor);
        if (LookAtActor.IsEmpty())
        {
            Params->TryGetStringField(TEXT("look_at_actor_path"), LookAtActor);
        }
        FVector ActorTarget = FVector::ZeroVector;
        ParseVectorField(Params, TEXT("actor_target"), ActorTarget);
        if (ActorTarget.IsNearlyZero())
        {
            ParseVectorField(Params, TEXT("target_location"), ActorTarget);
        }
        if (TargetLocation.IsNearlyZero())
        {
            return MakeErrorResult(TEXT(""), TEXT("target location required for sequence.create_shot"));
        }
        const bool bOk = SequenceSubsystem->CreateCameraShot(
            TargetLocation, TargetRotation, static_cast<float>(Duration), ActorPath, ActorTarget, LookAtActor, bEaseInOut);
        return bOk
            ? MakeSuccessResult(
                  TEXT(""),
                  FString::Printf(
                      TEXT("{\"duration\":%.2f,\"camera_shot\":true,\"look_at_actor\":\"%s\",\"ease_in_out\":%s}"),
                      Duration,
                      *LookAtActor,
                      bEaseInOut ? TEXT("true") : TEXT("false")))
            : MakeErrorResult(TEXT(""), TEXT("Failed to create camera shot"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown sequence action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAudioCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!AudioSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Audio subsystem not available"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("create_metasound"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("play_quartz"))
    {
        FString ClockHandle;
        FString Timeline;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("clock"), ClockHandle);
            Params->TryGetStringField(TEXT("timeline"), Timeline);
        }
        AudioSubsystem->PlayQuartzClock(ClockHandle, Timeline);
        return MakeSuccessResult(TEXT(""), TEXT("{\"played\":true,\"cue\":\"test\"}"));
    }
    else if (Action == TEXT("synthesize"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown audio action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleVisionCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
    if (!GetGameInstance())
    {
        return MakeErrorResult(TEXT(""), TEXT("GameInstance not available"));
    }

    UHephaestusVisionSubsystem* VisionSubsystem = GetGameInstance()->GetSubsystem<UHephaestusVisionSubsystem>();
    if (!VisionSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Vision subsystem not available"));
    }

    FString Action;
    if (Params.IsValid())
    {
        Params->TryGetStringField(TEXT("action"), Action);
    }
    if (Action.IsEmpty())
    {
        Command.Split(TEXT("."), nullptr, &Action, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
    }

    if (Action == TEXT("capture_frame"))
    {
        FHephaestusFrameMetadata Metadata;
        UTexture2D* Texture = nullptr;
        const bool bSuccess = VisionSubsystem->CaptureSingleFrame(Metadata, Texture);
        if (bSuccess)
        {
            TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
            ResultObj->SetNumberField(TEXT("frame_id"), static_cast<double>(Metadata.FrameID));
            ResultObj->SetNumberField(TEXT("width"), Metadata.Resolution.X);
            ResultObj->SetNumberField(TEXT("height"), Metadata.Resolution.Y);
            ResultObj->SetStringField(TEXT("path"), VisionSubsystem->GetLatestFramePath());
            ResultObj->SetStringField(TEXT("url"), TEXT("/v1/frame"));
            FString ResultJSON;
            TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultJSON);
            FJsonSerializer::Serialize(ResultObj, Writer);
            return MakeSuccessResult(TEXT(""), ResultJSON);
        }
        return MakeErrorResult(TEXT(""), TEXT("Failed to capture frame"));
    }
    else if (Action == TEXT("start_stream"))
    {
        FHephaestusVisionConfig Config;
        if (Params.IsValid() && Params->HasField(TEXT("width")))
        {
            Config.CaptureResolution.X = Params->GetIntegerField(TEXT("width"));
        }
        if (Params.IsValid() && Params->HasField(TEXT("height")))
        {
            Config.CaptureResolution.Y = Params->GetIntegerField(TEXT("height"));
        }
        if (Params.IsValid() && Params->HasField(TEXT("fps")))
        {
            Config.TargetFPS = Params->GetIntegerField(TEXT("fps"));
        }
        const bool bSuccess = VisionSubsystem->StartCapture(Config);
        return bSuccess ? MakeSuccessResult(TEXT("")) : MakeErrorResult(TEXT(""), TEXT("Failed to start stream"));
    }
    else if (Action == TEXT("stop_stream"))
    {
        VisionSubsystem->StopCapture();
        return MakeSuccessResult(TEXT(""));
    }
    else if (Action == TEXT("inject_overlay"))
    {
        FHephaestusDebugOverlay Overlay;
        if (Params.IsValid())
        {
            Params->TryGetStringField(TEXT("label"), Overlay.Label);
        }
        VisionSubsystem->InjectDebugOverlay(Overlay);
        return MakeSuccessResult(TEXT(""));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown vision action: %s"), *Action));
}

bool UHephaestusCommandHandler::ParseTransform(const TSharedPtr<FJsonObject>& Json, FTransform& OutTransform) const
{
    if (!Json.IsValid())
    {
        return false;
    }

    FVector Location = FVector::ZeroVector;
    FVector Scale = FVector(1.0f);
    FRotator Rotation = FRotator::ZeroRotator;

    ParseVectorField(Json, TEXT("location"), Location);
    ParseRotatorField(Json, TEXT("rotation"), Rotation);
    if (!ParseVectorField(Json, TEXT("scale"), Scale))
    {
        Scale = FVector(1.0f);
    }

    OutTransform = FTransform(Rotation, Location, Scale);
    return true;
}

bool UHephaestusCommandHandler::ParseTransformParams(const TSharedPtr<FJsonObject>& Params, FTransform& OutTransform) const
{
    OutTransform = FTransform::Identity;
    if (!Params.IsValid())
    {
        return true;
    }

    bool bOk = true;
    if (Params->HasField(TEXT("transform")))
    {
        const TSharedPtr<FJsonObject>* TransformObj = nullptr;
        if (Params->TryGetObjectField(TEXT("transform"), TransformObj) && TransformObj && TransformObj->IsValid())
        {
            bOk = ParseTransform(*TransformObj, OutTransform);
        }
        else
        {
            bOk = false;
        }
    }

    // Flat aliases override nested transform fields when present
    FVector Location = OutTransform.GetLocation();
    FVector Scale = OutTransform.GetScale3D();
    FRotator Rotation = OutTransform.Rotator();
    const bool bHadLoc = ParseVectorField(Params, TEXT("location"), Location);
    const bool bHadRot = ParseRotatorField(Params, TEXT("rotation"), Rotation);
    const bool bHadScale = ParseVectorField(Params, TEXT("scale"), Scale);
    if (bHadLoc || bHadRot || bHadScale)
    {
        OutTransform = FTransform(Rotation, Location, Scale);
    }
    return bOk;
}

bool UHephaestusCommandHandler::ParseVector(const TSharedPtr<FJsonObject>& Json, FVector& OutVector) const
{
    if (!Json.IsValid())
    {
        return false;
    }

    double X = 0, Y = 0, Z = 0;
    Json->TryGetNumberField(TEXT("x"), X);
    Json->TryGetNumberField(TEXT("y"), Y);
    Json->TryGetNumberField(TEXT("z"), Z);
    OutVector = FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
    return true;
}

bool UHephaestusCommandHandler::ParseVectorField(const TSharedPtr<FJsonObject>& Parent, const FString& FieldName, FVector& OutVector) const
{
    if (!Parent.IsValid())
    {
        return false;
    }

    const TSharedPtr<FJsonValue> Field = Parent->TryGetField(FieldName);
    if (!Field.IsValid() || Field->IsNull())
    {
        return false;
    }

    if (Field->Type == EJson::Object)
    {
        return ParseVector(Field->AsObject(), OutVector);
    }

    if (Field->Type == EJson::Array)
    {
        const TArray<TSharedPtr<FJsonValue>>& Arr = Field->AsArray();
        if (Arr.Num() < 3 || !Arr[0].IsValid() || !Arr[1].IsValid() || !Arr[2].IsValid())
        {
            return false;
        }
        OutVector = FVector(
            static_cast<float>(Arr[0]->AsNumber()),
            static_cast<float>(Arr[1]->AsNumber()),
            static_cast<float>(Arr[2]->AsNumber()));
        return true;
    }
    return false;
}

bool UHephaestusCommandHandler::ParseRotator(const TSharedPtr<FJsonObject>& Json, FRotator& OutRotator) const
{
    if (!Json.IsValid())
    {
        return false;
    }

    double Pitch = 0, Yaw = 0, Roll = 0;
    Json->TryGetNumberField(TEXT("pitch"), Pitch);
    Json->TryGetNumberField(TEXT("yaw"), Yaw);
    Json->TryGetNumberField(TEXT("roll"), Roll);
    OutRotator = FRotator(static_cast<float>(Pitch), static_cast<float>(Yaw), static_cast<float>(Roll));
    return true;
}

bool UHephaestusCommandHandler::ParseRotatorField(const TSharedPtr<FJsonObject>& Parent, const FString& FieldName, FRotator& OutRotator) const
{
    if (!Parent.IsValid())
    {
        return false;
    }

    const TSharedPtr<FJsonValue> Field = Parent->TryGetField(FieldName);
    if (!Field.IsValid() || Field->IsNull())
    {
        return false;
    }

    if (Field->Type == EJson::Object)
    {
        return ParseRotator(Field->AsObject(), OutRotator);
    }

    if (Field->Type == EJson::Array)
    {
        const TArray<TSharedPtr<FJsonValue>>& Arr = Field->AsArray();
        if (Arr.Num() < 3 || !Arr[0].IsValid() || !Arr[1].IsValid() || !Arr[2].IsValid())
        {
            return false;
        }
        OutRotator = FRotator(
            static_cast<float>(Arr[0]->AsNumber()),
            static_cast<float>(Arr[1]->AsNumber()),
            static_cast<float>(Arr[2]->AsNumber()));
        return true;
    }
    return false;
}

FHephaestusCommandResult UHephaestusCommandHandler::MakeSuccessResult(const FString& CommandID, const FString& ResultJSON,
    const TArray<FString>& Assets, const TArray<FString>& Actors, float TimeMs)
{
    FHephaestusCommandResult Result;
    Result.bSuccess = true;
    Result.ResultJSON = ResultJSON;
    Result.AssetReferences = Assets;
    Result.ActorReferences = Actors;
    Result.ExecutionTimeMs = TimeMs;
    Result.CommandID = CommandID;
    return Result;
}

FHephaestusCommandResult UHephaestusCommandHandler::MakeErrorResult(const FString& CommandID, const FString& ErrorMessage, float TimeMs)
{
    FHephaestusCommandResult Result;
    Result.bSuccess = false;
    Result.ErrorMessage = ErrorMessage;
    Result.ExecutionTimeMs = TimeMs;
    Result.CommandID = CommandID;
    return Result;
}

#undef LOCTEXT_NAMESPACE
#undef LOCTEXT_NAMESPACE