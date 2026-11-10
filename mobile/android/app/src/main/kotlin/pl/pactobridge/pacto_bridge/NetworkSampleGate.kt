package pl.pactobridge.pacto_bridge

/** A prepared TCP server may wait without a receiver; only real source data is fresh. */
internal class NetworkSampleGate(private val clock: ()->Long) {
    var active=false; private set
    private var lastSample: Long?=null
    fun prepare() { active=true; lastSample=null }
    fun sample() { check(active) { "Network publisher is stopped" }; lastSample=clock() }
    fun clearSample() { lastSample=null }
    fun fresh()=active && lastSample?.let { clock()-it<3000 }==true
    fun ageMs(): Long? = lastSample?.let { (clock()-it).coerceAtLeast(0) }
    fun canPublish()=active && lastSample!=null
    fun waitingForSource()=active && lastSample==null
    fun reset() { active=false; lastSample=null }
}
