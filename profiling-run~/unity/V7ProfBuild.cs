#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class V7ProfBuild
{
    /// <summary>IL2CPP development build with the profiling probe. -v7-apk <path>; -v7-armv7-only; -prof-emulator-x86 is not supported (arm64 only here).</summary>
    public static void Build()
    {
        var output = "v7-prof.apk"; var armv7Only = false;
        var args = System.Environment.GetCommandLineArgs();
        for (var i = 0; i < args.Length; i++) { if (args[i] == "-v7-apk" && i + 1 < args.Length) output = args[i + 1]; if (args[i] == "-v7-armv7-only") armv7Only = true; }
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("V7ProfProbe").AddComponent<V7ProfProbe>();
        EditorSceneManager.SaveScene(scene, "Assets/Scenes/Prof.unity");
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = armv7Only ? AndroidArchitecture.ARMv7 : AndroidArchitecture.ARM64;
        PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.daliys.v7prof");
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel25;
        PlayerSettings.Android.forceInternetPermission = true;
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes = new[] { "Assets/Scenes/Prof.unity" }, locationPathName = output, target = BuildTarget.Android, options = BuildOptions.Development | BuildOptions.AllowDebugging });
        Debug.Log("V7PROF build " + report.summary.result + " " + report.summary.totalSize + " bytes");
        if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) EditorApplication.Exit(1);
    }
}
#endif
