// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Http/HephaestusHttpServer.h"
#include "Command/HephaestusCommandHandler.h"
#include "HephaestusBridge.h"

#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "HttpPath.h"
#include "Engine/GameInstance.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Misc/CString.h"

#define LOCTEXT_NAMESPACE "HephaestusHttp"

uint32 UHephaestusHttpServer::ResolvePort()
{
    const FString EnvPort = FPlatformMisc::GetEnvironmentVariable(TEXT("HEPHAESTUS_UE_PORT"));
    if (!EnvPort.IsEmpty())
    {
        const int32 Parsed = FCString::Atoi(*EnvPort);
        if (Parsed > 0 && Parsed < 65536)
        {
            return static_cast<uint32>(Parsed);
        }
    }
    return 8099;
}

void UHephaestusHttpServer::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    // Ensure the command handler exists before we route to it.
    Collection.InitializeDependency(UHephaestusCommandHandler::StaticClass());
    StartServer(ResolvePort());
}

void UHephaestusHttpServer::Deinitialize()
{
    StopServer();
    Super::Deinitialize();
}

void UHephaestusHttpServer::StartServer(uint32 InPort)
{
    FHttpServerModule& HttpServerModule = FHttpServerModule::Get();
    Router = HttpServerModule.GetHttpRouter(InPort);
    if (!Router.IsValid())
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusHttpServer: failed to get router on port %u"), InPort);
        return;
    }

    RouteHandles.Add(Router->BindRoute(
        FHttpPath(TEXT("/health")), EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UHephaestusHttpServer::HandleHealth)));
    RouteHandles.Add(Router->BindRoute(
        FHttpPath(TEXT("/commands")), EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UHephaestusHttpServer::HandleCommands)));
    RouteHandles.Add(Router->BindRoute(
        FHttpPath(TEXT("/command")), EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UHephaestusHttpServer::HandleCommand)));
    RouteHandles.Add(Router->BindRoute(
        FHttpPath(TEXT("/batch")), EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UHephaestusHttpServer::HandleBatch)));

    HttpServerModule.StartAllListeners();
    BoundPort = InPort;
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusHttpServer: listening on http://127.0.0.1:%u"), InPort);
}

void UHephaestusHttpServer::StopServer()
{
    if (Router.IsValid())
    {
        for (const FHttpRouteHandle& Handle : RouteHandles)
        {
            if (Handle.IsValid())
            {
                Router->UnbindRoute(Handle);
            }
        }
    }
    RouteHandles.Reset();
    Router.Reset();
    BoundPort = 0;
}

UHephaestusCommandHandler* UHephaestusHttpServer::GetCommandHandler() const
{
    if (UGameInstance* GameInstance = GetGameInstance())
    {
        return GameInstance->GetSubsystem<UHephaestusCommandHandler>();
    }
    return nullptr;
}

FString UHephaestusHttpServer::RequestBodyToString(const FHttpServerRequest& Request)
{
    if (Request.Body.Num() == 0)
    {
        return FString();
    }
    FUTF8ToTCHAR Converter(reinterpret_cast<const ANSICHAR*>(Request.Body.GetData()), Request.Body.Num());
    return FString(Converter.Length(), Converter.Get());
}

FString UHephaestusHttpServer::ResultToJson(const FHephaestusCommandResult& Result)
{
    const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("success"), Result.bSuccess);
    Root->SetStringField(TEXT("error_message"), Result.ErrorMessage);
    Root->SetStringField(TEXT("result_json"), Result.ResultJSON.IsEmpty() ? TEXT("{}") : Result.ResultJSON);
    Root->SetNumberField(TEXT("execution_time_ms"), Result.ExecutionTimeMs);
    Root->SetStringField(TEXT("command_id"), Result.CommandID);

    TArray<TSharedPtr<FJsonValue>> Actors;
    for (const FString& Actor : Result.ActorReferences)
    {
        Actors.Add(MakeShared<FJsonValueString>(Actor));
    }
    Root->SetArrayField(TEXT("actor_references"), Actors);

    TArray<TSharedPtr<FJsonValue>> Assets;
    for (const FString& Asset : Result.AssetReferences)
    {
        Assets.Add(MakeShared<FJsonValueString>(Asset));
    }
    Root->SetArrayField(TEXT("asset_references"), Assets);

    FString Out;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Root, Writer);
    return Out;
}

void UHephaestusHttpServer::RespondJson(const FHttpResultCallback& OnComplete, const FString& Json, int32 StatusCode)
{
    TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(Json, TEXT("application/json"));
    Response->Code = static_cast<EHttpServerResponseCodes>(StatusCode);
    OnComplete(MoveTemp(Response));
}

bool UHephaestusHttpServer::HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    UHephaestusCommandHandler* Handler = GetCommandHandler();
    const int32 NumCommands = Handler ? Handler->GetAvailableCommands().Num() : 0;
    RespondJson(OnComplete, FString::Printf(TEXT("{\"status\":\"ok\",\"commands\":%d}"), NumCommands));
    return true;
}

bool UHephaestusHttpServer::HandleCommands(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    UHephaestusCommandHandler* Handler = GetCommandHandler();
    TArray<TSharedPtr<FJsonValue>> Commands;
    if (Handler)
    {
        for (const FString& Name : Handler->GetAvailableCommands())
        {
            Commands.Add(MakeShared<FJsonValueString>(Name));
        }
    }
    const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetArrayField(TEXT("commands"), Commands);
    FString Out;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Root, Writer);
    RespondJson(OnComplete, Out);
    return true;
}

bool UHephaestusHttpServer::HandleCommand(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    UHephaestusCommandHandler* Handler = GetCommandHandler();
    if (!Handler)
    {
        RespondJson(OnComplete, TEXT("{\"success\":false,\"error_message\":\"command handler unavailable\"}"), 503);
        return true;
    }

    const FString Body = RequestBodyToString(Request);
    // HTTP handlers run on the game thread, so this synchronous call is safe.
    const FHephaestusCommandResult Result = Handler->ExecuteCommand(Body);
    RespondJson(OnComplete, ResultToJson(Result), Result.bSuccess ? 200 : 200);
    return true;
}

bool UHephaestusHttpServer::HandleBatch(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    UHephaestusCommandHandler* Handler = GetCommandHandler();
    if (!Handler)
    {
        RespondJson(OnComplete, TEXT("{\"results\":[]}"), 503);
        return true;
    }

    const FString Body = RequestBodyToString(Request);
    TSharedPtr<FJsonObject> Parsed;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Body);

    TArray<TSharedPtr<FJsonValue>> Results;
    const TArray<TSharedPtr<FJsonValue>>* Commands = nullptr;
    if (FJsonSerializer::Deserialize(Reader, Parsed) && Parsed.IsValid() &&
        Parsed->TryGetArrayField(TEXT("commands"), Commands) && Commands)
    {
        for (const TSharedPtr<FJsonValue>& Entry : *Commands)
        {
            const TSharedPtr<FJsonObject>* EnvelopeObj = nullptr;
            if (!Entry->TryGetObject(EnvelopeObj) || !EnvelopeObj)
            {
                continue;
            }
            FString EnvelopeStr;
            const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&EnvelopeStr);
            FJsonSerializer::Serialize(EnvelopeObj->ToSharedRef(), Writer);

            const FHephaestusCommandResult Result = Handler->ExecuteCommand(EnvelopeStr);
            TSharedPtr<FJsonObject> ResultObj;
            const TSharedRef<TJsonReader<>> ResultReader = TJsonReaderFactory<>::Create(ResultToJson(Result));
            if (FJsonSerializer::Deserialize(ResultReader, ResultObj) && ResultObj.IsValid())
            {
                Results.Add(MakeShared<FJsonValueObject>(ResultObj));
            }
        }
    }

    const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetArrayField(TEXT("results"), Results);
    FString Out;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Root, Writer);
    RespondJson(OnComplete, Out);
    return true;
}

#undef LOCTEXT_NAMESPACE
