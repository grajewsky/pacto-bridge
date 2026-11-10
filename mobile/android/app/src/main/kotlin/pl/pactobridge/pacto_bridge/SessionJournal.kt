package pl.pactobridge.pacto_bridge

import android.content.Context
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.util.UUID

internal class SessionJournal(context: Context) {
    private val origin = SystemClock.elapsedRealtime()
    val file = File(context.getExternalFilesDir("sessions") ?: error("Brak katalogu sesji."),
        "pacto-${System.currentTimeMillis()}-${UUID.randomUUID().toString().take(8)}.jsonl")
    fun write(row: Map<String, Any?>) {
        val value = JSONObject(row)
        value.put("elapsed_ms",SystemClock.elapsedRealtime()-origin)
        value.put("timestamp_ms",System.currentTimeMillis())
        file.appendText(value.toString()+"\n",Charsets.UTF_8)
    }
}
