// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

#if WITH_EDITOR

#include "EditorSubsystem.h"
#include "HttpRouteHandle.h"
#include "HttpResultCallback.h"
#include "HephaestusEditorRemoteSubsystem.generated.h"

class IHttpRouter;
struct FHttpServerRequest;

/**
 * Editor-time HTTP control plane for engage/disengage PIE.
 *
 * Lives while the Unreal Editor has the project open (plugin loaded).
 * Default port 8766 (override: -HephaestusEditorPort=).
 *
 *   GET  /v1/health
 *   POST /v1/command   { "command": "editor.play"|"editor.stop", "params": {} }
 */
UCLASS()
class HEPHAESTUSBRIDGE_API UHephaestusEditorRemoteSubsystem : public UEditorSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	int32 GetListenPort() const { return ListenPort; }
	bool IsListening() const { return bIsListening; }

private:
	bool StartHttpServer();
	void StopHttpServer();

	bool HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
	bool HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
	bool HandleCors(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

	static void ApplyCors(TUniquePtr<FHttpServerResponse>& Response);
	static FString BodyToString(const TArray<uint8>& Body);
	static bool IsPieActive();
	static bool RequestPlay();
	static bool RequestStop();

	int32 ListenPort = 8766;
	bool bIsListening = false;

	TSharedPtr<IHttpRouter> HttpRouter;
	FHttpRouteHandle HealthRoute;
	FHttpRouteHandle CommandRoute;
	FHttpRouteHandle CorsHealthRoute;
	FHttpRouteHandle CorsCommandRoute;
};

#endif // WITH_EDITOR
