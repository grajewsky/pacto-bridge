package pl.pactobridge.pacto_bridge

/** Receiver-first discovery never invents a speed sample. */
internal class ReceiverOrderGate(private val clock: () -> Long) {
    enum class Phase { IDLE, WAITING, RECEIVER_READY, LIVE }
    var phase = Phase.IDLE; private set
    private var sampleTime: Long? = null
    private var peer: String? = null

    fun prepare() { reset(); phase=Phase.WAITING }
    fun confirmReceiver(address: String): Boolean {
        if (phase!=Phase.WAITING) return false
        peer=address; phase=Phase.RECEIVER_READY
        return true
    }
    fun requireReceiver() {
        check(phase==Phase.RECEIVER_READY && peer!=null) {
            "Najpierw sparuj telefon jako źródło prędkości w Zwift."
        }
    }
    fun sample() {
        check(phase in listOf(Phase.RECEIVER_READY,Phase.LIVE)) { "Brak potwierdzonego odbiornika." }
        if (phase==Phase.RECEIVER_READY) requireReceiver()
        phase=Phase.LIVE; sampleTime=clock()
    }
    fun fresh() = phase==Phase.LIVE && sampleTime?.let { clock()-it<3000 }==true
    fun preparing() = phase in listOf(Phase.WAITING,Phase.RECEIVER_READY)
    fun isPeer(address: String) = peer==address
    fun reset() { phase=Phase.IDLE; sampleTime=null; peer=null }
}
