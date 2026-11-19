// Browser glue of the WebGL build: localStorage, page visibility and fetch keepalive (Plugins/WebGL/MortrisWeb.jslib), HTTP through UnityWebRequest.
using System;
using UnityEngine;
using UnityEngine.Networking;

namespace Daliys.Analytics.Internal.Web
{
    internal static class WebPlatform
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        internal static bool IsSupported => true;

        [System.Runtime.InteropServices.DllImport("__Internal")] private static extern string MortrisStorageGet(string key);
        [System.Runtime.InteropServices.DllImport("__Internal")] private static extern int MortrisStorageSet(string key, string value);
        [System.Runtime.InteropServices.DllImport("__Internal")] private static extern int MortrisKeepalive(string url, string bearer, byte[] body, int length, int gzip);
        [System.Runtime.InteropServices.DllImport("__Internal")] private static extern void MortrisWatchVisibility(Action<int> onChange);

        private static Action<bool> _visibility;

        /// <summary>Calls <paramref name="onHidden"/>(true) when the page is hidden or unloaded (tab switch, minimise, close, navigation) and (false) when it is visible again.</summary>
        internal static void WatchVisibility(Action<bool> onHidden)
        {
            var first = _visibility == null;
            _visibility = onHidden;
            if (first) MortrisWatchVisibility(OnVisibility);
        }

        [AOT.MonoPInvokeCallback(typeof(Action<int>))]
        private static void OnVisibility(int hidden)
        {
            try { _visibility?.Invoke(hidden != 0); }
            catch (Exception exception) { Debug.LogException(exception); } // never let an exception escape into the browser's event dispatch
        }

        private sealed class LocalStorage : IWebStorage
        {
            public string Get(string key) => MortrisStorageGet(key);
            public bool Set(string key, string value) => MortrisStorageSet(key, value) == 1;
        }

        internal static IWebStorage CreateStorage() => new LocalStorage();

        private static bool Keepalive(string url, byte[] body, bool gzip, string bearer) => MortrisKeepalive(url, bearer ?? "", body, body.Length, gzip ? 1 : 0) == 1;
#else
        internal static bool IsSupported => false;
        internal static void WatchVisibility(Action<bool> onHidden) { }
        internal static IWebStorage CreateStorage() => throw new PlatformNotSupportedException();
        private static bool Keepalive(string url, byte[] body, bool gzip, string bearer) => false;
#endif

        /// <summary>The pipeline of a WebGL player (the browser's localStorage and network).</summary>
        internal static WebPipeline CreatePipeline(AnalyticsOptions options, Action<ServerPolicy> policyChanged) =>
            new WebPipeline(options, AnalyticsDeviceContext.Create(options), CreateStorage(), new UnityHttp(), () => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), policyChanged);

        /// <summary>UnityWebRequest, which a WebGL player runs on the browser's fetch/XHR; completion arrives on the main thread.</summary>
        internal sealed class UnityHttp : IWebHttp
        {
            private const int TimeoutSeconds = 20;

            public void Post(string url, byte[] body, bool gzip, string bearer, Action<int, string, string> done)
            {
                var request = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST)
                {
                    uploadHandler = new UploadHandlerRaw(body) { contentType = "application/json" },
                    downloadHandler = new DownloadHandlerBuffer(),
                    timeout = TimeoutSeconds,
                };
                request.SetRequestHeader("Content-Type", "application/json");
                if (gzip) request.SetRequestHeader("Content-Encoding", "gzip");
                if (!string.IsNullOrEmpty(bearer)) request.SetRequestHeader("Authorization", "Bearer " + bearer);
                request.SendWebRequest().completed += _ =>
                {
                    int status; string text, retryAfter;
                    try
                    {
                        // A refused CORS preflight, an offline browser and a timeout all come back as a connection error without a status.
                        status = request.result == UnityWebRequest.Result.ConnectionError ? 0 : (int)request.responseCode;
                        text = request.downloadHandler?.text ?? "";
                        retryAfter = request.GetResponseHeader("Retry-After");
                    }
                    finally { request.Dispose(); }
                    done(status, text, retryAfter);
                };
            }

            public bool PostKeepalive(string url, byte[] body, bool gzip, string bearer) => Keepalive(url, body, gzip, bearer);
        }
    }
}
