package pl.pactobridge.pacto_bridge

/** The native validated B2 receiver is the only caller allowed to supply speed. */
internal interface LivePublisher {
    fun requireReceiver()
    fun canWaitForSource(): Boolean
    fun onLiveMeasurement(tenthsKmh: Int)
    fun onTelemetryStale() {}
    fun stop()
}
