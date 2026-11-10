package pl.pactobridge.pacto_bridge

/** Independently implemented from this Pacto's captured workout, not other models. */
internal class PactoWireFrames {
    private val buffer = ArrayList<Int>()
    fun reset() = buffer.clear()
    fun feed(data: ByteArray): List<ByteArray> {
        data.forEach { buffer.add(it.toInt() and 255) }
        val result = ArrayList<ByteArray>()
        val lengths = mapOf(0xb0 to 5, 0xb2 to 19, 0xb3 to 12, 0xb4 to 16, 0xb5 to 6, 0xbf to 6)
        while (buffer.size >= 2) {
            if (buffer[0] != 0xf0) { buffer.removeAt(0); continue }
            val size = lengths[buffer[1]]
            if (size == null) { buffer.removeAt(0); continue }
            if (buffer.size < size) break
            val f = buffer.take(size)
            if (f[2] == 1 && f[3] == 0xd3 && (f.dropLast(1).sum() and 255) == f.last()) {
                result.add(f.map { it.toByte() }.toByteArray())
                repeat(size) { buffer.removeAt(0) }
            } else buffer.removeAt(0)
        }
        return result
    }
}

internal fun pactoHex(s: String) = s.split(" ").map { it.toInt(16).toByte() }.toByteArray()
internal fun ByteArray.pactoHex() = joinToString(" ") { "%02x".format(it.toInt() and 255) }

/** Serialized, acknowledged session. No automatic key forwarding, reconnect or target speed. */
internal class PactoSession(
    private val clock: () -> Long,
    private val send: (ByteArray) -> Unit,
    private val event: (String, String) -> Unit,
    private val speed: (Int) -> Unit,
    private val fail: (String) -> Unit,
    private val ended: () -> Unit
) {
    enum class State { NEW, INITIALIZING, READY, START_REQUESTED, RUNNING, STOPPING, ENDED, FAILED }
    private data class Command(val request: ByteArray, val response: ByteArray?, val zero: Boolean = false)
    // Fresh-connection form captured in the first full official session and
    // independently confirmed on Android. No silent fallback or retry.
    private val identify = Command(pactoHex("f0 a0 01 00 91"), pactoHex("f0 b0 01 d3 74"))
    private val poll = Command(pactoHex("f0 a2 01 d3 66"), null)
    private val setup = listOf(
        Command(pactoHex("f0 a5 01 d3 04 6d"), pactoHex("f0 b5 01 d3 05 7e")),
        Command(pactoHex("f0 a3 01 d3 01 15 01 02 51 01 51 23"), pactoHex("f0 b3 01 d3 01 15 01 02 51 01 51 33")),
        Command(pactoHex("f0 a4 01 d3 01 01 01 01 01 01 01 01 01 01 01 73"), pactoHex("f0 b4 01 d3 01 01 01 01 01 01 01 01 01 01 01 83")),
        Command(pactoHex("f0 af 01 d3 02 75"), pactoHex("f0 bf 01 d3 02 85"))
    )
    private val commands = ArrayList<Command>()
    var state = State.NEW; private set
    private var pending: Command? = null
    private var writeComplete = false
    private var replyComplete = false
    private var deadline = 0L
    private var nextWrite = 0L
    private var lastSample: Long? = null
    private var lastSpeed: Int? = null
    private var requestDeadline = 0L
    private var endDeadline = 0L

    fun begin() {
        check(state == State.NEW)
        state(State.INITIALIZING, "Identyfikacja i przygotowanie sesji na postoju.")
        commands.add(identify)
        // Fresh B2 zero precedes EVERY setup write; never send STOP to achieve zero.
        setup.forEach { commands.add(poll.copy(zero = true)); commands.add(it) }
        nextWrite = clock()
        tick()
    }

    private fun state(value: State, message: String) { state = value; event(value.name, message) }
    private fun abort(message: String) {
        if (state in listOf(State.FAILED, State.ENDED)) return
        commands.clear(); pending = null
        state(State.FAILED, message); fail(message)
    }

    fun writeFinished(success: Boolean) {
        if (pending == null) return
        if (!success) { abort("Android odrzucił zapis BLE. Sesja unieważniona."); return }
        writeComplete = true
        completeIfReady()
    }

    fun frame(frame: ByteArray) {
        if (state in listOf(State.NEW, State.FAILED, State.ENDED)) return
        val type = frame.getOrNull(1)?.toInt()?.and(255) ?: return
        val samples = if (type == 0xb2) PactoFrames().feed(frame) else emptyList()
        if (samples.isNotEmpty()) {
            val value = samples.single()
            lastSample = clock(); lastSpeed = value
            if (state == State.INITIALIZING && value != 0) {
                abort("Wykryto ruch podczas przygotowania. Nie wysłano komendy zatrzymania; użyj fizycznego STOP.")
                return
            }
            if (state in listOf(State.READY, State.START_REQUESTED) && value > 0) {
                state(State.RUNNING, "Ruch z konsoli potwierdzony rzeczywistym B2. Most tylko odczytuje prędkość.")
            }
            val p = pending
            if (p != null && p.response == null) {
                if (p.zero && value != 0) { abort("Przygotowanie wymaga zmierzonego zera."); return }
                replyComplete = true
            }
            if (state in listOf(State.READY, State.START_REQUESTED, State.RUNNING, State.STOPPING)) speed(value)
            if (state == State.STOPPING && value == 0) {
                endDeadline = clock() + 1000
                state(State.ENDED, "Pas zatrzymany. Zamykanie sesji bez komend silnika.")
            }
        }
        val p = pending
        if (p?.response?.contentEquals(frame) == true) replyComplete = true
        if (frame.contentEquals(pactoHex("f0 b5 01 d3 02 7b")) && state == State.READY) {
            if (lastSpeed == 0 && lastSample?.let { clock()-it < 3000 } == true) {
                requestDeadline = clock()+15000
                state(State.START_REQUESTED, "Rozruch z fizycznej konsoli. Oczekiwanie na rzeczywistą prędkość; bez komendy START z mostu.")
            }
        }
        if (frame.contentEquals(pactoHex("f0 b5 01 d3 03 7c")) && state in listOf(State.RUNNING, State.START_REQUESTED)) {
            state(State.STOPPING, "Konsola zgłosiła zatrzymanie. Odczyt rzeczywistego hamowania.")
        }
        completeIfReady()
    }

    private fun completeIfReady() {
        if (!writeComplete || !replyComplete || pending == null) return
        pending = null
        if (state == State.INITIALIZING && commands.isEmpty()) {
            state(State.READY, "Most gotowy. START, prędkość i STOP obsługuj fizycznymi przyciskami konsoli.")
        }
    }

    fun tick() {
        val now = clock()
        if (state == State.FAILED || state == State.NEW) return
        if (state == State.ENDED) { if (now >= endDeadline) ended(); return }
        if (state == State.START_REQUESTED && now >= requestDeadline) {
            state(State.READY, "Nie zaobserwowano ruchu po sygnale konsoli. Most nadal odczytuje; bez komendy START.")
        }
        if (pending != null && now >= deadline) { abort("Brak potwierdzenia protokołu. Sesja zamknięta; bez ponawiania komendy."); return }
        if (pending != null || now < nextWrite) return
        val cmd = if (commands.isNotEmpty()) commands.removeAt(0) else {
            if (state in listOf(State.READY, State.START_REQUESTED, State.RUNNING, State.STOPPING)) poll else return
        }
        if (cmd in setup && (lastSpeed != 0 || lastSample?.let { now-it < 3000 } != true)) {
            abort("Brak świeżego zera przed przygotowaniem sesji."); return
        }
        pending = cmd; writeComplete = false; replyComplete = false
        deadline = now+3000; nextWrite = now+500
        send(cmd.request.clone())
    }
}
