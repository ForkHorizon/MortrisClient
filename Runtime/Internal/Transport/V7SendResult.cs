// Outcome of one binary-transport (V8) send, read by the uploader.
using System;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>What one binary-transport send did; anything but Delivered/Empty sends the batch through V1 or backs off.</summary>
    internal enum V7ResultKind { Delivered, Empty, Fallback, Retry, PayloadTooLarge }

    internal sealed class V7SendResult
    {
        internal V7ResultKind Kind;
        /// <summary>Queued rows the acknowledgement removed.</summary>
        internal int Removed;
        internal string PolicyMode;
        internal int NextCheckSeconds;
        internal bool DiscardPending;
        internal int Status;
        internal TimeSpan? RetryAfter;
        internal string Detail;

        internal static V7SendResult Fallback(string detail) => new V7SendResult { Kind = V7ResultKind.Fallback, Detail = detail };
        internal static V7SendResult Retry(int status, TimeSpan? retryAfter, string detail) => new V7SendResult { Kind = V7ResultKind.Retry, Status = status, RetryAfter = retryAfter, Detail = detail };
        internal static readonly V7SendResult Empty = new V7SendResult { Kind = V7ResultKind.Empty };
    }
}
