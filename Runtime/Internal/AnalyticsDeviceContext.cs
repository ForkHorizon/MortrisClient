using System;
using System.Globalization;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    internal sealed class AnalyticsDeviceContext
    {
        internal const string SdkName = "mortris-unity";
        internal const string SdkVersion = "0.2.0";

        internal AnalyticsDeviceContext(string appVersion, string buildNumber, string platform, string osVersion, string deviceClass, string locale, int timezoneOffsetMinutes)
        {
            AppVersion = appVersion;
            BuildNumber = buildNumber;
            Platform = platform;
            OSVersion = osVersion;
            DeviceClass = deviceClass;
            Locale = locale;
            TimezoneOffsetMinutes = timezoneOffsetMinutes;
        }

        internal string AppVersion { get; }
        internal string BuildNumber { get; }
        internal string Platform { get; }
        internal string OSVersion { get; }
        internal string DeviceClass { get; }
        internal string Locale { get; }
        internal int TimezoneOffsetMinutes { get; }

        internal static AnalyticsDeviceContext Create(AnalyticsOptions options)
        {
            var t = AnalyticsProf.Begin();
            var appVersion = FirstNonEmpty(options.AppVersion, Application.version, "unknown");
            var buildNumber = FirstNonEmpty(options.BuildNumber, Application.buildGUID, "unknown");
            var platform = Application.platform.ToString().ToLowerInvariant();
            AnalyticsProf.End(Stage.DeviceApp, t); t = AnalyticsProf.Begin();
            var osVersion = FirstNonEmpty(SystemInfo.operatingSystem, "unknown");
            AnalyticsProf.End(Stage.DeviceOs, t); t = AnalyticsProf.Begin();
            var deviceClass = FirstNonEmpty(SystemInfo.deviceModel, SystemInfo.deviceType.ToString(), "unknown");
            AnalyticsProf.End(Stage.DeviceModel, t); t = AnalyticsProf.Begin();
            var locale = FirstNonEmpty(CultureInfo.CurrentCulture.Name, Application.systemLanguage.ToString(), "und");
            AnalyticsProf.End(Stage.DeviceCulture, t); t = AnalyticsProf.Begin();
            var timezoneOffsetMinutes = CurrentUtcOffsetMinutes();
            AnalyticsProf.End(Stage.DeviceTimezone, t);
            return new AnalyticsDeviceContext(appVersion, buildNumber, platform, osVersion, deviceClass, locale, timezoneOffsetMinutes);
        }

        /// <summary>
        /// The offset from UTC in minutes now. <c>TimeZoneInfo.Local</c> costs about 100 ms on first use in an IL2CPP Android player (it loads the time zone database), so on a device
        /// the offset comes from <c>java.util.TimeZone</c> (well under a millisecond); anywhere else, or if the call fails, it is the .NET value.
        /// </summary>
        private static int CurrentUtcOffsetMinutes()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var zones = new AndroidJavaClass("java.util.TimeZone"))
                using (var zone = zones.CallStatic<AndroidJavaObject>("getDefault"))
                    return zone.Call<int>("getOffset", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()) / 60000;
            }
            catch (Exception)
            {
            }
#endif
            return (int)TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow).TotalMinutes;
        }

        private static string FirstNonEmpty(params string[] values)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                    return value;
            }
            return "unknown";
        }
    }
}
