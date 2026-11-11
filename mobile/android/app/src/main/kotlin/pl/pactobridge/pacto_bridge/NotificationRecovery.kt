package pl.pactobridge.pacto_bridge

/** Bounded subscription repair; a valid B2 sample, not a write ACK, resets it. */
internal class NotificationRecovery(private val clock: () -> Long) {
    private var lastSample: Long? = null
    private var lastAttempt: Long? = null
    var attempts=0; private set
    var active=false; private set
    fun sample() { lastSample=clock(); attempts=0; lastAttempt=null }
    fun startIfDue(transportIdle: Boolean): Boolean {
        val now=clock()
        if (!transportIdle || active || attempts>=3 ||
            lastSample?.let { now-it>=3000 }!=true ||
            lastAttempt?.let { now-it<5000 }==true) return false
        attempts++; lastAttempt=now; active=true
        return true
    }
    fun finish() { active=false }
    fun exhausted()= !active && attempts>=3 &&
        lastAttempt?.let { clock()-it>=3000 }==true
    fun reset() { lastSample=null; lastAttempt=null; attempts=0; active=false }
}
