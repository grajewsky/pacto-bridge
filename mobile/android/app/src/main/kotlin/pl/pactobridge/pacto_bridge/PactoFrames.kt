package pl.pactobridge.pacto_bridge

import kotlin.math.roundToInt

/** Only captured B2 telemetry yields a speed. No key-event/motor interpretation. */
internal class PactoFrames {
    private val buffer = ArrayList<Int>()
    fun reset() = buffer.clear()
    fun feed(data: ByteArray): List<Int> {
        data.forEach { buffer.add(it.toInt() and 255) }
        val result = ArrayList<Int>()
        while (buffer.size >= 19) {
            val f = buffer.take(19)
            if (f.take(4) == listOf(240, 178, 1, 211) &&
                (f.take(18).sum() and 255) == f[18] &&
                f.subList(4,18).all { it != 0 } && f[12] in 1..100 && f[13] in 1..100) {
                result.add((f[12]-1)*100+f[13]-1)
                repeat(19) { buffer.removeAt(0) }
            } else buffer.removeAt(0)
        }
        return result
    }
}

internal fun rscPacket(tenthsKmh: Int): ByteArray {
    require(tenthsKmh >= 0)
    val speed = (tenthsKmh / 10.0 / 3.6 * 256).roundToInt()
    require(speed <= 65535)
    // Flags=0, uint16 speed in 1/256 m/s, cadence=0 unavailable placeholder.
    return byteArrayOf(0, speed.toByte(), (speed shr 8).toByte(), 0)
}
