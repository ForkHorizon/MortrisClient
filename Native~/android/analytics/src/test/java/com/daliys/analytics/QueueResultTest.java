package com.daliys.analytics;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class QueueResultTest {
    @Test public void exposesQueueOperationCounts() {
        QueueResult result = new QueueResult("install", "credential", 2, 3, 4, 5, 6L);
        assertEquals(2, result.getInsertedCount());
        assertEquals(3, result.getEvictedCount());
        assertEquals(4, result.getExpiredCount());
        assertEquals(5, result.getPendingCount());
        assertEquals(6L, result.getPendingBytes());
    }
}
