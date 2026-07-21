using System;
using System.Globalization;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    internal sealed class AnalyticsDeviceContext
    {
        internal const string SdkName = "mortris-unity";
        internal const string SdkVersion = "0.1.4";

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
            var appVersion = FirstNonEmpty(options.AppVersion, Application.version, "unknown");
            var buildNumber = FirstNonEmpty(options.BuildNumber, Application.buildGUID, "unknown");
            var platform = Application.platform.ToString().ToLowerInvariant();
            var osVersion = FirstNonEmpty(SystemInfo.operatingSystem, "unknown");
            var deviceClass = FirstNonEmpty(SystemInfo.deviceModel, SystemInfo.deviceType.ToString(), "unknown");
            var locale = FirstNonEmpty(CultureInfo.CurrentCulture.Name, Application.systemLanguage.ToString(), "und");
            var timezoneOffsetMinutes = (int)TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow).TotalMinutes;
            return new AnalyticsDeviceContext(appVersion, buildNumber, platform, osVersion, deviceClass, locale, timezoneOffsetMinutes);
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
