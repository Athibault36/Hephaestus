// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HephaestusCommandHandler.generated.h"

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

	UPROPERTY(BlueprintReadWrite)
	bool bSuccess = false;

	UPROPERTY(BlueprintReadWrite)
	FString ErrorMessage;

	UPROPERTY(BlueprintReadWrite)
	FString ResultJSON;

	UPROPERTY(BlueprintReadWrite)
	TArray<FString> AssetReferences;

	UPROPERTY(BlueprintReadWrite)
	TArray<FString> ActorReferences;

	UPROPERTY(BlueprintReadWrite)
	float ExecutionTimeMs = 0.0f;

	UPROPERTY(BlueprintReadWrite)
	FString CommandID;
};

/** Batch command result */
USTRUCT(BlueprintType)
struct FHephaestusBatchCommandResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	bool bOverallSuccess = false;

	UPROPERTY(BlueprintReadWrite)
	TArray<FHephaestusCommandResult> Results;

	UPROPERTY(BlueprintReadWrite)
	float TotalTimeMs = 0.0f;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnCommandExecuted, const FHephaestusCommandResult&, Result);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnCommandFailed, const FString&, CommandID, const FString&, ErrorMessage);

/** Native custom command handler (not Blueprint-exposed) */
DECLARE_DELEGATE_RetVal_TwoParams(bool, FHephaestusCustomCommandDelegate, const FString& /*CommandJSON*/, FHephaestusCommandResult& /*OutResult*/);

/**
 * UHephaestusCommandHandler
 *
 * Thread-safe command dispatcher that routes agent commands to subsystems.
 */
UCLASS(Blueprintable, Category = "Hephaestus")
class HEPHAESTUSBRIDGE_API UHephaestusCommandHandler : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Execute a single command (synchronous - game thread) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
	FHephaestusCommandResult ExecuteCommand(const FString& CommandJSON);

	/**
	 * Python/editor-friendly entry: resolve PIE/game GameInstance and run a command.
	 * Use this from Unreal Python — GameInstance.get_subsystem is not exposed.
	 */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command", meta = (WorldContext = "WorldContextObject"))
	static FHephaestusCommandResult ExecuteCommandForWorld(const UObject* WorldContextObject, const FString& CommandJSON);

	/** Execute multiple commands in sequence (synchronous) */
	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Command")
	FHephaestusBatchCommandResult ExecuteBatch(const TArray<FString>& CommandsJSON);

	/** Execute a single command asynchronously (native callback) */
	void ExecuteCommandAsync(const FString& CommandJSON, TFunction<void(const FHephaestusCommandResult&)> Callback);

	/** Execute multiple commands asynchronously (native callback) */
	void ExecuteBatchAsync(const TArray<FString>& CommandsJSON, TFunction<void(const FHephaestusBatchCommandResult&)> Callback);

	/** Register a custom command handler (native) */
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

	UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Command")
	FOnCommandExecuted OnCommandExecuted;

	UPROPERTY(BlueprintAssignable, Category = "Hephaestus|Command")
	FOnCommandFailed OnCommandFailed;

protected:
	FHephaestusCommandResult ExecuteCommand_GameThread(const FString& CommandJSON);
	FHephaestusCommandResult RouteCommand(const TSharedPtr<FJsonObject>& CommandObject);

	FHephaestusCommandResult HandleWorldCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleAssetCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleBlueprintCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleRenderingCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandlePCGCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleAnimationCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleAudioCommand(const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleVisionCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params);
	FHephaestusCommandResult HandleCustomCommand(const TSharedPtr<FJsonObject>& Params);

	bool ParseTransform(const TSharedPtr<FJsonObject>& Json, FTransform& OutTransform) const;
	/** Parse transform from nested "transform" and/or flat location/rotation/scale fields (object or [x,y,z] arrays). */
	bool ParseTransformParams(const TSharedPtr<FJsonObject>& Params, FTransform& OutTransform) const;
	bool ParseVector(const TSharedPtr<FJsonObject>& Json, FVector& OutVector) const;
	bool ParseVectorField(const TSharedPtr<FJsonObject>& Parent, const FString& FieldName, FVector& OutVector) const;
	bool ParseRotator(const TSharedPtr<FJsonObject>& Json, FRotator& OutRotator) const;
	bool ParseRotatorField(const TSharedPtr<FJsonObject>& Parent, const FString& FieldName, FRotator& OutRotator) const;

	FHephaestusCommandResult MakeSuccessResult(const FString& CommandID, const FString& ResultJSON = TEXT("{}"),
		const TArray<FString>& Assets = TArray<FString>(), const TArray<FString>& Actors = TArray<FString>(), float TimeMs = 0.0f);

	FHephaestusCommandResult MakeErrorResult(const FString& CommandID, const FString& ErrorMessage, float TimeMs = 0.0f);

private:
	TObjectPtr<UHephaestusWorldSubsystem> WorldSubsystem;
	TObjectPtr<UHephaestusAssetSubsystem> AssetSubsystem;
	TObjectPtr<UHephaestusBlueprintSubsystem> BlueprintSubsystem;
	TObjectPtr<UHephaestusRenderingSubsystem> RenderingSubsystem;
	TObjectPtr<UHephaestusPCGSubsystem> PCGSubsystem;
	TObjectPtr<UHephaestusAnimationSubsystem> AnimationSubsystem;
	TObjectPtr<UHephaestusAudioSubsystem> AudioSubsystem;

	TMap<FString, FHephaestusCustomCommandDelegate> CustomCommands;
	mutable FCriticalSection CustomCommandsLock;

	uint64 CommandCounter = 0;
	int64 TotalCommandsExecuted = 0;
	int64 TotalCommandsFailed = 0;
	double TotalExecutionTimeMs = 0.0;
};
