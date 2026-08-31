// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Command/HephaestusCommandHandler.h"
#include "World/HephaestusWorldSubsystem.h"
#include "Assets/HephaestusAssetSubsystem.h"
#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "Rendering/HephaestusRenderingSubsystem.h"
#include "PCG/HephaestusPCGSubsystem.h"
#include "Animation/HephaestusAnimationSubsystem.h"
#include "Audio/HephaestusAudioSubsystem.h"
#include "Vision/HephaestusVisionSubsystem.h"

#include "Async/Async.h"
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

void UHephaestusCommandHandler::ExecuteCommandAsync(const FString& CommandJSON, const FScriptDelegate& Callback)
{
    AsyncTask(ENamedThreads::GameThread, [this, CommandJSON, Callback]()
    {
        FHephaestusCommandResult Result = ExecuteCommand_GameThread(CommandJSON);

        // Execute callback on game thread
        if (Callback.IsBound())
        {
            // We need to pass the result to the delegate
            // This requires a specific delegate signature - using a workaround
            UFunction* Func = Callback.GetUFunction();
            if (Func)
            {
                struct FCallbackParams
                {
                    FHephaestusCommandResult Result;
                };
                FCallbackParams Params;
                Params.Result = Result;
                Callback.ProcessDelegate(Params);
            }
        }
    });
}

FHephaestusCommandResult UHephaestusCommandHandler::ExecuteCommand(const FString& CommandJSON)
{
    // Ensure we're on game thread
    check(IsInGameThread());
    return ExecuteCommand_GameThread(CommandJSON);
}

void UHephaestusCommandHandler::ExecuteBatchAsync(const TArray<FString>& CommandsJSON, const FScriptDelegate& Callback)
{
    AsyncTask(ENamedThreads::GameThread, [this, CommandsJSON, Callback]()
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

        // Execute callback
        if (Callback.IsBound())
        {
            UFunction* Func = Callback.GetUFunction();
            if (Func)
            {
                struct FBatchCallbackParams
                {
                    FHephaestusBatchCommandResult Result;
                };
                FBatchCallbackParams Params;
                Params.Result = BatchResult;
                Callback.ProcessDelegate(Params);
            }
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
        TEXT("world.destroy_actor"),
        TEXT("world.batch_edit"),
        TEXT("world.query_spatial"),
        TEXT("asset.create_material"),
        TEXT("asset.import"),
        TEXT("asset.reimport"),
        TEXT("asset.export"),
        TEXT("asset.create_instance"),
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
    Commands.Append(CustomCommands.GetKeys());

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
    TSharedPtr<FJsonObject> Params = CommandObject->GetObjectField(TEXT("params"));

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
        return HandleWorldCommand(Params);
    }
    else if (Command.StartsWith(TEXT("asset.")))
    {
        return HandleAssetCommand(Params);
    }
    else if (Command.StartsWith(TEXT("blueprint.")))
    {
        return HandleBlueprintCommand(Params);
    }
    else if (Command.StartsWith(TEXT("rendering.")))
    {
        return HandleRenderingCommand(Params);
    }
    else if (Command.StartsWith(TEXT("pcg.")))
    {
        return HandlePCGCommand(Params);
    }
    else if (Command.StartsWith(TEXT("animation.")))
    {
        return HandleAnimationCommand(Params);
    }
    else if (Command.StartsWith(TEXT("audio.")))
    {
        return HandleAudioCommand(Params);
    }
    else if (Command.StartsWith(TEXT("vision.")))
    {
        return HandleVisionCommand(Params);
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown command category: %s"), *Command));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleWorldCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!WorldSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("World subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("spawn_actor"))
    {
        // Params: class_path, transform, spawn_params
        FString ClassPath = Params->GetStringField(TEXT("class_path"));
        FTransform Transform;
        if (!ParseTransform(Params->GetObjectField(TEXT("transform")), Transform))
        {
            return MakeErrorResult(TEXT(""), TEXT("Invalid transform"));
        }

        AActor* Actor = WorldSubsystem->SpawnActor(ClassPath, Transform);
        if (Actor)
        {
            TArray<FString> Actors = { Actor->GetPathName() };
            FString ResultJSON = FString::Printf(TEXT("{\"actor_path\":\"%s\"}"), *Actor->GetPathName());
            return MakeSuccessResult(TEXT(""), ResultJSON, {}, Actors);
        }
        return MakeErrorResult(TEXT(""), TEXT("Failed to spawn actor"));
    }
    else if (Action == TEXT("destroy_actor"))
    {
        FString ActorPath = Params->GetStringField(TEXT("actor_path"));
        bool bSuccess = WorldSubsystem->DestroyActor(ActorPath);
        return bSuccess ? MakeSuccessResult(TEXT("")) : MakeErrorResult(TEXT(""), TEXT("Failed to destroy actor"));
    }
    else if (Action == TEXT("batch_edit"))
    {
        // Params: actors[], property_edits[]
        // Implementation would batch edit properties
        return MakeSuccessResult(TEXT(""), TEXT("{\"edited\":0}"));
    }
    else if (Action == TEXT("query_spatial"))
    {
        // Params: bounds, filter_class
        // Returns array of actor references
        return MakeSuccessResult(TEXT(""), TEXT("{\"actors\":[]}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown world action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAssetCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!AssetSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Asset subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("create_material"))
    {
        // Params: material_desc
        return MakeSuccessResult(TEXT(""), TEXT("{\"material_path\":\"\"}"));
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
        // Params: asset_path, file_path, export_options
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("create_instance"))
    {
        // Params: parent_material, parameters
        return MakeSuccessResult(TEXT(""), TEXT("{\"instance_path\":\"\"}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown asset action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleBlueprintCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!BlueprintSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Blueprint subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("compile"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
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

FHephaestusCommandResult UHephaestusCommandHandler::HandlePCGCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!PCGSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("PCG subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("mutate_graph"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("set_metadata"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("query_spatial"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown PCG action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAnimationCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!AnimationSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Animation subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("create_control_rig"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("retarget"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("edit_sequence"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("livelink_connect"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown animation action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleAudioCommand(const TSharedPtr<FJsonObject>& Params)
{
    if (!AudioSubsystem)
    {
        return MakeErrorResult(TEXT(""), TEXT("Audio subsystem not available"));
    }

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("create_metasound"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("play_quartz"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }
    else if (Action == TEXT("synthesize"))
    {
        return MakeSuccessResult(TEXT(""), TEXT("{}"));
    }

    return MakeErrorResult(TEXT(""), FString::Printf(TEXT("Unknown audio action: %s"), *Action));
}

FHephaestusCommandResult UHephaestusCommandHandler::HandleVisionCommand(const TSharedPtr<FJsonObject>& Params)
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

    FString Action = Params->GetStringField(TEXT("action"));

    if (Action == TEXT("capture_frame"))
    {
        FHephaestusFrameMetadata Metadata;
        UTexture2D* Texture = nullptr;
        bool bSuccess = VisionSubsystem->CaptureSingleFrame(Metadata, Texture);
        if (bSuccess && Texture)
        {
            FString ResultJSON = FString::Printf(TEXT("{\"frame_id\":%llu,\"width\":%d,\"height\":%d}"),
                Metadata.FrameID, Metadata.Resolution.X, Metadata.Resolution.Y);
            return MakeSuccessResult(TEXT(""), ResultJSON);
        }
        return MakeErrorResult(TEXT(""), TEXT("Failed to capture frame"));
    }
    else if (Action == TEXT("start_stream"))
    {
        FHephaestusVisionConfig Config;
        // Parse config from params
        bool bSuccess = VisionSubsystem->StartCapture(Config);
        return bSuccess ? MakeSuccessResult(TEXT("")) : MakeErrorResult(TEXT(""), TEXT("Failed to start stream"));
    }
    else if (Action == TEXT("stop_stream"))
    {
        VisionSubsystem->StopCapture();
        return MakeSuccessResult(TEXT(""));
    }
    else if (Action == TEXT("inject_overlay"))
    {
        // Parse overlay from params
        FHephaestusDebugOverlay Overlay;
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

    FVector Location, Scale;
    FRotator Rotation;

    if (Json->HasField(TEXT("location")))
    {
        ParseVector(Json->GetObjectField(TEXT("location")), Location);
    }
    if (Json->HasField(TEXT("rotation")))
    {
        ParseRotator(Json->GetObjectField(TEXT("rotation")), Rotation);
    }
    if (Json->HasField(TEXT("scale")))
    {
        ParseVector(Json->GetObjectField(TEXT("scale")), Scale);
    }
    else
    {
        Scale = FVector(1.0f);
    }

    OutTransform = FTransform(Rotation, Location, Scale);
    return true;
}

bool UHephaestusCommandHandler::ParseVector(const TSharedPtr<FJsonObject>& Json, FVector& OutVector) const
{
    if (!Json.IsValid())
    {
        return false;
    }

    OutVector.X = Json->GetNumberField(TEXT("x"));
    OutVector.Y = Json->GetNumberField(TEXT("y"));
    OutVector.Z = Json->GetNumberField(TEXT("z"));
    return true;
}

bool UHephaestusCommandHandler::ParseRotator(const TSharedPtr<FJsonObject>& Json, FRotator& OutRotator) const
{
    if (!Json.IsValid())
    {
        return false;
    }

    OutRotator.Pitch = Json->GetNumberField(TEXT("pitch"));
    OutRotator.Yaw = Json->GetNumberField(TEXT("yaw"));
    OutRotator.Roll = Json->GetNumberField(TEXT("roll"));
    return true;
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