// The durable queue of the browser (WebGL) build: V1 event JSON kept in memory and saved to localStorage, with the installation identity.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Web
{
    /// <summary>Small key/value storage that survives a page reload (localStorage in a browser). <see cref="Set"/> returns false when the storage refused (quota).</summary>
    internal interface IWebStorage
    {
        string Get(string key);
        bool Set(string key, string value);
    }

    /// <summary>
    /// Events waiting for the server, oldest first, each already in its V1 JSON form (with its sequence number). Bounded by characters (what localStorage
    /// counts) and optionally by count; when full the OLDEST events are dropped and counted. An event id already queued is ignored (a recovered session end
    /// has a fixed id). Not thread-safe: the browser pipeline uses it from the main thread.
    /// Storage keys are namespaced by project and environment, because every game on a portal origin shares one localStorage. Two tabs of one game share the
    /// keys: a save first takes in what the other tab stored (minus what this tab saw settled), so neither overwrites the other's events.
    /// </summary>
    internal sealed class WebEventQueue
    {
        private const string IdPrefix = "{\"event_id\":\"";
        private const int IdLength = 36;
        private const int SettledMemory = 20000;

        private readonly IWebStorage _storage;
        private readonly string _queueKey, _identityKey, _sessionKey, _countersKey;
        private readonly List<string> _events = new List<string>();
        private readonly HashSet<string> _ids = new HashSet<string>(StringComparer.Ordinal);
        /// <summary>Ids this tab removed (acknowledged, evicted, cleared): another tab's stored copy of them must not come back on a merge.</summary>
        private readonly HashSet<string> _settled = new HashSet<string>(StringComparer.Ordinal);
        private int _chars;
        private long _nextSequence;
        private bool _queueDirty, _identityDirty, _identitySaved;

        internal WebEventQueue(IWebStorage storage, string projectId, string environment, int maxChars, int maxEvents)
        {
            _storage = storage;
            var prefix = "mortris:" + projectId + ":" + environment + ":";
            _queueKey = prefix + "q"; _identityKey = prefix + "id"; _sessionKey = prefix + "s"; _countersKey = prefix + "c";
            MaxChars = maxChars; MaxEvents = maxEvents;
            Load();
        }

        internal int MaxChars { get; }
        /// <summary>0 = no limit by count.</summary>
        internal int MaxEvents { get; }
        internal int Count => _events.Count;
        internal int Chars => _chars;
        internal string InstallationId { get; private set; }
        internal string Credential { get; private set; }
        /// <summary>The server has registered this identity at least once (it survives page loads, so a page that closes early can still send).</summary>
        internal bool Registered { get; private set; }
        /// <summary>Events dropped because the queue was full, since the identity was created.</summary>
        internal long Evicted { get; private set; }
        internal bool Dirty => _queueDirty || _identityDirty;

        internal AnalyticsQueueState State => new AnalyticsQueueState(InstallationId, Credential, _events.Count);

        internal long NextSequence()
        {
            _identityDirty = true;
            return _nextSequence++;
        }

        /// <summary>Appends one event (V1 JSON object starting with its event_id). False when it was not kept: malformed, already queued, or bigger than the whole queue.</summary>
        internal bool Add(string eventJson)
        {
            if (!IsEvent(eventJson) || eventJson.Length > MaxChars)
            {
                Evicted++; _identityDirty = true;
                return false;
            }
            if (!_ids.Add(IdOf(eventJson))) return false;
            _events.Add(eventJson);
            _chars += eventJson.Length + 1;
            _queueDirty = true;
            Trim();
            return _ids.Contains(IdOf(eventJson));
        }

        /// <summary>The oldest events that fit both bounds.</summary>
        internal List<string> Oldest(int maxEvents, int maxChars)
        {
            var taken = new List<string>(Math.Min(maxEvents, _events.Count));
            var chars = 2;
            foreach (var e in _events)
            {
                if (taken.Count >= maxEvents || chars + e.Length + 1 > maxChars) break;
                taken.Add(e);
                chars += e.Length + 1;
            }
            return taken;
        }

        /// <summary>Removes the events with these ids (the server settled them); returns how many were removed.</summary>
        internal int Remove(ICollection<string> eventIds)
        {
            if (eventIds.Count == 0) return 0;
            var ids = eventIds as HashSet<string> ?? new HashSet<string>(eventIds, StringComparer.Ordinal);
            var removed = _events.RemoveAll(e => ids.Contains(IdOf(e)));
            foreach (var id in ids) if (_ids.Remove(id)) Settle(id);
            if (removed > 0) { RecountChars(); _queueDirty = true; }
            return removed;
        }

        internal void Clear()
        {
            foreach (var id in _ids) Settle(id);
            _events.Clear(); _ids.Clear(); _chars = 0; _queueDirty = true;
        }

        internal static string IdOf(string eventJson) => eventJson.Substring(IdPrefix.Length, IdLength);

        internal void MarkRegistered()
        {
            if (Registered) return;
            Registered = true; _identityDirty = true;
        }

        /// <summary>The server refused the credential as malformed: a fresh installation. The queued events stay (the batch envelope names the installation, not the events).</summary>
        internal void ResetIdentity()
        {
            NewIdentity();
            _identitySaved = true; // replaces the refused one in storage, never adopts it back
            Save();
        }

        internal string LoadSession() => _storage.Get(_sessionKey) ?? "";
        internal bool SaveSession(string snapshot) => _storage.Set(_sessionKey, snapshot ?? "");
        internal string LoadCounters() => _storage.Get(_countersKey) ?? "";
        internal bool SaveCounters(string json) => _storage.Set(_countersKey, json);

        /// <summary>
        /// Writes what changed, after taking in what another tab stored. Memory is never trimmed to make a write fit: when the storage refuses the queue
        /// (quota, or storage blocked altogether) the oldest half that fits is written instead, down to nothing, and false says the stored copy is short.
        /// The events are still in memory and still uploaded; only a page that dies before that loses what was not stored.
        /// </summary>
        internal bool Save()
        {
            var ok = true;
            if (_queueDirty)
            {
                MergeStored();
                var count = _events.Count;
                while (!_storage.Set(_queueKey, Join(count)))
                {
                    ok = false;
                    if (count == 0) break;
                    count /= 2;
                }
                if (count == _events.Count && ok) _queueDirty = false;
            }
            if (_identityDirty)
            {
                var stored = ReadIdentity();
                if (stored != null && stored.Value.id != InstallationId && !_identitySaved && !Registered)
                {
                    // two tabs opened on a first visit each made an identity: the one stored first wins, this tab's was never used
                    InstallationId = stored.Value.id; Credential = stored.Value.credential; Registered = stored.Value.registered;
                }
                if (stored != null && stored.Value.id == InstallationId && stored.Value.next > _nextSequence)
                    _nextSequence = stored.Value.next; // another tab handed out numbers meanwhile: continue after the highest
                if (_storage.Set(_identityKey, IdentityText())) { _identityDirty = false; _identitySaved = true; }
                else ok = false;
            }
            return ok;
        }

        private string Join(int count) => count == _events.Count ? string.Join("\n", _events) : string.Join("\n", _events.GetRange(0, count));

        private void MergeStored()
        {
            var stored = _storage.Get(_queueKey);
            if (string.IsNullOrEmpty(stored)) return;
            var added = false;
            foreach (var line in stored.Split('\n'))
            {
                if (!IsEvent(line)) continue;
                var id = IdOf(line);
                if (_settled.Contains(id) || !_ids.Add(id)) continue;
                _events.Add(line); _chars += line.Length + 1; added = true;
            }
            if (added) Trim();
        }

        private void Load()
        {
            var identity = ReadIdentity();
            if (identity != null)
            {
                InstallationId = identity.Value.id; Credential = identity.Value.credential; _nextSequence = identity.Value.next;
                Evicted = identity.Value.evicted; Registered = identity.Value.registered; _identitySaved = true;
            }
            else
            {
                NewIdentity();
            }
            MergeStored();
            Trim(); // the limits may have been lowered since the queue was saved
        }

        private (string id, string credential, long next, long evicted, bool registered)? ReadIdentity()
        {
            var parts = (_storage.Get(_identityKey) ?? "").Split(' ');
            if (parts.Length >= 5 && Guid.TryParse(parts[0], out _) && parts[1].Length == 43 &&
                long.TryParse(parts[2], NumberStyles.None, CultureInfo.InvariantCulture, out var next) &&
                long.TryParse(parts[3], NumberStyles.None, CultureInfo.InvariantCulture, out var evicted))
                return (parts[0], parts[1], next, evicted, parts[4] == "1");
            return null;
        }

        private void NewIdentity()
        {
            var secret = new byte[32];
            using (var random = RandomNumberGenerator.Create()) random.GetBytes(secret);
            InstallationId = Guid.NewGuid().ToString("D");
            Credential = Convert.ToBase64String(secret).TrimEnd('=').Replace('+', '-').Replace('/', '_');
            Registered = false;
            _identityDirty = true; _identitySaved = false;
        }

        private string IdentityText() =>
            InstallationId + " " + Credential + " " + _nextSequence.ToString(CultureInfo.InvariantCulture) + " " + Evicted.ToString(CultureInfo.InvariantCulture) + " " + (Registered ? "1" : "0");

        private static bool IsEvent(string line) =>
            line != null && line.Length > IdPrefix.Length + IdLength && line.StartsWith(IdPrefix, StringComparison.Ordinal) && line[IdPrefix.Length + IdLength] == '"';

        private void Settle(string id)
        {
            if (_settled.Count >= SettledMemory) _settled.Clear(); // ponytail: forgets old settlements; at worst a long-gone tab's copy is resent and deduplicated
            _settled.Add(id);
        }

        private void Trim()
        {
            var drop = 0; var chars = _chars;
            while (drop < _events.Count && (chars > MaxChars || (MaxEvents > 0 && _events.Count - drop > MaxEvents)))
            {
                chars -= _events[drop].Length + 1;
                drop++;
            }
            if (drop == 0) return;
            for (var i = 0; i < drop; i++) { var id = IdOf(_events[i]); _ids.Remove(id); Settle(id); }
            _events.RemoveRange(0, drop);
            _chars = chars;
            Evicted += drop;
            _queueDirty = true; _identityDirty = true;
        }

        private void RecountChars()
        {
            _chars = 0;
            foreach (var e in _events) _chars += e.Length + 1;
        }
    }
}
