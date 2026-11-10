package pl.pactobridge.pacto_bridge

import org.junit.Assert.*
import org.junit.Test

class ReceiverOrderGateTest {
    @Test fun discoveryStaysAvailableUntilReceiverPairsWithoutMakingSamples() {
        var now=0L; val g=ReceiverOrderGate { now }; g.prepare()
        now=3600000L
        assertTrue(g.preparing()); assertFalse(g.fresh())
        assertTrue(g.confirmReceiver("pc")); g.requireReceiver(); assertFalse(g.fresh())
        now+=3600000L
        assertTrue(g.preparing()); assertFalse(g.fresh())
    }
    @Test fun receiverDoesNotInventZeroOrEnableEarlyRsc() {
        var now=0L; val g=ReceiverOrderGate { now }
        g.prepare(); assertFalse(g.fresh()); assertTrue(g.preparing())
        assertTrue(g.confirmReceiver("pc")); g.requireReceiver()
        assertFalse(g.fresh()); assertTrue(g.isPeer("pc")); assertFalse(g.isPeer("other"))
        g.sample(); assertTrue(g.fresh()); assertFalse(g.preparing())
        now=3000; assertFalse(g.fresh())
    }
    @Test(expected=IllegalStateException::class)
    fun noSampleBeforeReceiverConfirms() { val g=ReceiverOrderGate { 0L }; g.prepare(); g.sample() }
    @Test
    fun receiverWaitsForRealDataWithoutInventingZero() {
        var now=0L; val g=ReceiverOrderGate { now }; g.prepare(); g.confirmReceiver("pc")
        now=3600000L; g.requireReceiver(); assertFalse(g.fresh())
    }
    @Test(expected=IllegalStateException::class)
    fun stoppedPublisherCannotRestartFromOldSourceCallback() {
        val g=ReceiverOrderGate { 0L }; g.prepare(); g.confirmReceiver("pc")
        g.sample(); g.reset(); g.sample()
    }
    @Test fun resetCannotRestoreOldReceiverOrSample() {
        val g=ReceiverOrderGate { 0L }; g.prepare(); g.confirmReceiver("pc"); g.sample(); g.reset()
        assertFalse(g.fresh()); assertFalse(g.isPeer("pc")); assertEquals(ReceiverOrderGate.Phase.IDLE,g.phase)
    }
}
