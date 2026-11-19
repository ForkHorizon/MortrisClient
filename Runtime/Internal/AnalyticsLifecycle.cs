// Hidden persistent object that forwards Unity's application callbacks to the analytics runtime.
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// A hidden, persistent object that forwards Unity's application callbacks to the analytics runtime. It is how the SDK learns that the player
    /// minimised or left the game (pause, focus loss, quit), so session ends are recorded and buffered events reach the durable queue.
    /// </summary>
    internal sealed class AnalyticsLifecycle : MonoBehaviour
    {
        private static AnalyticsLifecycle _instance;
        private AnalyticsRuntime _runtime;

        /// <summary>Creates the forwarder on the main thread. Does nothing outside play mode (edit-mode tests, tools).</summary>
        internal static void Attach(AnalyticsRuntime runtime)
        {
            if (!Application.isPlaying)
                return;

            Detach();
            var host = new GameObject("DaliysAnalyticsLifecycle") { hideFlags = HideFlags.HideAndDontSave };
            DontDestroyOnLoad(host);
            _instance = host.AddComponent<AnalyticsLifecycle>();
            _instance._runtime = runtime;
            _instance.StartCoroutine(_instance.WatchNetwork());
            // In a browser the page being hidden (tab switch, minimise, close) is what "the player left" means; Unity's pause callback does not fire there.
            Web.WebPlatform.WatchVisibility(hidden => { if (_instance != null) _instance._runtime?.OnApplicationPause(hidden); });
        }

        private void Update() => _runtime?.Tick();

        /// <summary>Removes the forwarder (the runtime was replaced or disposed, as tests do).</summary>
        internal static void Detach()
        {
            if (_instance == null)
                return;
            if (Application.isPlaying) Destroy(_instance.gameObject); else DestroyImmediate(_instance.gameObject);
            _instance = null;
        }

        /// <summary>
        /// Tells the runtime whether the device has a network (every 5 seconds; <c>Application.internetReachability</c> is a property read and needs no permission). This is only
        /// a hint: "reachable" can still mean a portal or a dead Wi-Fi, which the upload handles like any failure.
        /// </summary>
        private System.Collections.IEnumerator WatchNetwork()
        {
            var wait = new WaitForSecondsRealtime(5f);
            while (true)
            {
                _runtime?.SetNetworkReachable(Application.internetReachability != NetworkReachability.NotReachable);
                yield return wait;
            }
        }

        private void OnApplicationPause(bool paused) => _runtime?.OnApplicationPause(paused);

        private void OnApplicationFocus(bool hasFocus) => _runtime?.OnApplicationFocus(hasFocus);

        private void OnApplicationQuit() => _runtime?.OnApplicationQuit();
    }
}
