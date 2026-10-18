using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// The server stores a V7 event under a name-derived id computed from (project, install, epoch, sequence)
    /// (MortrisServer internal/transportv7.DerivedEventID). The SDK computes the same id so that an event it has to send through V1
    /// while a stream is open carries the identical id, and the server's primary key then recognises a resend of a row V7 already stored.
    /// </summary>
    internal static class V7Identity
    {
        // derive(DNS namespace, "transport-v7.mortris"); fixed forever (the server test pins it as 4afdc7a7-de1e-45d3-a74f-d6061efed25e).
        private static readonly byte[] DnsNamespace = { 0x6b, 0xa7, 0xb8, 0x10, 0x9d, 0xad, 0x11, 0xd1, 0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8 };
        private static readonly byte[] Namespace = Derive(DnsNamespace, "transport-v7.mortris");

        internal static string DerivedEventId(string project, string install, long epoch, long sequence)
        {
            var name = project.Length.ToString(CultureInfo.InvariantCulture) + ":" + project + "|" + install.Length.ToString(CultureInfo.InvariantCulture) + ":" + install + "|" +
                       epoch.ToString(CultureInfo.InvariantCulture) + "|" + sequence.ToString(CultureInfo.InvariantCulture);
            return Format(Derive(Namespace, name));
        }

        /// <summary>SHA-1 over namespace and name like an RFC 4122 v5 UUID, but with the version nibble 4 (the server only accepts v4-shaped ids).</summary>
        internal static byte[] Derive(byte[] ns, string name)
        {
            var input = new List<byte>(ns);
            input.AddRange(Encoding.UTF8.GetBytes(name));
            byte[] hash;
            using (var sha = SHA1.Create()) hash = sha.ComputeHash(input.ToArray());
            var id = new byte[16];
            Buffer.BlockCopy(hash, 0, id, 0, 16);
            id[6] = (byte)((id[6] & 0x0f) | 0x40);
            id[8] = (byte)((id[8] & 0x3f) | 0x80);
            return id;
        }

        private static string Format(byte[] id)
        {
            var hex = new StringBuilder(36);
            for (var i = 0; i < 16; i++)
            {
                if (i == 4 || i == 6 || i == 8 || i == 10) hex.Append('-');
                hex.Append(id[i].ToString("x2", CultureInfo.InvariantCulture));
            }
            return hex.ToString();
        }

        /// <summary>
        /// Rewrites each queued event's <c>event_id</c> to its derived id for the open stream. Returns the new batch JSON and, for each event,
        /// the pair (original id, derived id) so acknowledgements can be mapped back to the queue's rows.
        /// </summary>
        internal static string RewriteEventIds(string batchJson, string project, string install, long epoch, out List<KeyValuePair<string, string>> ids)
        {
            var events = MiniJson.ParseArray(batchJson);
            ids = new List<KeyValuePair<string, string>>(events.Count);
            foreach (var item in events)
            {
                var e = (Dictionary<string, object>)item;
                var original = (string)e["event_id"];
                var sequence = long.Parse(((JsonNumber)e["sequence"]).Lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
                var derived = DerivedEventId(project, install, epoch, sequence);
                e["event_id"] = derived;
                ids.Add(new KeyValuePair<string, string>(original, derived));
            }
            return MiniJson.Serialize(events);
        }
    }
}
