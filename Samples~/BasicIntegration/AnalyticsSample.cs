using System.Collections.Generic;
using Daliys.Analytics;
using UnityEngine;

namespace Daliys.Analytics.Samples
{
    public sealed class AnalyticsSample : MonoBehaviour
    {
        private void Awake()
        {
            Analytics.Initialize(new AnalyticsOptions
            {
                ServerUrl = "https://analytics.example.com",
                ProjectId = "sample-development",
                Environment = "development"
            });
        }

        private void Start()
        {
            Analytics.Track("sample_started", new Dictionary<string, object>
            {
                ["scene_name"] = gameObject.scene.name
            });
        }
    }
}
