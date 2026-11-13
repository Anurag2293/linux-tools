package dev.anurag.fileview

import android.app.Application
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import org.json.JSONArray

class Page(val loc: Loc) {
    var node by mutableStateOf<Node?>(null)
    var error by mutableStateOf<String?>(null)
    var loading by mutableStateOf(false)
    var readme by mutableStateOf<String?>(null)
    var sheet by mutableStateOf(0)
    var jumped = false
    val list = LazyListState()
    val scroll = ScrollState(0)
    var job: Job? = null
}

class AppModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("fileview", 0)

    val stack = mutableStateListOf<Page>()
    val recents = mutableStateListOf<String>()
    var wrap by mutableStateOf(prefs.getBoolean("wrap", true))
        private set

    init {
        prefs.getString("recents", null)?.let { s ->
            val a = JSONArray(s)
            repeat(a.length()) { recents.add(a.getString(it)) }
        }
    }

    fun restore(): Boolean {
        if (stack.isNotEmpty()) return true
        val saved = prefs.getString("stack", null) ?: return false
        val a = JSONArray(saved)
        if (a.length() == 0) return false
        repeat(a.length()) { i ->
            val o = a.getJSONObject(i)
            stack.add(Page(Loc(o.getString("p"), o.optString("f"))))
        }
        load(stack.last())
        return true
    }

    fun open(loc: Loc, replace: Boolean = false) {
        val top = stack.lastOrNull()
        if (top != null && top.loc == loc && !replace) return reload(top)
        val page = Page(loc)
        if (replace && top != null) {
            top.job?.cancel()
            stack[stack.lastIndex] = page
        } else {
            stack.add(page)
        }
        if (stack.size > 60) stack.removeAt(0)
        load(page)
        save()
    }

    fun openPath(path: String, flags: String = "") = open(Loc(path, flags))

    fun home() = open(Loc(Server.homePath))

    fun back(): Boolean {
        if (stack.size <= 1) return false
        stack.removeAt(stack.lastIndex).job?.cancel()
        stack.last().let { if (it.node == null && !it.loading) load(it) }
        save()
        return true
    }

    fun reload(page: Page) = load(page)

    fun toggleWrap() {
        wrap = !wrap
        prefs.edit().putBoolean("wrap", wrap).apply()
    }

    private fun load(page: Page) {
        page.job?.cancel()
        page.job = viewModelScope.launch {
            page.loading = true
            page.error = null
            try {
                val node = Net.node(page.loc)
                page.node = node
                if (!node.isDir) addRecent(node.path)
                if (node.isDir) loadReadme(page, node)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                page.error = Net.describe(e)
            } finally {
                page.loading = false
            }
        }
    }

    private suspend fun loadReadme(page: Page, node: Node) {
        val readme = node.entries.firstOrNull { !it.dir && it.name.lowercase() in setOf("readme.md", "context.md") }
        page.readme = readme?.let {
            try {
                Net.node(Loc(node.path + it.name)).text
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                null
            }
        }
    }

    private fun addRecent(path: String) {
        recents.remove(path)
        recents.add(0, path)
        while (recents.size > 40) recents.removeAt(recents.lastIndex)
        prefs.edit().putString("recents", JSONArray(recents.toList()).toString()).apply()
    }

    private fun save() {
        val a = JSONArray()
        stack.takeLast(30).forEach { a.put(org.json.JSONObject().put("p", it.loc.path).put("f", it.loc.flags)) }
        prefs.edit().putString("stack", a.toString()).apply()
    }
}
