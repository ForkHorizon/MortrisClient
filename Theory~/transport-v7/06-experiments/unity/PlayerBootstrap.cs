using System;
using UnityEngine;
namespace TransportV7Research
{
    public static class PlayerBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Start()
        {
            try
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                string output;
                using(var player=new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using(var activity=player.GetStatic<AndroidJavaObject>("currentActivity"))
                using(var files=activity.Call<AndroidJavaObject>("getFilesDir"))
                    output=System.IO.Path.Combine(files.Call<string>("getAbsolutePath"),"benchmark-output");
                bool passed=Harness.Run(output,"Unity Android IL2CPP",UnityEngine.Debug.isDebugBuild);
                UnityEngine.Debug.Log("V7_BENCHMARK_COMPLETE "+(passed?"PASS":"FAIL"));
                Application.Quit(passed?0:2);
#else
                string[] args=Environment.GetCommandLineArgs();string output=null;
                for(int i=0;i<args.Length-1;i++)if(args[i]=="--v7-output")output=args[i+1];
                if(output==null)return;
                Application.Quit(Harness.Run(output,"Unity macOS IL2CPP")?0:2);
#endif
            }
            catch(Exception e){Debug.LogException(e);Application.Quit(3);}
        }
    }
}
