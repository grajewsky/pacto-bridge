package pl.pactobridge.pacto_bridge

import org.junit.Assert.*
import org.junit.Test

class NetworkSampleGateTest {
    @Test fun discoveryWithoutSourceCannotInventZero() {
        var now=0L; val gate=NetworkSampleGate { now }; gate.prepare(); now=3600000
        assertTrue(gate.active); assertTrue(gate.waitingForSource()); assertFalse(gate.fresh())
    }
    @Test fun actualSourceDoesNotRequireAnAlreadySubscribedReceiver() {
        val gate=NetworkSampleGate { 0L }; gate.prepare(); gate.sample()
        assertTrue(gate.fresh()); assertFalse(gate.waitingForSource())
    }
    @Test fun sampleExpiresAtThreeSeconds() {
        var now=0L; val gate=NetworkSampleGate { now }; gate.prepare(); gate.sample()
        now=2999; assertTrue(gate.fresh()); now=3000; assertFalse(gate.fresh())
    }
    @Test(expected=IllegalStateException::class)
    fun oldSourceCannotRestartStoppedNetworkPublisher() {
        val gate=NetworkSampleGate { 0L }; gate.prepare(); gate.sample(); gate.reset()
        assertFalse(gate.fresh()); gate.sample()
    }
}
