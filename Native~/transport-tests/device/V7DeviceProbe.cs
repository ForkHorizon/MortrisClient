using System;
using System.Collections;
using System.Collections.Generic;
using Daliys.Analytics;
using UnityEngine;

/// <summary>
/// Device-level proof for the V7 transport: sends events whose shapes are in the synthetic catalog (V7), then one event with a shape the
/// catalog does not know (V1 fallback), against the local server on the host (10.0.2.2 from the emulator). Progress goes to logcat (V7DEVICE).
/// </summary>
public sealed class V7DeviceProbe : MonoBehaviour
{
    private const string Server = "http://10.0.2.2:18082", Project = "synth_indie_runner";
    private static readonly string[] Names = { "level_start", "level_end", "purchase_ui", "ad_view", "death", "tutorial_step", "sync" };

    private void Start()
    {
        Analytics.Initialize(new AnalyticsOptions
        {
            ServerUrl = Server, ProjectId = Project, Environment = "test", DebugLogging = true, UseTransportV7 = true,
            UploadInterval = TimeSpan.FromSeconds(5), UploadEventThreshold = 10, AppVersion = "0.2.0-device", BuildNumber = "device-1",
        });
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        var random = new System.Random(42);
        var accepted = 0;
        for (var i = 0; i < 120; i++)
        {
            var name = Names[random.Next(Names.Length)];
            var props = new Dictionary<string, object>
            {
                ["level"] = random.Next(1, 40), ["mode"] = new[] { "easy", "hard", "endless" }[random.Next(3)],
                ["score"] = new[] { 0, 10, 50, 100, 250 }[random.Next(5)], ["coins"] = random.Next(0, 5), ["lucky"] = random.NextDouble() < .1,
            };
            if (name == "purchase_ui") { props["sku"] = new[] { "gems_100", "gems_500", "noads" }[random.Next(3)]; props["price"] = new[] { 0.99, 4.99, 9.99 }[random.Next(3)]; }
            if (Analytics.Track(name, props) == TrackResult.AcceptedToHandoff) accepted++;
            yield return new WaitForSeconds(0.05f);
        }
        // A shape the project's catalog has never seen: must travel through V1.
        var unknown = Analytics.Track("level_start", new Dictionary<string, object> { ["level"] = 1, ["mode"] = "easy", ["score"] = 0, ["coins"] = 0, ["lucky"] = false, ["mystery"] = 7 });
        Debug.Log("V7DEVICE tracked accepted=" + accepted + " unknown=" + unknown);

        var done = false;
        for (var round = 0; round < 8 && !done; round++)
        {
            var flush = Analytics.FlushAsync();
            while (!flush.IsCompleted) yield return null;
            Debug.Log("V7DEVICE flush round " + round + " status=" + flush.Result.Status + " pending=" + flush.Result.HandoffEventsPending);
            done = flush.Result.Status == FlushStatus.Uploaded;
            yield return new WaitForSeconds(3f);
        }
        Debug.Log("V7DEVICE finished done=" + done);
        yield return new WaitForSeconds(5f);
        Application.Quit();
    }
}
