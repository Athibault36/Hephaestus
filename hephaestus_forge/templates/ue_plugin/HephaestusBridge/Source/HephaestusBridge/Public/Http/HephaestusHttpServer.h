// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "HttpResultCallback.h"
#include "IHttpRouter.h"
#include "HephaestusHttpServer.generated.h"

struct FHttpServerRequest;
struct FHephaestusCommandResult;
class UHephaestusCommandHandler;

/**
 * UHephaestusHttpServer
 *
 * Exposes UHephaestusCommandHandler over a small local HTTP server so external
 * agents (e.g. the Python hephaestus_forge.runtime.UEClient) can drive the
 * engine. Routes:
 *   GET  /health   -> {"status":"ok", "commands": N}
 *   GET  /commands -> {"commands":[...]}
 *   POST /command  -> executes one {"command","params"} envelope
 *   POST /batch    -> executes {"commands":[...]} in order
 *
 * UE's HTTP server dispatches request handlers on the game thread, so commands
 * are executed synchronously via UHephaestusCommandHandler::ExecuteCommand.
 *
 * The listen port comes from the HEPHAESTUS_UE_PORT env var (default 8099).
 */
UCLASS()
class HEPHAESTUSBRIDGE_API UHephaestusHttpServer : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Bind routes on the given port and start listening. */
    void StartServer(uint32 InPort);

    /** Stop listening and release the router. */
    void StopServer();

    /** The port the server is bound to (0 if not started). */
    uint32 GetPort() const { return BoundPort; }

    /** Default port, overridable via the HEPHAESTUS_UE_PORT environment variable. */
    static uint32 ResolvePort();

    /** Shared token from HEPHAESTUS_BRIDGE_TOKEN (empty = auth disabled unless forced). */
    static FString ResolveAuthToken();

    /** True when HEPHAESTUS_REQUIRE_AUTH=1 or a bridge token is configured. */
    static bool ShouldRequireAuth();

private:
    /** Return false after sending 401/503 when auth fails. */
    bool AuthorizeMutation(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete) const;

    static FString HeaderValue(const FHttpServerRequest& Request, const FString& HeaderName);

    bool HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleBatch(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleCommands(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    /** GET /frame/:id -> PNG bytes of the latest captured viewport frame. */
    bool HandleFrame(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

    UHephaestusCommandHandler* GetCommandHandler() const;

    static FString RequestBodyToString(const FHttpServerRequest& Request);
    static FString ResultToJson(const FHephaestusCommandResult& Result);
    static void RespondJson(const FHttpResultCallback& OnComplete, const FString& Json, int32 StatusCode = 200);

    TSharedPtr<IHttpRouter> Router;
    TArray<FHttpRouteHandle> RouteHandles;
    uint32 BoundPort = 0;
};
