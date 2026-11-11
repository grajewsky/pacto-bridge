package pl.pactobridge.pacto_bridge

import org.junit.Assert.*
import org.junit.Test

class PactoSessionTest {
    @Test fun transportPauseDuringWorkoutResumesOnlyReadPolls() {
        val r=Rig(); r.ready(); r.reply(r.zero()); r.advance()
        r.session.writeFinished(true)
        val before=r.writes.size
        r.now+=10000; r.session.tick(); r.now+=100; r.session.tick()
        assertEquals(listOf("f0 a2 01 d3 66"),r.writes.drop(before))
        assertTrue(r.errors.isEmpty())
        r.reply("f0 b2 01 d3 02 01 01 01 01 01 01 01 01 04 01 03 04 03 8f")
        assertEquals(3,r.values.last())
    }
    private class Rig {
        var now = 0L
        val writes = ArrayList<String>()
        val values = ArrayList<Int>()
        val errors = ArrayList<String>()
        var closed = false
        val session = PactoSession({ now }, { writes.add(it.pactoHex()) }, { _, _ -> },
            { values.add(it) }, { errors.add(it) }, { closed = true })
        fun reply(hex: String) { session.frame(pactoHex(hex)); session.writeFinished(true) }
        fun advance() { now += 500; session.tick() }
        fun zero() = "f0 b2 01 d3 01 01 01 01 01 01 01 01 01 01 01 01 01 02 85"
        fun ready() {
            session.begin()
            reply("f0 b0 01 d3 74"); advance()
            val replies = listOf("f0 b5 01 d3 05 7e", "f0 b3 01 d3 01 15 01 02 51 01 51 33",
                "f0 b4 01 d3 01 01 01 01 01 01 01 01 01 01 01 83", "f0 bf 01 d3 02 85")
            replies.forEach { reply(zero()); advance(); reply(it); advance() }
        }
    }

    @Test fun acknowledgedSetupIsZeroGatedAndNeverStartsMotor() {
        val r = Rig(); r.ready()
        assertEquals(PactoSession.State.READY, r.session.state)
        assertTrue(r.errors.isEmpty())
        assertFalse(r.writes.contains("f0 a5 01 d3 02 6b"))
        assertEquals(1, r.writes.count { it == "f0 a5 01 d3 04 6d" })
        assertTrue(r.writes.all { it in listOf("f0 a0 01 00 91", "f0 a2 01 d3 66",
            "f0 a5 01 d3 04 6d", "f0 a3 01 d3 01 15 01 02 51 01 51 23",
            "f0 a4 01 d3 01 01 01 01 01 01 01 01 01 01 01 73", "f0 af 01 d3 02 75") })
    }
    @Test fun wrongReplyCannotUnlockSetupAndTimeoutNeverRetries() {
        val r = Rig(); r.session.begin(); r.reply("f0 b5 01 d3 05 7e")
        r.now = 3000; r.session.tick(); r.now += 10000; r.session.tick()
        assertEquals(PactoSession.State.FAILED,r.session.state)
        assertEquals(1,r.writes.size)
    }
    @Test fun backendFailureInvalidatesSession() {
        val r = Rig(); r.session.begin(); r.session.writeFinished(false)
        assertEquals(PactoSession.State.FAILED,r.session.state)
        assertEquals(1,r.errors.size)
    }
    @Test fun nonzeroBeforeInitializationNeverCausesStopWrite() {
        val r = Rig(); r.session.begin(); r.reply("f0 b0 01 d3 74"); r.advance()
        val speed = pactoHex(r.zero()); speed[13] = 11
        speed[18] = (speed.take(18).sumOf { it.toInt() and 255 } and 255).toByte()
        r.session.frame(speed)
        assertEquals(PactoSession.State.FAILED,r.session.state)
        assertFalse(r.writes.contains("f0 a5 01 d3 04 6d"))
    }
    @Test fun consoleCountdownWithoutMovementReturnsToReadyWithoutMotorWrites() {
        val r = Rig(); r.ready(); r.reply(r.zero())
        r.session.frame(pactoHex("f0 b5 01 d3 02 7b"))
        assertEquals(PactoSession.State.START_REQUESTED,r.session.state)
        assertFalse(r.writes.contains("f0 a5 01 d3 02 6b"))
        r.now += 15000; r.session.tick()
        assertEquals(PactoSession.State.READY,r.session.state)
        assertFalse(r.writes.contains("f0 a5 01 d3 02 6b"))
    }
    @Test fun observedPhysicalStartAndStopNeverSendMotorStart() {
        val r = Rig(); r.ready(); r.reply(r.zero())
        r.session.frame(pactoHex("f0 b5 01 d3 02 7b"))
        // Exact first moving B2 from the S22+ physical START hardware trial.
        r.now += 4675
        r.session.frame(pactoHex("f0 b2 01 d3 02 01 01 01 01 01 01 01 01 04 01 03 04 03 8f"))
        assertEquals(PactoSession.State.RUNNING,r.session.state)
        assertEquals(3,r.values.last())
        assertTrue(r.errors.isEmpty())
        r.session.frame(pactoHex("f0 b5 01 d3 03 7c"))
        assertEquals(PactoSession.State.STOPPING,r.session.state)
        r.session.frame(pactoHex(r.zero())); r.now+=1000; r.session.tick()
        assertTrue(r.closed)
        assertEquals(0,r.writes.count { it == "f0 a5 01 d3 02 6b" })
        assertEquals(1,r.writes.count { it == "f0 a5 01 d3 04 6d" })
    }
    @Test fun alreadyPreparedSessionObservesMovementEvenIfConsoleEventWasMissed() {
        val r=Rig(); r.ready()
        r.session.frame(pactoHex("f0 b2 01 d3 02 01 01 01 01 01 01 01 01 04 01 03 04 03 8f"))
        assertEquals(PactoSession.State.RUNNING,r.session.state)
        assertEquals(3,r.values.last())
        assertFalse(r.writes.contains("f0 a5 01 d3 02 6b"))
    }
    @Test fun physicalStopDuringCountdownClosesAfterZeroWithoutStart() {
        val r=Rig(); r.ready(); r.reply(r.zero())
        r.session.frame(pactoHex("f0 b5 01 d3 02 7b"))
        r.session.frame(pactoHex("f0 b5 01 d3 03 7c"))
        r.session.frame(pactoHex(r.zero())); r.now+=1000; r.session.tick()
        assertTrue(r.closed)
        assertFalse(r.writes.contains("f0 a5 01 d3 02 6b"))
    }
    @Test fun fragmentsAndCoalescedRepliesValidateChecksum() {
        val f=PactoWireFrames()
        val ack=pactoHex("f0 b0 01 d3 74")
        assertTrue(f.feed(ack.copyOfRange(0,3)).isEmpty())
        assertEquals(2,f.feed(ack.copyOfRange(3,5)+ack).size)
        val bad=ack.clone(); bad[4]=0
        assertTrue(f.feed(bad).isEmpty())
        assertEquals(1,f.feed(ack).size)
    }
}
