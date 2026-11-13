package dev.anurag.fileview

import android.net.Uri
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

object Server {
    private val home: Uri = Uri.parse(BuildConfig.HOME_URL)
    val host: String = home.host!!
    val origin = "${home.scheme}://$host"
    val homePath: String = (home.path ?: "/").let { if (it.endsWith("/")) it else "$it/" }

    fun url(path: String, query: String? = null): String =
        origin + Uri.encode(path, "/") + (if (query.isNullOrEmpty()) "" else "?$query")

    fun locOf(uri: Uri): Loc? {
        if (uri.scheme != "https" || uri.host != host) return null
        var path = uri.path.orEmpty().ifEmpty { "/" }
        if (path == "/") path = homePath
        val query = uri.encodedQuery.orEmpty()
        val flags = listOf("src", "pages").filter { Regex("(^|&)$it(=|&|$)").containsMatchIn(query) }
        Regex("^L-?(\\d+)(?:-L?(\\d+))?$").find(uri.fragment.orEmpty())?.let { m ->
            path += ":" + m.groupValues[1] + m.groupValues[2].let { if (it.isEmpty()) "" else "-$it" }
        }
        return Loc(path, flags.joinToString("&"))
    }
}

data class Loc(val path: String, val flags: String = "")

class ApiError(message: String) : Exception(message)

class Entry(val name: String, val dir: Boolean, val size: Long, val mtime: Long)

class Cell(
    val text: String,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val bg: Color? = null,
    val fg: Color? = null,
    val align: TextAlign? = null,
    val colSpan: Int = 1,
)

class GridRow(val label: String, val cells: List<Cell?>)

class Grid(val name: String, val header: List<String>, val rows: List<GridRow>, val note: String)

class Node(o: JSONObject) {
    val path: String = o.getString("path")
    val name: String = o.getString("name")
    val kind: String = o.getString("kind")
    val size: Long = o.optLong("size")
    val mtime: Long = o.optLong("mtime")
    val line: Int? = if (o.isNull("line")) null else o.getInt("line")
    val end: Int? = if (o.isNull("end")) null else o.getInt("end")
    val root: String = o.optString("root", Server.homePath)
    val branch: String? = o.optJSONObject("git")?.optString("branch")
    val public: String = o.optString("public", Server.origin)
    val lang: String = o.optString("lang")
    val note: String = if (o.isNull("note")) "" else o.optString("note")
    val text: String = o.optString("text")
    val count: Int = o.optInt("count")
    val more: Int = o.optInt("more")
    val isDir get() = kind == "folder"

    val entries: List<Entry> = o.optJSONArray("entries")?.let { a ->
        List(a.length()) { i ->
            val e = a.getJSONObject(i)
            Entry(e.getString("n"), e.getBoolean("d"), e.optLong("s"), e.optLong("m"))
        }
    } ?: emptyList()

    val lines: List<Array<String>> = o.optJSONArray("lines")?.let { a ->
        List(a.length()) { i ->
            val l = a.getJSONArray(i)
            Array(l.length()) { j -> l.getString(j) }
        }
    } ?: emptyList()

    val grids: List<Grid> = when (kind) {
        "sheet" -> o.getJSONArray("sheets").let { a -> List(a.length()) { sheet(a.getJSONObject(it)) } }
        "table" -> listOf(csv(o.getJSONArray("rows")))
        else -> emptyList()
    }

    private fun csv(a: JSONArray): Grid {
        val rows = List(a.length()) { i -> a.getJSONArray(i).let { r -> List(r.length()) { r.getString(it) } } }
        val width = rows.maxOfOrNull { it.size } ?: 0
        val header = rows.firstOrNull().orEmpty().let { it + List(width - it.size) { "" } }
        val body = rows.drop(1).mapIndexed { i, r -> GridRow("${i + 1}", r.map { Cell(it) } + List(width - r.size) { Cell("") }) }
        val note = if (rows.size > 1000) "Showing the first 1000 rows." else ""
        return Grid("", header, body, note)
    }

    private fun sheet(s: JSONObject): Grid {
        val cols = s.getJSONArray("cols").let { a -> List(a.length()) { a.getString(it) } }
        val rows = s.getJSONArray("rows").let { a ->
            List(a.length()) { i ->
                val r = a.getJSONObject(i)
                val cells = r.getJSONArray("c")
                GridRow(r.getInt("n").toString(), List(cells.length()) { j -> cell(cells.opt(j)) })
            }
        }
        return Grid(s.getString("name"), cols, rows, s.optString("note"))
    }

    private fun cell(v: Any?): Cell? = when (v) {
        null, JSONObject.NULL -> null
        is String -> Cell(v)
        is JSONObject -> Cell(
            text = v.optString("t"),
            bold = v.has("b"),
            italic = v.has("i"),
            bg = v.optString("bg").takeIf { it.isNotEmpty() }?.let(::hex),
            fg = v.optString("fg").takeIf { it.isNotEmpty() }?.let(::hex),
            align = when (v.optString("a")) {
                "center" -> TextAlign.Center
                "right" -> TextAlign.End
                "left" -> TextAlign.Start
                else -> if (v.has("n")) TextAlign.End else null
            },
            colSpan = v.optInt("cs", 1),
        )
        else -> Cell(v.toString())
    }

    private fun hex(s: String) = Color(android.graphics.Color.parseColor(s))

    fun link(): String = public + Uri.encode(path, "/") +
        (line?.let { ":$it" + (end?.takeIf { e -> e != it }?.let { e -> "-$e" } ?: "") } ?: "")

    fun parent(): String? {
        val trimmed = path.trimEnd('/')
        if (trimmed.isEmpty()) return null
        return trimmed.substring(0, trimmed.lastIndexOf('/') + 1)
    }
}

object Net {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(240, TimeUnit.SECONDS)
        .build()

    private fun get(url: String): JSONObject {
        client.newCall(Request.Builder().url(url).build()).execute().use { r ->
            val body = r.body?.string().orEmpty()
            val json = try {
                JSONObject(body)
            } catch (e: Exception) {
                throw ApiError(if (r.isSuccessful) "Unexpected reply from fileview." else "HTTP ${r.code}")
            }
            if (!r.isSuccessful) throw ApiError(json.optString("error", "HTTP ${r.code}"))
            return json
        }
    }

    suspend fun node(loc: Loc): Node = withContext(Dispatchers.IO) {
        Node(get(Server.url(loc.path, listOf("api", loc.flags).filter { it.isNotEmpty() }.joinToString("&"))))
    }

    suspend fun find(dir: String, q: String): List<String> = withContext(Dispatchers.IO) {
        val a = get(Server.url(dir, "find=" + Uri.encode(q))).getJSONArray("results")
        List(a.length()) { a.getString(it) }
    }

    suspend fun fetch(path: String, dest: File) = withContext(Dispatchers.IO) {
        client.newCall(Request.Builder().url(Server.url(path, "raw")).build()).execute().use { r ->
            if (!r.isSuccessful) throw ApiError("HTTP ${r.code}")
            dest.parentFile?.mkdirs()
            dest.outputStream().use { out -> r.body!!.byteStream().copyTo(out) }
        }
    }

    fun describe(e: Throwable): String = when (e) {
        is ApiError -> e.message ?: "Error"
        is IOException -> "Can't reach ${Server.host}. Check that Tailscale is connected and the machine is awake."
        else -> e.message ?: e.javaClass.simpleName
    }
}
