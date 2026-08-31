// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

using UnrealBuildTool;
using System;
using System.Collections.Generic;

public class HephaestusBridge : ModuleRules
{
    // Default is a first-compile-friendly set. Set HEPHAESTUS_FULL_BUILD=1 to also
    // require PixelStreaming / WebRTC / OpenCV / ThirdParty LLM stacks.
    private static bool WantFullOptionalStack()
    {
        string Flag = Environment.GetEnvironmentVariable("HEPHAESTUS_FULL_BUILD");
        return Flag == "1" || string.Equals(Flag, "true", StringComparison.OrdinalIgnoreCase);
    }

    public HephaestusBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicIncludePaths.AddRange(
            new string[] {
                ModuleDirectory,
                ModuleDirectory + "/Public",
                ModuleDirectory + "/Public/Vision",
                ModuleDirectory + "/Public/Command",
                ModuleDirectory + "/Public/Http",
                ModuleDirectory + "/Public/World",
                ModuleDirectory + "/Public/Assets",
                ModuleDirectory + "/Public/Blueprints",
                ModuleDirectory + "/Public/Rendering",
                ModuleDirectory + "/Public/PCG",
                ModuleDirectory + "/Public/Animation",
                ModuleDirectory + "/Public/Audio",
            }
        );

        PrivateIncludePaths.AddRange(
            new string[] {
                ModuleDirectory + "/Private",
                ModuleDirectory + "/Private/Vision",
                ModuleDirectory + "/Private/Command",
                ModuleDirectory + "/Private/Http",
                ModuleDirectory + "/Private/World",
                ModuleDirectory + "/Private/Assets",
                ModuleDirectory + "/Private/Blueprints",
                ModuleDirectory + "/Private/Rendering",
                ModuleDirectory + "/Private/PCG",
                ModuleDirectory + "/Private/Animation",
                ModuleDirectory + "/Private/Audio",
            }
        );

        // Core + HTTP bridge (required for M1 health/command/frame)
        PublicDependencyModuleNames.AddRange(
            new string[] {
                "Core",
                "CoreUObject",
                "Engine",
                "InputCore",
                "Slate",
                "SlateCore",
                "Renderer",
                "RenderCore",
                "RHI",
                "Projects",
                "GameplayTags",
                "GameplayTasks",
                "AIModule",
                "NavigationSystem",
                "AnimGraphRuntime",
                "ControlRig",
                "LiveLinkInterface",
                "PCG",
                "Niagara",
                "NiagaraCore",
                "AssetRegistry",
                "Json",
                "JsonUtilities",
                "HTTP",
                "HTTPServer",
                "Sockets",
                "Networking",
                "ImageWrapper",
                "ImageWriteQueue",
                "MediaAssets",
                "MediaUtils",
                "DeveloperSettings",
                "AudioMixer",
            }
        );

        // Editor-only modules — never link into a cooked game target.
        if (Target.bBuildEditor)
        {
            PublicDependencyModuleNames.AddRange(
                new string[] {
                    "UnrealEd",
                    "AssetTools",
                    "BlueprintGraph",
                    "KismetCompiler",
                    "GraphEditor",
                    "PropertyEditor",
                    "ContentBrowser",
                    "EditorStyle",
                    "ToolMenus",
                    "WorkspaceMenuStructure",
                }
            );
        }

        PrivateDependencyModuleNames.AddRange(
            new string[] {
                "ApplicationCore",
                "CinematicCamera",
                "LevelSequence",
                "MovieScene",
                "MovieSceneTracks",
                "RenderGraph",
                "GlobalShader",
                "StaticMeshDescription",
                "MeshDescription",
                "Landscape",
                "Foliage",
            }
        );

        // Optional heavy plugins — off unless HEPHAESTUS_FULL_BUILD=1
        if (WantFullOptionalStack())
        {
            PublicDependencyModuleNames.AddRange(new string[] { "PixelStreaming", "WebRTC", "OpenCV" });
            PublicDefinitions.Add("HEPHAESTUS_WITH_PIXEL_STREAMING=1");
        }
        else
        {
            PublicDefinitions.Add("HEPHAESTUS_WITH_PIXEL_STREAMING=0");
        }

        // MetaSound / Quartz are useful but often missing; keep soft for first compile.
        if (WantFullOptionalStack())
        {
            PublicDependencyModuleNames.AddRange(new string[] { "MetaSoundEngine", "QuartzCore", "Synthesis" });
            PublicDefinitions.Add("HEPHAESTUS_WITH_METASOUND=1");
        }
        else
        {
            PublicDefinitions.Add("HEPHAESTUS_WITH_METASOUND=0");
        }

        // Third-party: only enable when the ThirdParty tree exists (never force =1).
        PublicDefinitions.Add("WITH_TRT_LLM=0");
        PublicDefinitions.Add("WITH_LLAMA_CPP=0");
        PublicDefinitions.Add("WITH_GRPC=0");
        PublicDefinitions.Add("WITH_OPENCV=0");
        PublicDefinitions.Add("WITH_LLM_INFERENCE=0");
        SetupLLMInference(Target);
        SetupOpenCV(Target);
        SetupGRPC(Target);

        if (Target.Platform == UnrealTargetPlatform.Win64)
        {
            PublicSystemLibraries.AddRange(new string[] { "ws2_32", "winmm", "bcrypt", "crypt32" });
        }
        else if (Target.Platform == UnrealTargetPlatform.Linux)
        {
            PublicSystemLibraries.AddRange(new string[] { "pthread", "dl", "rt" });
        }
        else if (Target.Platform == UnrealTargetPlatform.Mac)
        {
            PublicFrameworks.AddRange(new string[] { "Cocoa", "IOKit", "CoreVideo", "CoreAudio", "AudioToolbox" });
        }

        bUseUnityBuild = true;
        bUsePCHFiles = true;
        MinFilesUsingUnityBuild = 4;
        CppStandard = CppStandardVersion.Cpp20;

        PublicDefinitions.AddRange(
            new string[] {
                "HEPHAESTUS_BRIDGE_API=DLLEXPORT",
                "WITH_HEPHAESTUS_VISION=1",
                "WITH_HEPHAESTUS_COMMAND=1",
                "WITH_HEPHAESTUS_WORLD=1",
                "WITH_HEPHAESTUS_ASSETS=1",
                "WITH_HEPHAESTUS_BLUEPRINTS=1",
                "WITH_HEPHAESTUS_RENDERING=1",
                "WITH_HEPHAESTUS_PCG=1",
                "WITH_HEPHAESTUS_ANIMATION=1",
                "WITH_HEPHAESTUS_AUDIO=1",
            }
        );
    }

    private void SetupLLMInference(ReadOnlyTargetRules Target)
    {
        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));

        string TRTPath = System.IO.Path.Combine(ThirdPartyPath, "TensorRT-LLM");
        if (System.IO.Directory.Exists(TRTPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(TRTPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(TRTPath, "lib", Target.Platform.ToString()));
            if (Target.Platform == UnrealTargetPlatform.Win64)
            {
                PublicAdditionalLibraries.Add("tensorrt_llm.lib");
                PublicAdditionalLibraries.Add("nvinfer.lib");
            }
            else
            {
                PublicAdditionalLibraries.Add("tensorrt_llm");
                PublicAdditionalLibraries.Add("nvinfer");
            }
            PublicDefinitions.Add("WITH_TRT_LLM=1");
            PublicDefinitions.Add("WITH_LLM_INFERENCE=1");
        }

        string LlamaPath = System.IO.Path.Combine(ThirdPartyPath, "llama.cpp");
        if (System.IO.Directory.Exists(LlamaPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(LlamaPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(LlamaPath, "build", Target.Platform.ToString()));
            if (Target.Platform == UnrealTargetPlatform.Win64)
            {
                PublicAdditionalLibraries.Add("llama.lib");
                PublicAdditionalLibraries.Add("ggml.lib");
            }
            else
            {
                PublicAdditionalLibraries.Add("llama");
                PublicAdditionalLibraries.Add("ggml");
            }
            PublicDefinitions.Add("WITH_LLAMA_CPP=1");
            PublicDefinitions.Add("WITH_LLM_INFERENCE=1");
        }
    }

    private void SetupOpenCV(ReadOnlyTargetRules Target)
    {
        if (!WantFullOptionalStack())
        {
            return;
        }

        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));
        string OpenCVPath = System.IO.Path.Combine(ThirdPartyPath, "opencv");
        if (!System.IO.Directory.Exists(OpenCVPath))
        {
            return;
        }

        PublicIncludePaths.Add(System.IO.Path.Combine(OpenCVPath, "include"));
        PublicLibraryPaths.Add(System.IO.Path.Combine(OpenCVPath, "lib", Target.Platform.ToString()));
        if (Target.Platform == UnrealTargetPlatform.Win64)
            PublicAdditionalLibraries.Add("opencv_world4100.lib");
        else
            PublicAdditionalLibraries.Add("opencv_world4100");
        PublicDefinitions.Add("WITH_OPENCV=1");
    }

    private void SetupGRPC(ReadOnlyTargetRules Target)
    {
        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));
        string GRPCPath = System.IO.Path.Combine(ThirdPartyPath, "grpc");
        if (!System.IO.Directory.Exists(GRPCPath))
        {
            return;
        }

        PublicIncludePaths.Add(System.IO.Path.Combine(GRPCPath, "include"));
        PublicLibraryPaths.Add(System.IO.Path.Combine(GRPCPath, "lib", Target.Platform.ToString()));
        foreach (string lib in new string[] { "grpc", "grpcpp", "protobuf" })
        {
            if (Target.Platform == UnrealTargetPlatform.Win64)
                PublicAdditionalLibraries.Add(lib + ".lib");
            else
                PublicAdditionalLibraries.Add(lib);
        }
        PublicDefinitions.Add("WITH_GRPC=1");
    }
}
