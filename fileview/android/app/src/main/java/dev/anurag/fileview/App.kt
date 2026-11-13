package dev.anurag.fileview

import android.content.Context
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.WrapText
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

@Composable
fun AppScreen(vm: AppModel, onExit: () -> Unit) {
    var searching by rememberSaveable { mutableStateOf(false) }
    val page = vm.stack.lastOrNull() ?: return
    BackHandler(enabled = !searching) { if (!vm.back()) onExit() }
    BackHandler(enabled = searching) { searching = false }
    if (searching) {
        SearchScreen(
            vm = vm,
            root = page.node?.root ?: Server.homePath,
            onOpen = { searching = false; vm.openPath(it) },
            onClose = { searching = false },
        )
    } else {
        PageScreen(vm, page, onSearch = { searching = true })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PageScreen(vm: AppModel, page: Page, onSearch: () -> Unit) {
    val c = Fv.c
    val node = page.node
    Scaffold(
        containerColor = c.bg,
        topBar = {
            Column(Modifier.background(c.bg)) {
                TopAppBar(
                    title = {
                        Column {
                            Text(
                                node?.name ?: page.loc.path.trimEnd('/').substringAfterLast('/').ifEmpty { "/" },
                                maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 17.sp, fontWeight = FontWeight.SemiBold,
                            )
                            val sub = node?.let(::subtitle).orEmpty()
                            if (sub.isNotEmpty()) Text(sub, fontSize = 12.sp, color = c.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    },
                    navigationIcon = {
                        if (vm.stack.size > 1) {
                            IconButton(onClick = { vm.back() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
                        } else {
                            val parent = node?.parent()
                            IconButton(onClick = { parent?.let(vm::openPath) }, enabled = parent != null) {
                                Icon(Icons.Outlined.ArrowUpward, "Parent folder")
                            }
                        }
                    },
                    actions = {
                        IconButton(onClick = onSearch) { Icon(Icons.Outlined.Search, "Search files") }
                        Overflow(vm, page, node)
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg),
                )
                Crumbs(node?.path ?: page.loc.path) { vm.openPath(it) }
                HorizontalDivider(color = c.line)
                Box(Modifier.fillMaxWidth().height(2.dp)) {
                    if (page.loading && node != null) LinearProgressIndicator(Modifier.fillMaxSize(), color = c.accent, trackColor = c.bg)
                }
            }
        },
    ) { pad ->
        Box(Modifier.padding(top = pad.calculateTopPadding()).fillMaxSize()) {
            val error = page.error
            when {
                node != null -> key(page) { Content(vm, page, node) }
                error != null -> Message(Icons.Outlined.CloudOff, "Can't open this", error, "Retry") { vm.reload(page) }
                else -> Loading(page.loc.path)
            }
            if (node != null && error != null) {
                Surface(
                    Modifier.align(Alignment.BottomCenter).padding(16.dp).navigationBarsPadding(),
                    color = c.bg3, shape = MaterialTheme.shapes.medium, tonalElevation = 2.dp,
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp)) {
                        Text(error, fontSize = 13.sp, color = c.fg2, modifier = Modifier.weight(1f))
                        TextButton(onClick = { vm.reload(page) }) { Text("Retry") }
                    }
                }
            }
        }
    }
}

private fun subtitle(n: Node): String = listOfNotNull(
    if (n.isDir) "${n.entries.size + n.more} items" else n.lang.ifEmpty { null },
    if (n.isDir) null else human(n.size),
    n.lines.size.takeIf { n.kind == "code" && it > 0 }?.let { "$it lines" },
    n.branch?.let { "⎇ $it" },
).joinToString(" · ")

fun human(n: Long): String {
    var v = n.toDouble()
    for (unit in listOf("B", "KB", "MB", "GB")) {
        if (v < 1024) return if (unit == "B") "${v.toLong()} B" else "%.1f %s".format(v, unit)
        v /= 1024
    }
    return "%.1f TB".format(v)
}

@Composable
private fun Content(vm: AppModel, page: Page, node: Node) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val onLink: (String) -> Unit = { openLink(ctx, vm, node, it) }
    @Composable
    fun refreshable(body: @Composable () -> Unit) {
        @OptIn(ExperimentalMaterial3Api::class)
        PullToRefreshBox(isRefreshing = page.loading, onRefresh = { vm.reload(page) }, modifier = Modifier.fillMaxSize()) { body() }
    }
    when (node.kind) {
        "folder" -> refreshable { FolderView(vm, page, node, onLink) }
        "code" -> refreshable { CodeView(vm, page, node) }
        "markdown" -> refreshable { MarkdownPage(page, node, onLink) }
        "table", "sheet" -> SheetView(page, node)
        "pages" -> PagesView(page, node)
        "image" -> ZoomableImage(Server.url(node.path, "raw&v=${node.mtime}"), node.name)
        "video" -> VideoView(Server.url(node.path, "raw"))
        "html" -> HtmlView(Server.url(node.path, "embed"), onLink)
        else -> FileInfo(node, scope)
    }
}

fun openLink(ctx: Context, vm: AppModel, node: Node, link: String) {
    val uri = resolveLink(node, link) ?: return
    val loc = Server.locOf(uri)
    if (loc != null) vm.open(loc) else Actions.external(ctx, uri)
}

private fun resolveLink(node: Node, link: String): Uri? {
    if (link.isBlank() || link.startsWith("#")) return null
    if (Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:").containsMatchIn(link)) return Uri.parse(link)
    val cut = link.indexOfAny(charArrayOf('?', '#')).let { if (it < 0) link.length else it }
    val rel = Uri.decode(link.substring(0, cut))
    val rest = link.substring(cut)
    val dir = if (node.isDir) node.path else node.path.substring(0, node.path.lastIndexOf('/') + 1)
    val parts = ArrayList<String>()
    for (seg in ((if (rel.startsWith("/")) "" else dir) + rel).split('/')) {
        when (seg) {
            "", "." -> Unit
            ".." -> if (parts.isNotEmpty()) parts.removeAt(parts.lastIndex)
            else -> parts.add(seg)
        }
    }
    val path = "/" + parts.joinToString("/") + if (rel.endsWith("/") && parts.isNotEmpty()) "/" else ""
    return Uri.parse(Server.origin + Uri.encode(path, "/") + rest)
}

@Composable
private fun Crumbs(path: String, onOpen: (String) -> Unit) {
    val c = Fv.c
    val crumbs = remember(path) {
        val out = ArrayList<Pair<String, String>>()
        val home = Server.homePath
        var acc: String
        val rest: String
        if (path.startsWith(home)) {
            out.add("~" to home); acc = home; rest = path.removePrefix(home)
        } else {
            out.add("/" to "/"); acc = "/"; rest = path.removePrefix("/")
        }
        val segs = rest.split('/').filter { it.isNotEmpty() }
        segs.forEachIndexed { i, s ->
            val isLast = i == segs.lastIndex
            acc += s + if (!isLast || path.endsWith("/")) "/" else ""
            out.add(s to acc)
        }
        out
    }
    val state = rememberLazyListState()
    LaunchedEffect(crumbs) { state.scrollToItem(crumbs.lastIndex) }
    LazyRow(
        state = state,
        contentPadding = PaddingValues(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth().height(34.dp),
    ) {
        itemsIndexed(crumbs) { i, (label, target) ->
            if (i > 0) Text("/", color = c.faint, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 2.dp))
            val last = i == crumbs.lastIndex
            Text(
                label,
                fontSize = 13.sp,
                color = if (last) c.fg else c.muted,
                fontWeight = if (last) FontWeight.Medium else FontWeight.Normal,
                modifier = Modifier
                    .clickable(enabled = !last) { onOpen(target) }
                    .padding(horizontal = 4.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
private fun Overflow(vm: AppModel, page: Page, node: Node?) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf(false) }
    IconButton(onClick = { open = true }) { Icon(Icons.Outlined.MoreVert, "More") }
    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
        @Composable
        fun item(text: String, icon: ImageVector, action: () -> Unit) = DropdownMenuItem(
            text = { Text(text) },
            leadingIcon = { Icon(icon, null) },
            onClick = { open = false; action() },
        )
        item("Refresh", Icons.Outlined.Refresh) { vm.reload(page) }
        if (node != null) {
            item("Copy link", Icons.Outlined.ContentCopy) { Actions.copy(ctx, node.link()) }
            item("Share link", Icons.Outlined.Share) { Actions.share(ctx, node.link()) }
            sourceToggle(page, node)?.let { (label, flags) ->
                item(label, if (flags.contains("src")) Icons.Outlined.Code else Icons.Outlined.Visibility) {
                    vm.open(Loc(node.path, flags), replace = true)
                }
            }
            if (node.kind == "code") {
                item(if (vm.wrap) "Don't wrap lines" else "Wrap lines", Icons.AutoMirrored.Filled.WrapText) { vm.toggleWrap() }
            }
            if (!node.isDir) {
                item("Open with…", Icons.AutoMirrored.Outlined.OpenInNew) { Actions.openWith(ctx, scope, node) }
                item("Download", Icons.Outlined.Download) { Actions.download(ctx, node) }
            }
            item("Open in browser", Icons.Outlined.Public) { Actions.external(ctx, Uri.parse(node.link())) }
        }
        item("Home", Icons.Outlined.Home) { vm.home() }
    }
}

private fun sourceToggle(page: Page, node: Node): Pair<String, String>? {
    val ext = node.name.substringAfterLast('.', "").lowercase()
    val flags = page.loc.flags
    return when {
        ext == "docx" -> if ("pages" in flags) "Text view" to "" else "Page view" to "pages"
        ext in setOf("md", "markdown", "csv", "tsv", "html", "htm") ->
            if ("src" in flags || node.kind == "code") "Preview" to "" else "Source" to "src"
        else -> null
    }
}

@Composable
fun Message(icon: ImageVector, title: String, text: String, button: String? = null, onClick: () -> Unit = {}) {
    val c = Fv.c
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(icon, null, tint = c.faint, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(14.dp))
        Text(title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = c.fg)
        Spacer(Modifier.height(6.dp))
        Text(text, fontSize = 14.sp, color = c.muted, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        if (button != null) {
            Spacer(Modifier.height(20.dp))
            Button(onClick = onClick) { Text(button) }
        }
    }
}

@Composable
private fun Loading(path: String) {
    val c = Fv.c
    val slow = path.substringAfterLast('.').lowercase() in setOf("pptx", "odp", "pdf", "docx")
    var waited by remember { mutableStateOf(false) }
    LaunchedEffect(path) { delay(1500); waited = true }
    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        CircularProgressIndicator(color = c.accent)
        if (waited && slow) {
            Spacer(Modifier.height(16.dp))
            Text("Rendering pages on ${Server.host.substringBefore('.')}…", color = c.muted, fontSize = 13.sp)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SearchScreen(vm: AppModel, root: String, onOpen: (String) -> Unit, onClose: () -> Unit) {
    val c = Fv.c
    var q by rememberSaveable { mutableStateOf("") }
    var scopeDir by rememberSaveable { mutableStateOf(root) }
    var results by remember { mutableStateOf<List<String>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    LaunchedEffect(Unit) { focus.requestFocus() }
    LaunchedEffect(q, scopeDir) {
        error = null
        if (q.isBlank()) { results = emptyList(); return@LaunchedEffect }
        delay(160)
        busy = true
        try {
            results = Net.find(scopeDir, q).map { scopeDir + it }
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            error = Net.describe(e)
        } finally {
            busy = false
        }
    }
    Scaffold(
        containerColor = c.bg,
        topBar = {
            Column(Modifier.background(c.bg)) {
                TopAppBar(
                    navigationIcon = { IconButton(onClick = onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Close") } },
                    title = {
                        TextField(
                            value = q,
                            onValueChange = { q = it },
                            singleLine = true,
                            placeholder = { Text("Search files", color = c.faint) },
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = c.bg, unfocusedContainerColor = c.bg,
                                focusedIndicatorColor = c.bg, unfocusedIndicatorColor = c.bg, cursorColor = c.accent,
                            ),
                            keyboardOptions = KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { keyboard?.hide() }),
                            trailingIcon = {
                                if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.accent)
                                else if (q.isNotEmpty()) IconButton(onClick = { q = "" }) { Icon(Icons.Outlined.Close, "Clear") }
                            },
                            modifier = Modifier.fillMaxWidth().focusRequester(focus),
                        )
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg),
                )
                Row(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(root, Server.homePath).distinct().forEach { dir ->
                        FilterChip(
                            selected = scopeDir == dir,
                            onClick = { scopeDir = dir },
                            label = { Text(if (dir == Server.homePath) "All of ~" else shortPath(dir), maxLines = 1) },
                        )
                    }
                }
                HorizontalDivider(color = c.line)
            }
        },
    ) { pad ->
        LazyColumn(Modifier.padding(pad).fillMaxSize().imePadding()) {
            val list = if (q.isBlank()) vm.recents.toList() else results
            if (q.isBlank() && list.isNotEmpty()) item { SectionLabel("Recent") }
            error?.let { item { Text(it, color = c.muted, fontSize = 13.sp, modifier = Modifier.padding(16.dp)) } }
            if (q.isNotBlank() && !busy && list.isEmpty() && error == null) {
                item { Text("No files match \"$q\".", color = c.muted, fontSize = 14.sp, modifier = Modifier.padding(16.dp)) }
            }
            items(list, key = { it }) { path ->
                val name = path.substringAfterLast('/')
                val (icon, tint) = iconFor(name, false, c)
                Row(
                    Modifier.fillMaxWidth().clickable { onOpen(path) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(icon, null, tint = tint, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(14.dp))
                    Column {
                        Text(name, fontSize = 15.sp, color = c.fg, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(shortPath(path.substringBeforeLast('/')), fontSize = 12.sp, color = c.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

@Composable
fun SectionLabel(text: String) {
    Text(
        text.uppercase(), color = Fv.c.faint, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.8.sp,
        modifier = Modifier.padding(start = 16.dp, top = 14.dp, bottom = 6.dp),
    )
}

fun shortPath(path: String): String {
    val home = Server.homePath.trimEnd('/')
    return when {
        path == home || path == "$home/" -> "~"
        path.startsWith("$home/") -> "~/" + path.removePrefix("$home/").trimEnd('/')
        else -> path.trimEnd('/').ifEmpty { "/" }
    }
}
