#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class V7DeviceBuild
{
    /// <summary>Builds the probe APK: IL2CPP, ARM64 + ARMv7, development build. Output path comes from -v7-apk.</summary>
    public static void Build()
    {
        var output = "v7-device.apk";
        var args = System.Environment.GetCommandLineArgs();
        for (var i = 0; i < args.Length - 1; i++) if (args[i] == "-v7-apk") output = args[i + 1];

        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("V7DeviceProbe").AddComponent<V7DeviceProbe>();
        EditorSceneManager.SaveScene(scene, "Assets/Scenes/Probe.unity");

        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64 | AndroidArchitecture.ARMv7;
        PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.daliys.v7device");
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel25;
        PlayerSettings.Android.forceInternetPermission = true;
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/Probe.unity" }, locationPathName = output, target = BuildTarget.Android, options = BuildOptions.Development,
        });
        Debug.Log("V7DEVICE build " + report.summary.result + " " + report.summary.totalSize + " bytes");
        if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) EditorApplication.Exit(1);
    }
}
#endif
