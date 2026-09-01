// Copyright (c) 2024 HephaestusForge. All Rights Reserved.

using UnrealBuildTool;
using System.IO;

public class HephaestusBridge : ModuleRules
{
	public HephaestusBridge(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;

		PublicIncludePaths.AddRange(new string[]
		{
			Path.Combine(ModuleDirectory, "Public"),
			Path.Combine(ModuleDirectory, "Public", "Vision"),
			Path.Combine(ModuleDirectory, "Public", "Command"),
			Path.Combine(ModuleDirectory, "Public", "World"),
			Path.Combine(ModuleDirectory, "Public", "Assets"),
			Path.Combine(ModuleDirectory, "Public", "Blueprints"),
			Path.Combine(ModuleDirectory, "Public", "Rendering"),
			Path.Combine(ModuleDirectory, "Public", "PCG"),
			Path.Combine(ModuleDirectory, "Public", "Animation"),
			Path.Combine(ModuleDirectory, "Public", "Audio"),
			Path.Combine(ModuleDirectory, "Public", "Sequence"),
		});

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"Projects",
			"Json",
			"JsonUtilities",
			"HTTP",
			"HTTPServer",
			"Sockets",
			"Networking",
			"AssetRegistry",
			"ImageWrapper",
			"GameplayTags",
			"GameplayTasks",
			"AIModule",
			"NavigationSystem",
			"AudioMixer",
			"LevelSequence",
			"MovieScene",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore",
			"RenderCore",
			"RHI",
			"ApplicationCore",
		});

		if (Target.bBuildEditor)
		{
			PrivateDependencyModuleNames.AddRange(new string[]
			{
				"UnrealEd",
				"AssetTools",
				"BlueprintGraph",
				"PropertyEditor",
				"ContentBrowser",
				"ToolMenus",
				"EditorStyle",
				"DeveloperSettings",
			});
		}

		PublicDefinitions.AddRange(new string[]
		{
			"WITH_HEPHAESTUS_VISION=1",
			"WITH_HEPHAESTUS_COMMAND=1",
			"WITH_HEPHAESTUS_WORLD=1",
			"WITH_HEPHAESTUS_ASSETS=1",
			"WITH_HEPHAESTUS_BLUEPRINTS=1",
			"WITH_HEPHAESTUS_RENDERING=1",
			"WITH_HEPHAESTUS_PCG=1",
			"WITH_HEPHAESTUS_ANIMATION=1",
			"WITH_HEPHAESTUS_AUDIO=1",
			"WITH_HEPHAESTUS_SEQUENCE=1",
			"WITH_HEPHAESTUS_REMOTE_API=1",
		});
	}
}

