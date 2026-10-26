#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class CmpBuild
{
    /// <summary>IL2CPP development build with the profiling probe. -v7-apk <path>; -v7-armv7-only; -prof-emulator-x86 is not supported (arm64 only here).</summary>
    public static void Build()
    {
        var output = "v7-prof.apk"; var armv7Only = false; var profile = false; var development = false;
        var args = System.Environment.GetCommandLineArgs();
        for (var i = 0; i < args.Length; i++) { if (args[i] == "-v7-apk" && i + 1 < args.Length) output = args[i + 1]; if (args[i] == "-v7-armv7-only") armv7Only = true; if (args[i] == "-cmp-profile") profile = true; if (args[i] == "-cmp-dev") development = true; }
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("CmpProbe").AddComponent<CmpProbe>();
        EditorSceneManager.SaveScene(scene, "Assets/Scenes/Cmp.unity");
        // -cmp-profile compiles the SDK's stage timers in (scripting define DALIYS_ANALYTICS_PROFILE); -cmp-dev makes a Development player (valid ProfilerRecorder allocation counters)
        PlayerSettings.SetScriptingDefineSymbols(NamedBuildTarget.Android, profile ? "DALIYS_ANALYTICS_PROFILE" : "");
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = armv7Only ? AndroidArchitecture.ARMv7 : AndroidArchitecture.ARM64;
        PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.daliys.cmpprobe");
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel25;
        PlayerSettings.Android.forceInternetPermission = true;
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes = new[] { "Assets/Scenes/Cmp.unity" }, locationPathName = output, target = BuildTarget.Android, options = development ? BuildOptions.Development : BuildOptions.None });
        Debug.Log("CMP build " + report.summary.result + " " + report.summary.totalSize + " bytes");
        if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) EditorApplication.Exit(1);
    }
}
#endif
