// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Animation/HephaestusAnimationSubsystem.h"
#include "HephaestusBridge.h"
#include "World/HephaestusWorldSubsystem.h"
#include "Engine/World.h"
#include "Animation/AnimInstance.h"
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
#include "UObject/Package.h"

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

static FString InferAnimBlueprintPath(const FString& MeshPath)
{
	if (MeshPath.IsEmpty())
	{
		return FString();
	}
	FString PackagePath = MeshPath;
	int32 DotIndex = INDEX_NONE;
	if (PackagePath.FindLastChar(TEXT('.'), DotIndex))
	{
		PackagePath = PackagePath.Left(DotIndex);
	}
	const FString BaseName = FPaths::GetBaseFilename(PackagePath);
	const FString Dir = FPackageName::GetLongPackagePath(PackagePath);
	const TArray<FString> Candidates = {
		FString::Printf(TEXT("%s/%s_ABP.%s_ABP"), *Dir, *BaseName, *BaseName),
		FString::Printf(TEXT("%s/ABP_%s.ABP_%s"), *Dir, *BaseName, *BaseName),
		FString::Printf(TEXT("%s/%s_AnimBP.%s_AnimBP"), *Dir, *BaseName, *BaseName),
		FString::Printf(TEXT("%s/%s_BP.%s_BP"), *Dir, *BaseName, *BaseName),
	};
	for (const FString& Candidate : Candidates)
	{
		if (LoadClass<UAnimInstance>(nullptr, *Candidate))
		{
			return Candidate;
		}
	}
	return FString();
}

static void ApplyAnimBlueprint(USkeletalMeshComponent* Comp, const FString& AnimBlueprintPath)
{
	if (!Comp || AnimBlueprintPath.IsEmpty())
	{
		return;
	}
	if (UClass* AnimClass = LoadClass<UAnimInstance>(nullptr, *AnimBlueprintPath))
	{
		Comp->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		Comp->SetAnimInstanceClass(AnimClass);
	}
}

AActor* UHephaestusAnimationSubsystem::SpawnSkeletalMeshActor(
	const FString& MeshPath,
	const FTransform& Transform,
	const FString& AnimBlueprintPath)
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
			FString AnimBP = AnimBlueprintPath;
			if (AnimBP.IsEmpty())
			{
				AnimBP = InferAnimBlueprintPath(ResolvedPath);
			}
			ApplyAnimBlueprint(Comp, AnimBP);
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
				FString AnimBP = AnimBlueprintPath;
				if (AnimBP.IsEmpty())
				{
					AnimBP = InferAnimBlueprintPath(WithSuffix);
				}
				ApplyAnimBlueprint(Comp, AnimBP);
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

static TArray<FString> LocomotionCandidates(const FString& Mode)
{
	const FString ModeLower = Mode.ToLower();
	if (ModeLower.Contains(TEXT("run")))
	{
		return {
			TEXT("/Game/Characters/Mannequins/Animations/Manny/MM_Run_InPlace.MM_Run_InPlace"),
			TEXT("/Game/Characters/Mannequins/Animations/Quinn/MF_Run_InPlace.MF_Run_InPlace"),
			TEXT("/Game/ThirdPerson/Animations/ThirdPersonRun.ThirdPersonRun"),
		};
	}
	if (ModeLower.Contains(TEXT("walk")) || ModeLower.Contains(TEXT("jog")))
	{
		return {
			TEXT("/Game/Characters/Mannequins/Animations/Manny/MM_Walk_InPlace.MM_Walk_InPlace"),
			TEXT("/Game/Characters/Mannequins/Animations/Quinn/MF_Walk_InPlace.MF_Walk_InPlace"),
			TEXT("/Game/ThirdPerson/Animations/ThirdPersonWalk.ThirdPersonWalk"),
		};
	}
	return {
		TEXT("/Game/Characters/Mannequins/Animations/Manny/MM_Idle.MM_Idle"),
		TEXT("/Game/Characters/Mannequins/Animations/Quinn/MF_Idle.MF_Idle"),
		TEXT("/Game/ThirdPerson/Animations/ThirdPersonIdle.ThirdPersonIdle"),
	};
}

AActor* UHephaestusAnimationSubsystem::SpawnLocomotionCharacter(
	const FString& MeshPath,
	const FTransform& Transform,
	const FString& AnimBlueprintPath)
{
	UWorld* World = ResolveWorld();
	if (!World)
	{
		return nullptr;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACharacter* Character = World->SpawnActor<ACharacter>(ACharacter::StaticClass(), Transform, SpawnParams);
	if (!Character)
	{
		return nullptr;
	}

	FString ResolvedPath = MeshPath;
	if (ResolvedPath.IsEmpty())
	{
		ResolvedPath = TEXT("/Engine/EngineMeshes/SkeletalMesh/SK_Mannequin.SK_Mannequin");
	}

	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *ResolvedPath);
	if (!Mesh && !ResolvedPath.Contains(TEXT(".")))
	{
		const FString WithSuffix = ResolvedPath + TEXT(".") + FPaths::GetCleanFilename(ResolvedPath);
		Mesh = LoadObject<USkeletalMesh>(nullptr, *WithSuffix);
	}

	if (USkeletalMeshComponent* Comp = Character->GetMesh())
	{
		if (Mesh)
		{
			Comp->SetSkeletalMesh(Mesh);
		}
		Comp->SetRelativeLocation(FVector(0.f, 0.f, -90.f));
		Comp->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
		FString AnimBP = AnimBlueprintPath;
		if (AnimBP.IsEmpty() && Mesh)
		{
			AnimBP = InferAnimBlueprintPath(ResolvedPath);
		}
		ApplyAnimBlueprint(Comp, AnimBP);
	}

	return Character;
}

bool UHephaestusAnimationSubsystem::PlayLocomotionFallback(const FString& ActorPath, const FString& Mode, bool bLoop)
{
	for (const FString& Candidate : LocomotionCandidates(Mode))
	{
		if (PlayAnimSequence(ActorPath, Candidate, bLoop))
		{
			UE_LOG(LogHephaestusBridge, Log, TEXT("PlayLocomotionFallback: %s on %s"), *Candidate, *ActorPath);
			return true;
		}
	}
	UE_LOG(LogHephaestusBridge, Warning, TEXT("PlayLocomotionFallback: no fallback anim loaded for mode %s"), *Mode);
	return false;
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
