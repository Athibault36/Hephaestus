// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#if WITH_EDITOR

#include "Command/HephaestusEditorRemoteSubsystem.h"

#include "HephaestusBridge.h"
#include "HephaestusVersion.h"

#include "Async/Async.h"
#include "Editor.h"
#include "Editor/UnrealEdEngine.h"
#include "HttpPath.h"
#include "HttpServerConstants.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealEdGlobals.h"

void UHephaestusEditorRemoteSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	int32 PortOverride = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("HephaestusEditorPort="), PortOverride) && PortOverride > 0)
	{
		ListenPort = PortOverride;
	}

	if (StartHttpServer())
	{
		UE_LOG(LogHephaestusBridge, Log,
			TEXT("HephaestusEditorRemote: listening on http://127.0.0.1:%d  (editor.play / editor.stop)"),
			ListenPort);
	}
	else
	{
		UE_LOG(LogHephaestusBridge, Error,
			TEXT("HephaestusEditorRemote: failed to bind port %d"), ListenPort);
	}
}

void UHephaestusEditorRemoteSubsystem::Deinitialize()
{
	StopHttpServer();
	Super::Deinitialize();
}

bool UHephaestusEditorRemoteSubsystem::StartHttpServer()
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
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleHealth));

	CommandRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/command")),
		EHttpServerRequestVerbs::VERB_POST,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCommand));

	CorsHealthRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/health")),
		EHttpServerRequestVerbs::VERB_OPTIONS,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCors));

	CorsCommandRoute = HttpRouter->BindRoute(
		FHttpPath(TEXT("/v1/command")),
		EHttpServerRequestVerbs::VERB_OPTIONS,
		FHttpRequestHandler::CreateUObject(this, &UHephaestusEditorRemoteSubsystem::HandleCors));

	if (!HealthRoute.IsValid() || !CommandRoute.IsValid())
	{
		StopHttpServer();
		return false;
	}

	FHttpServerModule::Get().StartAllListeners();
	bIsListening = true;
	return true;
}

void UHephaestusEditorRemoteSubsystem::StopHttpServer()
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
		Unbind(CorsHealthRoute);
		Unbind(CorsCommandRoute);
		HttpRouter.Reset();
	}
	bIsListening = false;
}

void UHephaestusEditorRemoteSubsystem::ApplyCors(TUniquePtr<FHttpServerResponse>& Response)
{
	if (!Response.IsValid())
	{
		return;
	}
	Response->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });
	Response->Headers.Add(TEXT("Access-Control-Allow-Methods"), { TEXT("GET, POST, OPTIONS") });
	Response->Headers.Add(TEXT("Access-Control-Allow-Headers"), { TEXT("Content-Type") });
}

bool UHephaestusEditorRemoteSubsystem::HandleCors(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(TEXT(""), TEXT("text/plain"));
	Response->Code = EHttpServerResponseCodes::NoContent;
	ApplyCors(Response);
	OnComplete(MoveTemp(Response));
	return true;
}

bool UHephaestusEditorRemoteSubsystem::IsPieActive()
{
	return GEditor != nullptr && GEditor->PlayWorld != nullptr;
}

bool UHephaestusEditorRemoteSubsystem::RequestPlay()
{
	if (!GUnrealEd)
	{
		return false;
	}
	if (IsPieActive())
	{
		return true;
	}
	FRequestPlaySessionParams Params;
	GUnrealEd->RequestPlaySession(Params);
	return true;
}

bool UHephaestusEditorRemoteSubsystem::RequestStop()
{
	if (!GUnrealEd)
	{
		return false;
	}
	if (!IsPieActive())
	{
		return true;
	}
	GUnrealEd->RequestEndPlayMap();
	return true;
}

bool UHephaestusEditorRemoteSubsystem::HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("ok"), true);
	Root->SetStringField(TEXT("service"), TEXT("hephaestus-editor"));
	Root->SetNumberField(TEXT("port"), ListenPort);
	Root->SetNumberField(TEXT("pie_port"), 8765);
	Root->SetBoolField(TEXT("pie_active"), IsPieActive());
	Root->SetStringField(TEXT("plugin_version"), HEPHAESTUS_BRIDGE_VERSION);
	Root->SetStringField(TEXT("project_name"), FApp::GetProjectName());
	Root->SetStringField(TEXT("project_dir"), FPaths::ConvertRelativePathToFull(FPaths::ProjectDir()));

	FString Body;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
	FJsonSerializer::Serialize(Root, Writer);

	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(Body, TEXT("application/json"));
	Response->Code = EHttpServerResponseCodes::Ok;
	ApplyCors(Response);
	OnComplete(MoveTemp(Response));
	return true;
}

bool UHephaestusEditorRemoteSubsystem::HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
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

	TWeakObjectPtr<UHephaestusEditorRemoteSubsystem> WeakThis(this);
	AsyncTask(ENamedThreads::GameThread, [WeakThis, CommandJSON, OnComplete]()
	{
		bool bSuccess = false;
		FString Error;
		FString Action;

		TSharedPtr<FJsonObject> JsonObject;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(CommandJSON);
		if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
		{
			Error = TEXT("Invalid JSON");
		}
		else
		{
			Action = JsonObject->GetStringField(TEXT("command"));
			if (Action.Equals(TEXT("editor.play"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.start"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.play"), ESearchCase::IgnoreCase))
			{
				bSuccess = WeakThis.IsValid() && RequestPlay();
				if (!bSuccess)
				{
					Error = TEXT("Failed to request Play session (is UnrealEd available?)");
				}
			}
			else if (Action.Equals(TEXT("editor.stop"), ESearchCase::IgnoreCase)
				|| Action.Equals(TEXT("pie.stop"), ESearchCase::IgnoreCase))
			{
				bSuccess = WeakThis.IsValid() && RequestStop();
				if (!bSuccess)
				{
					Error = TEXT("Failed to request End Play (is UnrealEd available?)");
				}
			}
			else
			{
				Error = FString::Printf(
					TEXT("Unknown editor command '%s' (use editor.play or editor.stop)"), *Action);
			}
		}

		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetBoolField(TEXT("success"), bSuccess);
		Out->SetStringField(TEXT("error"), Error);
		Out->SetStringField(TEXT("command"), Action);
		Out->SetBoolField(TEXT("pie_active"), IsPieActive());
		Out->SetStringField(TEXT("result_json"), bSuccess
			? FString::Printf(TEXT("{\"action\":\"%s\",\"pie_active\":%s}"),
				*Action, IsPieActive() ? TEXT("true") : TEXT("false"))
			: TEXT("{}"));

		FString ResponseBody;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResponseBody);
		FJsonSerializer::Serialize(Out, Writer);

		TUniquePtr<FHttpServerResponse> Response =
			FHttpServerResponse::Create(ResponseBody, TEXT("application/json"));
		Response->Code = bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest;
		ApplyCors(Response);
		OnComplete(MoveTemp(Response));
	});

	return true;
}

FString UHephaestusEditorRemoteSubsystem::BodyToString(const TArray<uint8>& Body)
{
	if (Body.Num() == 0)
	{
		return FString();
	}
	TArray<uint8> NullTerminated = Body;
	NullTerminated.Add(0);
	return FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(NullTerminated.GetData())));
}

#endif // WITH_EDITOR
