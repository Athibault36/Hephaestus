// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

#include "Blueprints/HephaestusBlueprintSubsystem.h"
#include "KismetCompilerModule.h"
#include "BlueprintEditorModule.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_FunctionResult.h"
#include "K2Node_CallFunction.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"

#define LOCTEXT_NAMESPACE "HephaestusBlueprints"

void UHephaestusBlueprintSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Initialized"));
}

void UHephaestusBlueprintSubsystem::Deinitialize()
{
    Super::Deinitialize();
    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Deinitialized"));
}

bool UHephaestusBlueprintSubsystem::CompileBlueprint(UBlueprint* Blueprint)
{
    if (!Blueprint)
    {
        return false;
    }

    // Use KismetCompiler to compile
    FKismetCompilerContext CompilerContext(Blueprint, EBlueprintCompileOptions::None, nullptr);
    CompilerContext.Compile();

    bool bSuccess = CompilerContext.GetResults().NumErrors == 0;
    if (bSuccess)
    {
        UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Compiled blueprint %s"), *Blueprint->GetName());
    }
    else
    {
        UE_LOG(LogHephaestusBridge, Error, TEXT("HephaestusBlueprintSubsystem: Failed to compile blueprint %s (%d errors)"),
            *Blueprint->GetName(), CompilerContext.GetResults().NumErrors);
    }

    return bSuccess;
}

bool UHephaestusBlueprintSubsystem::AddFunctionToBlueprint(UBlueprint* Blueprint, const FHephaestusFunctionDesc& FunctionDesc)
{
    if (!Blueprint || !Blueprint->SkeletonGeneratedClass)
    {
        return false;
    }

    // Create function graph
    UEdGraph* FunctionGraph = FBlueprintEditorUtils::CreateNewGraph(
        Blueprint,
        FName(*FunctionDesc.Name),
        UEdGraph::StaticClass(),
        UEdGraphSchema_K2::StaticClass()
    );

    if (!FunctionGraph)
    {
        return false;
    }

    // Set as function graph
    FunctionGraph->bAllowDeletion = true;

    // Create entry node
    UK2Node_FunctionEntry* EntryNode = NewObject<UK2Node_FunctionEntry>(FunctionGraph);
    EntryNode->FunctionReference.SetExternalMember(FName(*FunctionDesc.Name), Blueprint->GeneratedClass);
    EntryNode->AllocateDefaultPins();
    FunctionGraph->AddNode(EntryNode, true, true);

    // Add parameter pins based on FunctionDesc.Parameters
    for (const auto& Pair : FunctionDesc.Parameters)
    {
        // Create input pins on entry node
        // This requires parsing the type string and creating appropriate pins
    }

    // Create result node if return type is not void
    if (FunctionDesc.ReturnType != TEXT("void"))
    {
        UK2Node_FunctionResult* ResultNode = NewObject<UK2Node_FunctionResult>(FunctionGraph);
        ResultNode->FunctionReference.SetExternalMember(FName(*FunctionDesc.Name), Blueprint->GeneratedClass);
        ResultNode->AllocateDefaultPins();
        FunctionGraph->AddNode(ResultNode, true, true);
    }

    // Add graph to blueprint
    Blueprint->FunctionGraphs.Add(FunctionGraph);
    Blueprint->Refresh();

    UE_LOG(LogHephaestusBridge, Log, TEXT("HephaestusBlueprintSubsystem: Added function %s to blueprint %s"),
        *FunctionDesc.Name, *Blueprint->GetName());

    return true;
}

bool UHephaestusBlueprintSubsystem::SetBlueprintProperty(UBlueprint* Blueprint, const FString& PropertyName, const FString& Value)
{
    if (!Blueprint)
    {
        return false;
    }

    // Find property in blueprint
    UProperty* Property = Blueprint->GetClass()->FindPropertyByName(FName(*PropertyName));
    if (!Property)
    {
        UE_LOG(LogHephaestusBridge, Warning, TEXT("HephaestusBlueprintSubsystem: Property not found: %s"), *PropertyName);
        return false;
    }

    // Set value (simplified - would need full type parsing)
    void* ValuePtr = Property->ContainerPtrToValuePtr<void>(Blueprint);
    if (FNumericProperty* NumericProp = CastField<FNumericProperty>(Property))
    {
        if (FIntProperty* IntProp = CastField<FIntProperty>(Property))
        {
            *static_cast<int32*>(ValuePtr) = FCString::Atoi(*Value);
        }
        else if (FFloatProperty* FloatProp = CastField<FFloatProperty>(Property))
        {
            *static_cast<float*>(ValuePtr) = FCString::Atof(*Value);
        }
    }
    else if (FStrProperty* StrProp = CastField<FStrProperty>(Property))
    {
        *static_cast<FString*>(ValuePtr) = Value;
    }
    else if (FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
    {
        *static_cast<bool*>(ValuePtr) = (Value == TEXT("true") || Value == TEXT("1"));
    }

    Blueprint->PostEditChange();
    return true;
}

FHephaestusDiffResult UHephaestusBlueprintSubsystem::DiffBlueprints(UBlueprint* BlueprintA, UBlueprint* BlueprintB)
{
    FHephaestusDiffResult Result;

    if (!BlueprintA || !BlueprintB)
    {
        return Result;
    }

    // Compare function graphs
    TSet<FString> GraphNamesA, GraphNamesB;
    for (UEdGraph* Graph : BlueprintA->FunctionGraphs)
    {
        GraphNamesA.Add(Graph->GetName());
    }
    for (UEdGraph* Graph : BlueprintB->FunctionGraphs)
    {
        GraphNamesB.Add(Graph->GetName());
    }

    // Find added/removed functions
    for (const FString& Name : GraphNamesA)
    {
        if (!GraphNamesB.Contains(Name))
        {
            Result.RemovedFunctions.Add(Name);
        }
    }
    for (const FString& Name : GraphNamesB)
    {
        if (!GraphNamesA.Contains(Name))
        {
            Result.AddedFunctions.Add(Name);
        }
    }

    // For common graphs, compare nodes
    for (const FString& Name : GraphNamesA)
    {
        if (GraphNamesB.Contains(Name))
        {
            UEdGraph* GraphA = nullptr;
            UEdGraph* GraphB = nullptr;

            for (UEdGraph* G : BlueprintA->FunctionGraphs)
            {
                if (G->GetName() == Name) { GraphA = G; break; }
            }
            for (UEdGraph* G : BlueprintB->FunctionGraphs)
            {
                if (G->GetName() == Name) { GraphB = G; break; }
            }

            if (GraphA && GraphB)
            {
                // Compare nodes (simplified)
                TSet<FString> NodesA, NodesB;
                for (UEdGraphNode* Node : GraphA->Nodes)
                {
                    NodesA.Add(Node->GetName());
                }
                for (UEdGraphNode* Node : GraphB->Nodes)
                {
                    NodesB.Add(Node->GetName());
                }

                for (const FString& NodeName : NodesA)
                {
                    if (!NodesB.Contains(NodeName))
                    {
                        Result.RemovedNodes.Add(FString::Printf(TEXT("%s::%s"), *Name, *NodeName));
                    }
                    else
                    {
                        // Could do deeper comparison here
                        Result.ModifiedNodes.Add(FString::Printf(TEXT("%s::%s"), *Name, *NodeName));
                    }
                }
                for (const FString& NodeName : NodesB)
                {
                    if (!NodesA.Contains(NodeName))
                    {
                        Result.AddedNodes.Add(FString::Printf(TEXT("%s::%s"), *Name, *NodeName));
                    }
                }
            }
        }
    }

    Result.bIdentical = (Result.AddedNodes.Num() == 0 && Result.RemovedNodes.Num() == 0 &&
                         Result.ModifiedNodes.Num() == 0 && Result.AddedFunctions.Num() == 0 &&
                         Result.RemovedFunctions.Num() == 0);

    return Result;
}

#undef LOCTEXT_NAMESPACE