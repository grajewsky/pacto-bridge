package pl.pactobridge.pacto_bridge

import org.junit.Assert.*
import org.junit.Test

class PactoFramesTest {
    @Test(expected = IllegalStateException::class)
    fun publicNativeConnectionCannotBypassEvidenceInterlock() { LiveSessionPolicy.requireVerified() }
    @Test(expected = IllegalStateException::class)
    fun movingBeltCannotOpenValidationSession() { LiveSessionPolicy.requireStoppedOperatorSession(false,true) }
    @Test(expected = IllegalStateException::class)
    fun absentOperatorCannotOpenValidationSession() { LiveSessionPolicy.requireStoppedOperatorSession(true,false) }

    private fun hex(s: String) = s.trim().split(" ").map { it.toInt(16).toByte() }.toByteArray()

    @Test fun realWorkoutFragmentsAndPhysicalStop() {
        val stream = javaClass.getResourceAsStream("/workout.hex")!!
        val decoder = PactoFrames()
        val values = ArrayList<Int>()
        stream.bufferedReader().useLines { lines -> lines.forEach { line ->
            val bytes = hex(line)
            values.addAll(decoder.feed(bytes.copyOfRange(0,7)))
            values.addAll(decoder.feed(bytes.copyOfRange(7,bytes.size)))
        } }
        assertEquals(196, values.size)
        assertEquals(0, values.first())
        assertEquals(0, values.last())
        assertTrue(values.containsAll(listOf(2,5,7,10,20)))
        assertEquals(20, values.maxOrNull())
    }

    @Test fun badFramesAndControlsCannotInventZero() {
        val decoder = PactoFrames()
        val frame = hex("f0 b2 01 d3 01 01 01 01 01 01 01 01 01 01 01 01 01 02 85")
        val bad = frame.clone(); bad[18] = 0
        assertTrue(decoder.feed(bad).isEmpty())
        assertTrue(decoder.feed(hex("f0 b5 01 d3 03 7c")).isEmpty())
        assertEquals(listOf(0), decoder.feed(frame))
        decoder.feed(frame.copyOfRange(0,10)); decoder.reset()
        assertTrue(decoder.feed(frame.copyOfRange(10,19)).isEmpty())
    }

    @Test fun rscUsesMeasuredSpeedNotCadence() {
        assertArrayEquals(byteArrayOf(0,0,0,0), rscPacket(0))
        assertArrayEquals(byteArrayOf(0,71,0,0), rscPacket(10))
        assertArrayEquals(byteArrayOf(0,142.toByte(),0,0), rscPacket(20))
        assertArrayEquals(byteArrayOf(0,0,1,0), rscPacket(36))
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeSpeedRejected() { rscPacket(-1) }

    @Test(expected = IllegalArgumentException::class)
    fun rscOverflowRejected() { rscPacket(9999) }
}
