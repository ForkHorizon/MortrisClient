using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// Named counters for the game's own ids (attempt 1, 2, 3...; <c>Analytics.NextId</c>). A value is bumped in memory at once and written to the durable queue
    /// in the same transaction as the next batch of events, so after a crash a counter and the events that used its numbers are either both there or both
    /// gone: a number the server has seen is never handed out again.
    /// </summary>
    internal sealed class AnalyticsCounters
    {
        internal const int MaxCounters = 64;
        private readonly object _sync = new object();
        private readonly Dictionary<string, long> _values = new Dictionary<string, long>(StringComparer.Ordinal);
        private bool _dirty, _loaded;

        internal bool IsLoaded { get { lock (_sync) return _loaded; } }

        internal static bool ValidName(string name)
        {
            if (string.IsNullOrEmpty(name) || name.Length > 64) return false;
            foreach (var c in name) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
            return true;
        }

        /// <summary>Takes the stored values (JSON object of integers; empty or damaged text means none). Values already counted in memory are kept when larger.</summary>
        internal void Load(string json)
        {
            lock (_sync)
            {
                if (!string.IsNullOrEmpty(json))
                {
                    try
                    {
                        foreach (var pair in MiniJson.ParseObject(json))
                            if (ValidName(pair.Key) && pair.Value is JsonNumber n && long.TryParse(n.Lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var value) && value >= 0)
                                _values[pair.Key] = _values.TryGetValue(pair.Key, out var current) && current > value ? current : value;
                    }
                    catch (FormatException) { /* damaged: start from what is in memory */ }
                }
                _loaded = true;
            }
        }

        /// <summary>The next number of the counter (1 for a counter never used).</summary>
        internal long Next(string name)
        {
            if (!ValidName(name)) throw new ArgumentException("A counter name is 1 to 64 characters: a-z, 0-9 and _.", nameof(name));
            lock (_sync)
            {
                if (!_values.TryGetValue(name, out var value))
                {
                    if (_values.Count >= MaxCounters) throw new InvalidOperationException("At most " + MaxCounters + " counters are supported.");
                    value = 0;
                }
                _values[name] = ++value;
                _dirty = true;
                return value;
            }
        }

        /// <summary>The values as JSON when something changed since the last snapshot, else null.</summary>
        internal string Snapshot()
        {
            lock (_sync)
            {
                if (!_dirty) return null;
                _dirty = false;
                var json = new StringBuilder("{");
                var first = true;
                foreach (var pair in _values)
                {
                    if (!first) json.Append(',');
                    first = false;
                    json.Append('"').Append(pair.Key).Append("\":").Append(pair.Value.ToString(CultureInfo.InvariantCulture));
                }
                return json.Append('}').ToString();
            }
        }

        /// <summary>The last snapshot was not stored: offer it again with the next batch.</summary>
        internal void MarkDirty() { lock (_sync) _dirty = true; }
    }
}
