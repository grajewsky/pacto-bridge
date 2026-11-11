package pl.pactobridge.pacto_bridge

import org.junit.Assert.*
import org.junit.Test

class NotificationRecoveryTest {
    @Test fun repairsOnlyEstablishedTelemetryAfterThreeSecondsAndWhenGattIdle() {
        var now=0L; val r=NotificationRecovery { now }
        now=60000; assertFalse(r.startIfDue(true))
        r.sample(); now+=2999; assertFalse(r.startIfDue(true))
        now++; assertFalse(r.startIfDue(false)); assertTrue(r.startIfDue(true))
        assertFalse(r.startIfDue(true)); assertEquals(1,r.attempts)
    }
    @Test fun threeAttemptsAreSpacedAndDoNotRetryForever() {
        var now=0L; val r=NotificationRecovery { now }; r.sample()
        now=3000; assertTrue(r.startIfDue(true)); r.finish()
        now=7999; assertFalse(r.startIfDue(true))
        now=8000; assertTrue(r.startIfDue(true)); r.finish()
        now=13000; assertTrue(r.startIfDue(true)); r.finish()
        assertFalse(r.exhausted()); now=16000; assertTrue(r.exhausted())
        now=3600000; assertFalse(r.startIfDue(true))
    }
    @Test fun realSampleRestoresBudgetAndStopDiscardsPreviousSession() {
        var now=0L; val r=NotificationRecovery { now }; r.sample()
        now=3000; r.startIfDue(true); r.finish()
        r.sample(); assertEquals(0,r.attempts); assertFalse(r.exhausted())
        now+=3000; assertTrue(r.startIfDue(true))
        r.reset(); now+=60000
        assertFalse(r.active); assertFalse(r.startIfDue(true))
    }
}
