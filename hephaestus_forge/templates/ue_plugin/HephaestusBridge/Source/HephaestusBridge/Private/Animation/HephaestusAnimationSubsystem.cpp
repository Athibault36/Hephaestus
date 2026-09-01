// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Animation/HephaestusAnimationSubsystem.h"
#include "HephaestusBridge.h"
#include "World/HephaestusWorldSubsystem.h"
#include "Engine/World.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/SkeletalMeshActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimInstance.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "TimerManager.h"
#include "Misc/Paths.h"

namespace
{
struct FHephaestusMoveJob
{
	TWeakObjectPtr<AActor> Actor;
	FVector Start = FVector::ZeroVector;
	FVector End = FVector::ZeroVector;
	float Duration = 1.f;
	float Elapsed = 0.f;
	FTimerHandle Timer;
};

static TArray<TSharedPtr<FHephaestusMoveJob>> GActiveMoveJobs;

static USkeletalMeshComponent* ResolveSkeletalMeshComponent(AActor* Actor)
{
	if (!Actor)
	{
		return nullptr;
	}
	if (ASkeletalMeshActor* SkelActor = Cast<ASkeletalMeshActor>(Actor))
	{
		return SkelActor->GetSkeletalMeshComponent();
	}
	if (ACharacter* Character = Cast<ACharacter>(Actor))
	{
		return Character->GetMesh();
	}
	TArray<USkeletalMeshComponent*> Components;
	Actor->GetComponents<USkeletalMeshComponent>(Components);
	return Components.Num() > 0 ? Components[0] : nullptr;
}
} // namespace

void UHephaestusAnimationSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusAnimationSubsystem: Initialized"));
}

void UHephaestusAnimationSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

UWorld* UHephaestusAnimationSubsystem::ResolveWorld() const
{
	if (const UGameInstance* GI = GetGameInstance())
	{
		return GI->GetWorld();
	}
	return nullptr;
}

UObject* UHephaestusAnimationSubsystem::CreateControlRig(USkeletalMesh* SkeletalMesh, const FHephaestusControlRigDesc& RigDesc)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("CreateControlRig stub — ControlRig integration not linked yet (%s)"), *RigDesc.Name);
	return nullptr;
}

UAnimSequence* UHephaestusAnimationSubsystem::RetargetAnimation(UAnimSequence* Source, USkeletalMesh* Target, UObject* IKRig)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("RetargetAnimation stub"));
	return nullptr;
}

bool UHephaestusAnimationSubsystem::EditSequence(UAnimSequence* Sequence, const TMap<FString, FString>& Edits)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("EditSequence stub"));
	return false;
}

bool UHephaestusAnimationSubsystem::LiveLinkConnect(const FString& SubjectName, const FString& Config)
{
	UE_LOG(LogHephaestusBridge, Warning, TEXT("LiveLinkConnect stub: %s"), *SubjectName);
	return false;
}

AActor* UHephaestusAnimationSubsystem::SpawnSkeletalMeshActor(const FString& MeshPath, const FTransform& Transform)
{
	UWorld* World = ResolveWorld();
	if (!World)
	{
		return nullptr;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ASkeletalMeshActor* Actor = World->SpawnActor<ASkeletalMeshActor>(ASkeletalMeshActor::StaticClass(), Transform, SpawnParams);
	if (!Actor)
	{
		return nullptr;
	}

	FString ResolvedPath = MeshPath;
	if (ResolvedPath.IsEmpty())
	{
		ResolvedPath = TEXT("/Engine/EngineMeshes/SkeletalMesh/SK_Mannequin.SK_Mannequin");
	}

	if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *ResolvedPath))
	{
		if (USkeletalMeshComponent* Comp = Actor->GetSkeletalMeshComponent())
		{
			Comp->SetSkeletalMesh(Mesh);
		}
	}
	else if (!ResolvedPath.Contains(TEXT(".")))
	{
		const FString WithSuffix = ResolvedPath + TEXT(".") + FPaths::GetCleanFilename(ResolvedPath);
		if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *WithSuffix))
		{
			if (USkeletalMeshComponent* Comp = Actor->GetSkeletalMeshComponent())
			{
				Comp->SetSkeletalMesh(Mesh);
			}
		}
		else
		{
			UE_LOG(LogHephaestusBridge, Warning, TEXT("SpawnSkeletalMeshActor: failed to load mesh %s"), *ResolvedPath);
		}
	}
	else
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("SpawnSkeletalMeshActor: failed to load mesh %s"), *ResolvedPath);
	}

	return Actor;
}

bool UHephaestusAnimationSubsystem::PlayAnimSequence(const FString& ActorPath, const FString& AnimPath, bool bLoop)
{
	if (AnimPath.IsEmpty())
	{
		return false;
	}

	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}

	UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	if (!WorldSubsystem)
	{
		return false;
	}

	AActor* Actor = WorldSubsystem->FindActorByPath(ActorPath);
	USkeletalMeshComponent* Comp = ResolveSkeletalMeshComponent(Actor);
	if (!Comp)
	{
		return false;
	}

	UAnimSequence* Anim = LoadObject<UAnimSequence>(nullptr, *AnimPath);
	if (!Anim)
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayAnimSequence: failed to load %s"), *AnimPath);
		return false;
	}

	Comp->SetAnimationMode(EAnimationMode::AnimationSingleNode);
	Comp->PlayAnimation(Anim, bLoop);
	return true;
}

bool UHephaestusAnimationSubsystem::PlayTransformSequence(
	const FString& ActorPath,
	const FVector& TargetLocation,
	float DurationSeconds)
{
	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}

	UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	UWorld* World = ResolveWorld();
	if (!WorldSubsystem || !World)
	{
		return false;
	}

	AActor* Actor = WorldSubsystem->FindActorByPath(ActorPath);
	if (!Actor)
	{
		return false;
	}

	const TSharedPtr<FHephaestusMoveJob> Job = MakeShared<FHephaestusMoveJob>();
	Job->Actor = Actor;
	Job->Start = Actor->GetActorLocation();
	Job->End = TargetLocation;
	Job->Duration = FMath::Max(DurationSeconds, 0.1f);
	GActiveMoveJobs.Add(Job);

	World->GetTimerManager().SetTimer(
		Job->Timer,
		FTimerDelegate::CreateWeakLambda(this, [this, Job, World]()
		{
			if (!Job->Actor.IsValid())
			{
				GActiveMoveJobs.Remove(Job);
				return;
			}
			Job->Elapsed += 0.016f;
			const float Alpha = FMath::Clamp(Job->Elapsed / Job->Duration, 0.f, 1.f);
			Job->Actor->SetActorLocation(FMath::Lerp(Job->Start, Job->End, Alpha));
			if (Alpha >= 1.f)
			{
				World->GetTimerManager().ClearTimer(Job->Timer);
				GActiveMoveJobs.Remove(Job);
			}
		}),
		0.016f,
		true);

	return true;
}

bool UHephaestusAnimationSubsystem::IsActorAnimPlaying(const FString& ActorPath) const
{
	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}

	const UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	if (!WorldSubsystem)
	{
		return false;
	}

	AActor* Actor = WorldSubsystem->FindActorByPath(ActorPath);
	const USkeletalMeshComponent* Comp = ResolveSkeletalMeshComponent(Actor);
	return Comp && Comp->IsPlaying();
}

bool UHephaestusAnimationSubsystem::PlayMontage(const FString& ActorPath, const FString& MontagePath, bool bLoop)
{
	if (MontagePath.IsEmpty())
	{
		return false;
	}

	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}

	UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	if (!WorldSubsystem)
	{
		return false;
	}

	AActor* Actor = WorldSubsystem->FindActorByPath(ActorPath);
	USkeletalMeshComponent* Comp = ResolveSkeletalMeshComponent(Actor);
	if (!Comp)
	{
		return false;
	}

	UAnimMontage* Montage = LoadObject<UAnimMontage>(nullptr, *MontagePath);
	if (!Montage)
	{
		UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayMontage: failed to load %s"), *MontagePath);
		return false;
	}

	UAnimInstance* AnimInst = Comp->GetAnimInstance();
	if (!AnimInst)
	{
		Comp->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		AnimInst = Comp->GetAnimInstance();
	}
	if (!AnimInst)
	{
		return false;
	}

	AnimInst->Montage_Play(Montage, 1.f, EMontagePlayReturnType::MontageLength, 0.f, bLoop);
	return true;
}

bool UHephaestusAnimationSubsystem::StopAnimation(const FString& ActorPath)
{
	UGameInstance* GI = GetGameInstance();
	if (!GI)
	{
		return false;
	}
	UHephaestusWorldSubsystem* WorldSubsystem = GI->GetSubsystem<UHephaestusWorldSubsystem>();
	if (!WorldSubsystem)
	{
		return false;
	}
	AActor* Actor = WorldSubsystem->FindActorByPath(ActorPath);
	USkeletalMeshComponent* Comp = ResolveSkeletalMeshComponent(Actor);
	if (!Comp)
	{
		return false;
	}
	Comp->Stop();
	if (UAnimInstance* AnimInst = Comp->GetAnimInstance())
	{
		AnimInst->StopAllMontages(0.f);
	}
	return true;
}
