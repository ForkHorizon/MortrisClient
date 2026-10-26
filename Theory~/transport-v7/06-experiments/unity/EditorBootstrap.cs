using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace TransportV7Research
{
    public static class EditorBootstrap
    {
        static string Argument(string name)
        {
            string[] args=Environment.GetCommandLineArgs();
            for(int i=0;i<args.Length-1;i++) if(args[i]==name)return args[i+1];
            throw new ArgumentException(name);
        }
        [Serializable] public sealed class EnvironmentState { public bool android_supported; public string contents_path, unity_version; }
        public static void ReportEnvironment()
        {
            var state=new EnvironmentState { android_supported=BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Android,BuildTarget.Android),contents_path=EditorApplication.applicationContentsPath,unity_version=Application.unityVersion };
            File.WriteAllText(Argument("--v7-output"),JsonUtility.ToJson(state,true));EditorApplication.Exit(0);
        }
        public static void RunEditor()
        {
            try { bool passed=Harness.Run(Argument("--v7-output"),"Unity Editor Mono");EditorApplication.Exit(passed?0:2); }
            catch(Exception e) { Debug.LogException(e);EditorApplication.Exit(3); }
        }
        public static void BuildAndroid()
        {
            try
            {
                PlayerSettings.allowUnsafeCode=true;
                var plugin=(PluginImporter)AssetImporter.GetAtPath("Assets/Plugins/Android/arm64-v8a/libzstd.so");
                plugin.SetCompatibleWithAnyPlatform(false);plugin.SetCompatibleWithEditor(false);
                plugin.SetCompatibleWithPlatform(BuildTarget.Android,true);plugin.SetPlatformData(BuildTarget.Android,"CPU","ARM64");plugin.SaveAndReimport();
                PlayerSettings.companyName="TransportResearch";PlayerSettings.productName="TransportV7Bench";
                PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android,"com.daliys.transport7.research");
                PlayerSettings.bundleVersion="7.0.0";PlayerSettings.Android.bundleVersionCode=1;
                PlayerSettings.Android.targetArchitectures=AndroidArchitecture.ARM64;
                PlayerSettings.Android.minSdkVersion=AndroidSdkVersions.AndroidApiLevel25;
                PlayerSettings.Android.targetSdkVersion=AndroidSdkVersions.AndroidApiLevel35;
                PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android,ScriptingImplementation.IL2CPP);
                var scene=UnityEditor.SceneManagement.EditorSceneManager.NewScene(UnityEditor.SceneManagement.NewSceneSetup.EmptyScene);
                UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene,"Assets/Benchmark.unity");
                string[] args=Environment.GetCommandLineArgs();bool development=Array.IndexOf(args,"--v7-development")>=0;
                BuildReport report=BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes=new[]{"Assets/Benchmark.unity"},locationPathName=Argument("--v7-player"),target=BuildTarget.Android,options=development?BuildOptions.Development:BuildOptions.None });
                EditorApplication.Exit(report.summary.result==BuildResult.Succeeded?0:4);
            }
            catch(Exception e){Debug.LogException(e);EditorApplication.Exit(5);}
        }
        public static void BuildPlayer()
        {
            PlayerSettings.allowUnsafeCode=true;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone,ScriptingImplementation.IL2CPP);
            var scene=UnityEditor.SceneManagement.EditorSceneManager.NewScene(UnityEditor.SceneManagement.NewSceneSetup.EmptyScene);
            UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene,"Assets/Benchmark.unity");
            BuildReport report=BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes=new[]{"Assets/Benchmark.unity"},locationPathName=Argument("--v7-player"),target=BuildTarget.StandaloneOSX,options=BuildOptions.None });
            EditorApplication.Exit(report.summary.result==BuildResult.Succeeded?0:4);
        }
    }
}
