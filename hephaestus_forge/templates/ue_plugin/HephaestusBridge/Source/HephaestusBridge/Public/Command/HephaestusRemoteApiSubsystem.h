// Copyright (c) 2024 HephaestusForge. All Rights Reserved.



#pragma once



#include "CoreMinimal.h"

#include "Subsystems/GameInstanceSubsystem.h"

#include "HttpRouteHandle.h"

#include "HttpResultCallback.h"

#include "HephaestusRemoteApiSubsystem.generated.h"



class IHttpRouter;

struct FHttpServerRequest;



/**

 * Localhost HTTP bridge for external agents (forge CLI / Mission Control).

 * Starts with PIE GameInstance; stops when PIE ends.

 *

 *   GET  /v1/health

 *   GET  /v1/frame     latest PNG (capture first via vision.capture_frame)

 *   POST /v1/command   body = Hephaestus command JSON

 *   OPTIONS /*         CORS preflight

 */

UCLASS()

class HEPHAESTUSBRIDGE_API UHephaestusRemoteApiSubsystem : public UGameInstanceSubsystem

{

	GENERATED_BODY()



public:

	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	virtual void Deinitialize() override;



	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Remote")

	int32 GetListenPort() const { return ListenPort; }



	UFUNCTION(BlueprintCallable, Category = "Hephaestus|Remote")

	bool IsListening() const { return bIsListening; }



private:

	bool StartHttpServer();

	void StopHttpServer();



	bool HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

	bool HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

	bool HandleFrame(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

	bool HandleCors(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);



	static void ApplyCors(TUniquePtr<FHttpServerResponse>& Response);

	static FString BodyToString(const TArray<uint8>& Body);

	static FString ResultToJson(const struct FHephaestusCommandResult& Result);



	int32 ListenPort = 8765;

	bool bIsListening = false;



	TSharedPtr<IHttpRouter> HttpRouter;

	FHttpRouteHandle HealthRoute;

	FHttpRouteHandle CommandRoute;

	FHttpRouteHandle FrameRoute;

	FHttpRouteHandle CorsCommandRoute;

	FHttpRouteHandle CorsFrameRoute;

	FHttpRouteHandle CorsHealthRoute;

};


