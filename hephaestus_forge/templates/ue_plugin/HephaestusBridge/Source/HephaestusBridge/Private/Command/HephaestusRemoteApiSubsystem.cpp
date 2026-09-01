// Copyright (c) 2024 HephaestusForge. All Rights Reserved.



#include "Command/HephaestusRemoteApiSubsystem.h"

#include "Command/HephaestusCommandHandler.h"

#include "Vision/HephaestusVisionSubsystem.h"

#include "HephaestusBridge.h"
#include "HephaestusVersion.h"



#include "Async/Async.h"

#include "HttpPath.h"

#include "HttpServerModule.h"

#include "IHttpRouter.h"

#include "HttpServerRequest.h"

#include "HttpServerResponse.h"

#include "HttpServerConstants.h"

#include "Misc/CommandLine.h"

#include "Misc/Parse.h"

#include "Serialization/JsonSerializer.h"

#include "Serialization/JsonWriter.h"



void UHephaestusRemoteApiSubsystem::Initialize(FSubsystemCollectionBase& Collection)

{

	Super::Initialize(Collection);



	int32 PortOverride = 0;

	if (FParse::Value(FCommandLine::Get(), TEXT("HephaestusRemotePort="), PortOverride) && PortOverride > 0)

	{

		ListenPort = PortOverride;

	}



	if (StartHttpServer())

	{

		UE_LOG(LogHephaestusBridge, Log,

			TEXT("HephaestusRemoteApi: listening on http://127.0.0.1:%d  (POST /v1/command, GET /v1/frame)"), ListenPort);

	}

	else

	{

		UE_LOG(LogHephaestusBridge, Error,

			TEXT("HephaestusRemoteApi: failed to bind port %d"), ListenPort);

	}

}



void UHephaestusRemoteApiSubsystem::Deinitialize()

{

	StopHttpServer();

	Super::Deinitialize();

}



bool UHephaestusRemoteApiSubsystem::StartHttpServer()

{

	if (!FHttpServerModule::IsAvailable())

	{

		FModuleManager::LoadModuleChecked<FHttpServerModule>(TEXT("HTTPServer"));

	}



	HttpRouter = FHttpServerModule::Get().GetHttpRouter(static_cast<uint32>(ListenPort), /*bFailOnBindFailure=*/true);

	if (!HttpRouter.IsValid())

	{

		return false;

	}



	HealthRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/health")),

		EHttpServerRequestVerbs::VERB_GET,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleHealth));



	CommandRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/command")),

		EHttpServerRequestVerbs::VERB_POST,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleCommand));



	FrameRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/frame")),

		EHttpServerRequestVerbs::VERB_GET,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleFrame));



	CorsHealthRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/health")),

		EHttpServerRequestVerbs::VERB_OPTIONS,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleCors));



	CorsCommandRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/command")),

		EHttpServerRequestVerbs::VERB_OPTIONS,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleCors));



	CorsFrameRoute = HttpRouter->BindRoute(

		FHttpPath(TEXT("/v1/frame")),

		EHttpServerRequestVerbs::VERB_OPTIONS,

		FHttpRequestHandler::CreateUObject(this, &UHephaestusRemoteApiSubsystem::HandleCors));



	if (!HealthRoute.IsValid() || !CommandRoute.IsValid() || !FrameRoute.IsValid())

	{

		StopHttpServer();

		return false;

	}



	FHttpServerModule::Get().StartAllListeners();

	bIsListening = true;

	return true;

}



void UHephaestusRemoteApiSubsystem::StopHttpServer()

{

	if (HttpRouter.IsValid())

	{

		auto Unbind = [this](FHttpRouteHandle& Handle)

		{

			if (Handle.IsValid())

			{

				HttpRouter->UnbindRoute(Handle);

				Handle.Reset();

			}

		};

		Unbind(HealthRoute);

		Unbind(CommandRoute);

		Unbind(FrameRoute);

		Unbind(CorsHealthRoute);

		Unbind(CorsCommandRoute);

		Unbind(CorsFrameRoute);

		HttpRouter.Reset();

	}

	bIsListening = false;

}



void UHephaestusRemoteApiSubsystem::ApplyCors(TUniquePtr<FHttpServerResponse>& Response)

{

	if (!Response.IsValid())

	{

		return;

	}

	Response->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });

	Response->Headers.Add(TEXT("Access-Control-Allow-Methods"), { TEXT("GET, POST, OPTIONS") });

	Response->Headers.Add(TEXT("Access-Control-Allow-Headers"), { TEXT("Content-Type") });

}



bool UHephaestusRemoteApiSubsystem::HandleCors(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)

{

	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(TEXT(""), TEXT("text/plain"));

	Response->Code = EHttpServerResponseCodes::NoContent;

	ApplyCors(Response);

	OnComplete(MoveTemp(Response));

	return true;

}



bool UHephaestusRemoteApiSubsystem::HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)

{

	const FString Body = FString::Printf(

		TEXT("{\"ok\":true,\"service\":\"hephaestus-remote\",\"port\":%d,\"plugin_version\":\"%s\"}"),
		ListenPort,
		HEPHAESTUS_BRIDGE_VERSION);

	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(Body, TEXT("application/json"));

	Response->Code = EHttpServerResponseCodes::Ok;

	ApplyCors(Response);

	OnComplete(MoveTemp(Response));

	return true;

}



bool UHephaestusRemoteApiSubsystem::HandleFrame(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)

{

	TWeakObjectPtr<UHephaestusRemoteApiSubsystem> WeakThis(this);

	AsyncTask(ENamedThreads::GameThread, [WeakThis, OnComplete]()

	{

		TArray64<uint8> PngCopy;

		if (WeakThis.IsValid())

		{

			if (UGameInstance* GI = WeakThis->GetGameInstance())

			{

				if (UHephaestusVisionSubsystem* Vision = GI->GetSubsystem<UHephaestusVisionSubsystem>())

				{

					PngCopy = Vision->GetLatestFramePng();

				}

			}

		}



		if (PngCopy.Num() == 0)

		{

			TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(

				TEXT("{\"error\":\"no_frame\",\"hint\":\"POST vision.capture_frame first\"}"),

				TEXT("application/json"));

			Response->Code = EHttpServerResponseCodes::NotFound;

			ApplyCors(Response);

			OnComplete(MoveTemp(Response));

			return;

		}



		TArray<uint8> Body;

		Body.Append(PngCopy.GetData(), static_cast<int32>(PngCopy.Num()));

		TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(MoveTemp(Body), TEXT("image/png"));

		Response->Code = EHttpServerResponseCodes::Ok;

		ApplyCors(Response);

		OnComplete(MoveTemp(Response));

	});



	return true;

}



bool UHephaestusRemoteApiSubsystem::HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)

{

	const FString CommandJSON = BodyToString(Request.Body);

	if (CommandJSON.IsEmpty())

	{

		TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Error(

			EHttpServerResponseCodes::BadRequest, TEXT("empty_body"), TEXT("POST body must be command JSON"));

		ApplyCors(Response);

		OnComplete(MoveTemp(Response));

		return true;

	}



	TWeakObjectPtr<UHephaestusRemoteApiSubsystem> WeakThis(this);

	AsyncTask(ENamedThreads::GameThread, [WeakThis, CommandJSON, OnComplete]()

	{

		FHephaestusCommandResult Result;

		if (!WeakThis.IsValid())

		{

			Result.bSuccess = false;

			Result.ErrorMessage = TEXT("Remote API subsystem destroyed");

		}

		else

		{

			Result = UHephaestusCommandHandler::ExecuteCommandForWorld(WeakThis.Get(), CommandJSON);

		}



		const FString ResponseBody = UHephaestusRemoteApiSubsystem::ResultToJson(Result);

		TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(ResponseBody, TEXT("application/json"));

		Response->Code = Result.bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest;

		ApplyCors(Response);

		OnComplete(MoveTemp(Response));

	});



	return true;

}



FString UHephaestusRemoteApiSubsystem::BodyToString(const TArray<uint8>& Body)

{

	if (Body.Num() == 0)

	{

		return FString();

	}

	TArray<uint8> NullTerminated = Body;

	NullTerminated.Add(0);

	return FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(NullTerminated.GetData())));

}



FString UHephaestusRemoteApiSubsystem::ResultToJson(const FHephaestusCommandResult& Result)

{

	TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();

	Obj->SetBoolField(TEXT("success"), Result.bSuccess);

	Obj->SetStringField(TEXT("error"), Result.ErrorMessage);

	Obj->SetStringField(TEXT("result_json"), Result.ResultJSON);

	Obj->SetStringField(TEXT("command_id"), Result.CommandID);

	Obj->SetNumberField(TEXT("time_ms"), Result.ExecutionTimeMs);



	TArray<TSharedPtr<FJsonValue>> Actors;

	for (const FString& Path : Result.ActorReferences)

	{

		Actors.Add(MakeShared<FJsonValueString>(Path));

	}

	Obj->SetArrayField(TEXT("actor_paths"), Actors);



	TArray<TSharedPtr<FJsonValue>> Assets;

	for (const FString& Path : Result.AssetReferences)

	{

		Assets.Add(MakeShared<FJsonValueString>(Path));

	}

	Obj->SetArrayField(TEXT("asset_paths"), Assets);



	FString Out;

	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);

	FJsonSerializer::Serialize(Obj, Writer);

	return Out;

}


