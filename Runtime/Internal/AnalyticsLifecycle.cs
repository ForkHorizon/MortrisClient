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
        }

        /// <summary>Removes the forwarder (the runtime was replaced or disposed, as tests do).</summary>
        internal static void Detach()
        {
            if (_instance == null)
                return;
            if (Application.isPlaying) Destroy(_instance.gameObject); else DestroyImmediate(_instance.gameObject);
            _instance = null;
        }

        private void OnApplicationPause(bool paused) => _runtime?.OnApplicationPause(paused);

        private void OnApplicationFocus(bool hasFocus) => _runtime?.OnApplicationFocus(hasFocus);

        private void OnApplicationQuit() => _runtime?.OnApplicationQuit();
    }
}
