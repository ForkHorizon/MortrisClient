package com.daliys.analytics;

/** Immutable JNI-friendly result for queue operations. */
public final class QueueResult {
    private final String installationId;
    private final String installationCredential;
    private final int insertedCount;
    private final int evictedCount;
    private final int expiredCount;
    private final int pendingCount;
    private final long pendingBytes;

    QueueResult(String installationId, String installationCredential, int insertedCount,
                int evictedCount, int expiredCount, int pendingCount, long pendingBytes) {
        this.installationId = installationId;
        this.installationCredential = installationCredential;
        this.insertedCount = insertedCount;
        this.evictedCount = evictedCount;
        this.expiredCount = expiredCount;
        this.pendingCount = pendingCount;
        this.pendingBytes = pendingBytes;
    }

    public String getInstallationId() { return installationId; }
    public String getInstallationCredential() { return installationCredential; }
    public int getInsertedCount() { return insertedCount; }
    public int getEvictedCount() { return evictedCount; }
    public int getExpiredCount() { return expiredCount; }
    public int getPendingCount() { return pendingCount; }
    public long getPendingBytes() { return pendingBytes; }
}
