// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusCommandHandler.generated.h"

// Forward declarations
class UHephaestusWorldSubsystem;
class UHephaestusAssetSubsystem;
class UHephaestusBlueprintSubsystem;
class UHephaestusRenderingSubsystem;
class UHephaestusPCGSubsystem;
class UHephaestusAnimationSubsystem;
class UHephaestusAudioSubsystem;

/** Command execution result */
USTRUCT(BlueprintType)
struct FHephaestusCommandResult
{
    GENERATED_BODY()

    /** Whether command succeeded */
    UPROPERTY(BlueprintReadWrite)
    bool bSuccess = false;

    /** Error message if failed */
    UPROPERTY(BlueprintReadWrite)
    FString ErrorMessage;

    /** JSON result payload */
    UPROPERTY(BlueprintReadWrite)
    FString ResultJSON;

    /** Asset references created/modified */
    UPROPERTY(BlueprintReadWrite)
    TArray<FString> AssetReferences;

    /** Actor references created/modified */
    UPROPERTY(BlueprintReadWrite)
    TArray<FString> ActorReferences;

    /** Execution time in milliseconds */
    UPROPERTY(BlueprintReadWrite)
    float ExecutionTimeMs = 0.0f;

    /** Command ID for correlation */
    UPROPERTY(BlueprintReadWrite)
    FString CommandID;
};

/** Batch command result */
USTRUCT(BlueprintType)
struct FHephaestusBatchCommandResult
{
    GENERATED_BODY()

    /** Overall success */
    UPROPERTY(BlueprintReadWrite)
    bool bOverallSuccess = false;

    /** Individual results */
    UPROPERTY(BlueprintReadWrite)
    TArray<FHephaestusCommandResult> Results;

    /** Total execution time */
    UPROPERTY(BlueprintReadWrite)
    float TotalTimeMs = 0.0f;
};

/** Command handler delegate for custom commands */
DECLARE_DELEGATE_RetVal_TwoParams(bool, FHephaestusCustomCommandDelegate, const FString& /*CommandJSON*/, FHephaestusCommandResult& /*OutResult*/);

/**
 * UHephaestusCommandHandler
 * 
 * Thread-safe command dispatcher that routes agent commands to appropriate subsystems.
 * Executes all commands on the Game Thread via AsyncTask.
 * Supports: World manipulation, Asset operations, Blueprint editing, Rendering, PCG, Animation, Audio.
 * Provides JSON-based command protocol for gRPC/WebRTC transport.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusCommandHandler : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    // ~ UGameInstanceSubsystem interface
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    // ~ End UGameInstanceSubsystem interface

    /** Execute a single command (async, returns via callback) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    void ExecuteCommandAsync(const FString& CommandJSON, const FScriptDelegate& Callback);

    /** Execute a single command (synchronous - blocks game thread) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    FHephaestusCommandResult ExecuteCommand(const FString& CommandJSON);

    /** Execute multiple commands in sequence (async) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    void ExecuteBatchAsync(const TArray<FString>& CommandsJSON, const FScriptDelegate& Callback);

    /** Execute multiple commands in sequence (synchronous) */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    FHephaestusBatchCommandResult ExecuteBatch(const TArray<FString>& CommandsJSON);

    /** Register a custom command handler */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    bool RegisterCustomCommand(const FString& CommandName, const FHephaestusCustomCommandDelegate& Handler);

    /** Unregister a custom command handler */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    bool UnregisterCustomCommand(const FString& CommandName);

    /** Get list of available command names */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    TArray<FString> GetAvailableCommands() const;

    /** Validate command JSON without executing */
    UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
    bool ValidateCommand(const FString& CommandJSON, FString& OutErrorMessage) const;

    /** Events */
    UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Command")
    FOnCommandExecuted OnCommandExecuted;

    UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Command")
    FOnCommandFailed OnCommandFailed;

protected:
    /** Internal: Execute command on game thread */
    FHephaestusCommandResult ExecuteCommand_GameThread(const FString& CommandJSON);

    /** Internal: Route command to appropriate handler */
    FHephaestusCommandResult RouteCommand(const TSharedPtr<FJsonObject>& CommandObject);

    /** Command handlers */
    FHephaestusCommandResult HandleWorldCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleAssetCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleBlueprintCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleRenderingCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandlePCGCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleAnimationCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleAudioCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleVisionCommand(const TSharedPtr<FJsonObject>& Params);
    FHephaestusCommandResult HandleCustomCommand(const TSharedPtr<FJsonObject>& Params);

    /** Helper: Parse transform from JSON */
    bool ParseTransform(const TSharedPtr<FJsonObject>& Json, FTransform& OutTransform) const;

    /** Helper: Parse vector from JSON */
    bool ParseVector(const TSharedPtr<FJsonObject>& Json, FVector& OutVector) const;

    /** Helper: Parse rotator from JSON */
    bool ParseRotator(const TSharedPtr<FJsonObject>& Json, FRotator& OutRotator) const;

    /** Helper: Create result from success */
    FHephaestusCommandResult MakeSuccessResult(const FString& CommandID, const FString& ResultJSON = TEXT("{}"),
        const TArray<FString>& Assets = {}, const TArray<FString>& Actors = {}, float TimeMs = 0.0f);

    /** Helper: Create result from error */
    FHephaestusCommandResult MakeErrorResult(const FString& CommandID, const FString& ErrorMessage, float TimeMs = 0.0f);

private:
    /** Subsystem references */
    TObjectPtr<UHephaestusWorldSubsystem> WorldSubsystem;
    TObjectPtr<UHephaestusAssetSubsystem> AssetSubsystem;
    TObjectPtr<UHephaestusBlueprintSubsystem> BlueprintSubsystem;
    TObjectPtr<UHephaestusRenderingSubsystem> RenderingSubsystem;
    TObjectPtr<UHephaestusPCGSubsystem> PCGSubsystem;
    TObjectPtr<UHephaestusAnimationSubsystem> AnimationSubsystem;
    TObjectPtr<UHephaestusAudioSubsystem> AudioSubsystem;

    /** Custom command handlers */
    TMap<FString, FHephaestusCustomCommandDelegate> CustomCommands;
    mutable FCriticalSection CustomCommandsLock;

    /** Command ID generator */
    uint64 CommandCounter = 0;

    /** Statistics */
    int64 TotalCommandsExecuted = 0;
    int64 TotalCommandsFailed = 0;
    double TotalExecutionTimeMs = 0.0;
};

/** Delegate for async command execution */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnCommandExecuted, const FHephaestusCommandResult&, Result);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnCommandFailed, const FString&, CommandID, const FString&, ErrorMessage);