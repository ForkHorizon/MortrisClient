using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// The per-process alias table of repeated event context (session, app version, device...). Packets refer to a context by
    /// its index; the server holds the same table for the stream. Append-only within an epoch; a new process starts a new epoch.
    /// </summary>
    internal sealed class M7Aliases
    {
        private readonly List<string[]> _records = new List<string[]>();
        private readonly Dictionary<string, int> _index = new Dictionary<string, int>(StringComparer.Ordinal);

        internal M7Aliases() : this(RandomEpoch()) { }

        internal M7Aliases(byte[] epoch)
        {
            if (epoch == null || epoch.Length != 8) throw new ArgumentException("Alias epoch must be 8 bytes.");
            Epoch = (byte[])epoch.Clone();
        }

        internal byte[] Epoch { get; }
        internal string EpochHex => ToHex(Epoch);
        internal int Count => _records.Count;
        internal int MaxRecords => 65536;

        /// <summary>Index of the context record, appended when new. Fails when the table is full.</summary>
        internal bool TryRegister(string origin, M7Event e, out int index)
        {
            var record = new[] { origin, e.SessionId, e.AppVersion, e.BuildNumber, e.Platform, e.OsVersion, e.DeviceClass, e.Locale, e.TimezoneOffsetMinutes.ToString(System.Globalization.CultureInfo.InvariantCulture) };
            var key = string.Join("\u0001", record);
            if (_index.TryGetValue(key, out index)) return true;
            if (_records.Count >= MaxRecords) return false;
            index = _records.Count;
            _index.Add(key, index);
            _records.Add(record);
            return true;
        }

        /// <summary>JSON array of records [from, Count) in the server's wire form (the last value is an integer).</summary>
        internal string RecordsJson(int from, int count)
        {
            var json = new StringBuilder("[");
            for (var i = from; i < from + count; i++)
            {
                if (i > from) json.Append(',');
                var r = _records[i];
                json.Append('[');
                for (var j = 0; j < 8; j++) json.Append(MiniJson.Escape(r[j])).Append(',');
                json.Append(r[8]).Append(']');
            }
            return json.Append(']').ToString();
        }

        private static byte[] RandomEpoch()
        {
            var bytes = new byte[8];
            using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
            return bytes;
        }

        internal static string ToHex(byte[] bytes)
        {
            var builder = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes) builder.Append(b.ToString("x2", System.Globalization.CultureInfo.InvariantCulture));
            return builder.ToString();
        }
    }
}
