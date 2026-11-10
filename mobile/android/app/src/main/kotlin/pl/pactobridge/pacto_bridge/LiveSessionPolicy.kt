package pl.pactobridge.pacto_bridge

/** Evidence interlock shared in intent with desktop safety.py; no runtime override. */
internal object LiveSessionPolicy {
    fun requireStoppedOperatorSession(stopped: Boolean, operatorPresent: Boolean) {
        check(stopped && operatorPresent) {
            "Test pełnej sesji wymaga zatrzymanego pasa, konsoli 0 i operatora przy fizycznym STOP."
        }
    }
    fun requireVerified() {
        throw IllegalStateException(
            "Połączenie live zablokowane: pełna sesja i przyciski fizyczne wymagają weryfikacji w PactoBridge. " +
            "Dekoder i działanie oryginalnego iConsole+ nie zastępują tego testu.")
    }
}
