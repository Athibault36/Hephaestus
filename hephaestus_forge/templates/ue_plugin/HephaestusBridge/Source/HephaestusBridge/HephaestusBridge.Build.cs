// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

using UnrealBuildTool;
using System.Collections.Generic;

public class HephaestusBridge : ModuleRules
{
    public HephaestusBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        // --- Public Include Paths ---
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

        // --- Private Include Paths ---
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

        // --- Core UE Dependencies ---
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
                "NiagaraShader",
                "MetaSoundEngine",
                "QuartzCore",
                "Synthesis",
                "AudioMixer",
                "AssetRegistry",
                "AssetTools",
                "UnrealEd",
                "BlueprintGraph",
                "KismetCompiler",
                "GraphEditor",
                "PropertyEditor",
                "ContentBrowser",
                "EditorStyle",
                "ToolMenus",
                "WorkspaceMenuStructure",
                "DeveloperSettings",
                "Json",
                "JsonUtilities",
                "HTTP",
                "HTTPServer",
                "Sockets",
                "Networking",
                "PacketHandler",
                "NetCore",
                "OnlineSubsystem",
                "OnlineSubsystemUtils",
                "PythonScriptPlugin",
                "ImageWrapper",
                "ImageWriteQueue",
                "MediaAssets",
                "MediaUtils",
                "PixelStreaming",
                "WebRTC",
                "OpenCV",
            }
        );

        // --- Private Dependencies ---
        PrivateDependencyModuleNames.AddRange(
            new string[] {
                "ApplicationCore",
                "CinematicCamera",
                "LevelSequence",
                "MovieScene",
                "MovieSceneTracks",
                "Sequencer",
                "GeometryCollectionEngine",
                "GeometryCollectionSimulationCore",
                "Chaos",
                "ChaosSolverEngine",
                "ChaosNiagara",
                "FieldSystemEngine",
                "RenderGraph",
                "RDG",
                "GlobalShader",
                "ShaderCore",
                "PipelineStateCache",
                "StaticMeshDescription",
                "MeshDescription",
                "MeshUtilities",
                "MeshReductionInterface",
                "SkeletalMeshReduction",
                "Landscape",
                "Foliage",
                "InstancedFoliage",
                "ProceduralMeshComponent",
                "CustomMeshComponent",
            }
        );

        // --- ThirdParty: llama.cpp / TensorRT-LLM ---
        SetupLLMInference(Target);

        // --- ThirdParty: WebRTC (already in UE via PixelStreaming) ---
        // WebRTC is included via PixelStreaming module dependency

        // --- ThirdParty: OpenCV ---
        SetupOpenCV(Target);

        // --- ThirdParty: gRPC / Protobuf ---
        SetupGRPC(Target);

        // --- Platform Specific ---
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

        // --- Build Configuration ---
        bUseUnityBuild = true;
        bUsePCHFiles = true;
        MinFilesUsingUnityBuild = 4;

        // C++20 for modern features
        CppStandard = CppStandardVersion.Cpp20;

        // Optimization
        if (Target.Configuration == UnrealTargetConfiguration.Shipping || Target.Configuration == UnrealTargetConfiguration.Test)
        {
            bCompileWithOptimization = true;
            bUseFastMalloc = true;
        }

        // Enable modules for hot reload
        bAllowHotReload = true;

        // --- Definitions ---
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
                "WITH_LLM_INFERENCE=1",
                "WITH_TRT_LLM=1",
                "WITH_LLAMA_CPP=1",
                "WITH_GRPC=1",
                "WITH_OPENCV=1",
            }
        );
    }

    private void SetupLLMInference(ReadOnlyTargetRules Target)
    {
        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));

        // TensorRT-LLM
        string TRTPath = System.IO.Path.Combine(ThirdPartyPath, "TensorRT-LLM");
        if (System.IO.Directory.Exists(TRTPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(TRTPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(TRTPath, "lib", Target.Platform.ToString()));

            if (Target.Platform == UnrealTargetPlatform.Win64)
            {
                PublicAdditionalLibraries.Add("tensorrt_llm.lib");
                PublicAdditionalLibraries.Add("nvinfer.lib");
                PublicAdditionalLibraries.Add("nvonnxparser.lib");
                PublicDefinitions.Add("WITH_TRT_LLM=1");
            }
            else if (Target.Platform == UnrealTargetPlatform.Linux)
            {
                PublicAdditionalLibraries.Add("tensorrt_llm");
                PublicAdditionalLibraries.Add("nvinfer");
                PublicAdditionalLibraries.Add("nvonnxparser");
                PublicDefinitions.Add("WITH_TRT_LLM=1");
            }

            // CUDA Runtime
            string CudaPath = System.Environment.GetEnvironmentVariable("CUDA_PATH") ?? "/usr/local/cuda";
            PublicIncludePaths.Add(System.IO.Path.Combine(CudaPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(CudaPath, "lib64"));
            PublicAdditionalLibraries.AddRange(new string[] { "cudart", "cublas", "curand" });
        }

        // llama.cpp (fallback / CPU offload)
        string LlamaPath = System.IO.Path.Combine(ThirdPartyPath, "llama.cpp");
        if (System.IO.Directory.Exists(LlamaPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(LlamaPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(LlamaPath, "build", Target.Platform.ToString()));

            if (Target.Platform == UnrealTargetPlatform.Win64)
            {
                PublicAdditionalLibraries.Add("llama.lib");
                PublicAdditionalLibraries.Add("ggml.lib");
                PublicAdditionalLibraries.Add("ggml-base.lib");
                PublicAdditionalLibraries.Add("ggml-cpu.lib");
                PublicAdditionalLibraries.Add("ggml-cuda.lib");
                PublicAdditionalLibraries.Add("ggml-metal.lib");
            }
            else
            {
                PublicAdditionalLibraries.Add("llama");
                PublicAdditionalLibraries.Add("ggml");
                PublicAdditionalLibraries.Add("ggml-base");
                PublicAdditionalLibraries.Add("ggml-cpu");
            }
            PublicDefinitions.Add("WITH_LLAMA_CPP=1");
        }
    }

    private void SetupOpenCV(ReadOnlyTargetRules Target)
    {
        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));
        string OpenCVPath = System.IO.Path.Combine(ThirdPartyPath, "opencv");

        if (System.IO.Directory.Exists(OpenCVPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(OpenCVPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(OpenCVPath, "lib", Target.Platform.ToString()));

            string[] opencvLibs = {
                "opencv_world4100",  // Single unified lib (adjust version as needed)
                // Or individual modules:
                // "opencv_core4100", "opencv_imgproc4100", "opencv_imgcodecs4100",
                // "opencv_videoio4100", "opencv_cudaarithm4100", "opencv_cudawarping4100",
            };

            foreach (string lib in opencvLibs)
            {
                if (Target.Platform == UnrealTargetPlatform.Win64)
                    PublicAdditionalLibraries.Add(lib + ".lib");
                else
                    PublicAdditionalLibraries.Add(lib);
            }
            PublicDefinitions.Add("WITH_OPENCV=1");
        }
        else
        {
            // Try system OpenCV (Linux/macOS)
            if (Target.Platform != UnrealTargetPlatform.Win64)
            {
                PublicAdditionalLibraries.AddRange(new string[] {
                    "opencv_core", "opencv_imgproc", "opencv_imgcodecs",
                    "opencv_videoio", "opencv_cudaarithm", "opencv_cudawarping"
                });
                PublicDefinitions.Add("WITH_OPENCV=1");
            }
        }
    }

    private void SetupGRPC(ReadOnlyTargetRules Target)
    {
        string ThirdPartyPath = System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "../../ThirdParty"));
        string GRPCPath = System.IO.Path.Combine(ThirdPartyPath, "grpc");

        if (System.IO.Directory.Exists(GRPCPath))
        {
            PublicIncludePaths.Add(System.IO.Path.Combine(GRPCPath, "include"));
            PublicLibraryPaths.Add(System.IO.Path.Combine(GRPCPath, "lib", Target.Platform.ToString()));

            string[] grpcLibs = { "grpc", "grpcpp", "grpc++_reflection", "grpc++_unsecure", "upb", "protobuf", "absl_*" };

            foreach (string lib in grpcLibs)
            {
                if (Target.Platform == UnrealTargetPlatform.Win64)
                    PublicAdditionalLibraries.Add(lib + ".lib");
                else
                    PublicAdditionalLibraries.Add(lib);
            }
            PublicDefinitions.Add("WITH_GRPC=1");
        }
    }
}