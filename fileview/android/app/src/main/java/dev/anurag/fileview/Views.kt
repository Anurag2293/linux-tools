package dev.anurag.fileview

import android.annotation.SuppressLint
import android.text.format.DateUtils
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.DisableSelection
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Article
import androidx.compose.material.icons.automirrored.outlined.InsertDriveFile
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import kotlinx.coroutines.CoroutineScope

/* ---------- icons ---------- */

fun iconFor(name: String, dir: Boolean, c: Palette): Pair<ImageVector, Color> {
    if (dir) return Icons.Outlined.Folder to c.muted
    val ext = name.substringAfterLast('.', "").lowercase()
    return when (ext) {
        "md", "markdown", "rst", "txt" -> Icons.AutoMirrored.Outlined.Article to c.fg2
        "py", "sh", "bash", "zsh" -> Icons.Outlined.Terminal to c.str
        "cpp", "cc", "c", "h", "hpp", "js", "mjs", "ts", "tsx", "go", "rs", "java", "kt", "kts" -> Icons.Outlined.Code to c.fn
        "json", "yaml", "yml", "xml", "toml", "launch", "test", "xacro", "urdf", "beh", "pml", "repos" -> Icons.Outlined.DataObject to c.num
        "csv", "tsv", "xlsx", "xlsm", "ods" -> Icons.Outlined.TableChart to c.str
        "html", "htm", "css" -> Icons.Outlined.Html to c.kw
        "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp" -> Icons.Outlined.Image to c.fn
        "mp4", "m4v", "webm", "mov", "ogv" -> Icons.Outlined.Movie to c.fn
        "pptx", "odp" -> Icons.Outlined.Slideshow to c.type
        "pdf" -> Icons.Outlined.PictureAsPdf to c.accent
        "docx", "odt" -> Icons.Outlined.Description to c.type
        "zip", "gz", "tar", "bag", "db3", "mcap" -> Icons.Outlined.FolderZip to c.muted
        "log", "out" -> Icons.Outlined.Notes to c.muted
        else -> when (name) {
            "Makefile", "CMakeLists.txt", "Dockerfile", "Tiltfile" -> Icons.Outlined.Terminal to c.str
            else -> Icons.AutoMirrored.Outlined.InsertDriveFile to c.muted
        }
    }
}

/* ---------- folder ---------- */

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun FolderView(vm: AppModel, page: Page, node: Node, onLink: (String) -> Unit) {
    val c = Fv.c
    val ctx = LocalContext.current
    val now = remember(node) { System.currentTimeMillis() }
    LazyColumn(state = page.list, modifier = Modifier.fillMaxSize(), contentPadding = WindowInsets.navigationBars.asPaddingValues()) {
        if (node.entries.isEmpty()) item { Text("This folder is empty.", color = c.muted, modifier = Modifier.padding(20.dp)) }
        items(node.entries, key = { it.name }) { e ->
            val (icon, tint) = iconFor(e.name, e.dir, c)
            val target = node.path + e.name + if (e.dir) "/" else ""
            Row(
                Modifier
                    .fillMaxWidth()
                    .combinedClickable(
                        onClick = { vm.openPath(target) },
                        onLongClick = { Actions.copy(ctx, node.public + android.net.Uri.encode(target, "/")) },
                    )
                    .padding(horizontal = 16.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(icon, null, tint = tint, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(e.name, fontSize = 15.sp, color = c.fg, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val ago = DateUtils.getRelativeTimeSpanString(e.mtime * 1000, now, DateUtils.MINUTE_IN_MILLIS, DateUtils.FORMAT_ABBREV_RELATIVE)
                    Text(
                        if (e.dir) ago.toString() else "${human(e.size)} · $ago",
                        fontSize = 12.sp, color = c.muted, maxLines = 1,
                    )
                }
            }
        }
        if (node.more > 0) item { Text("${node.more} more not shown", color = c.muted, fontSize = 13.sp, modifier = Modifier.padding(16.dp)) }
        page.readme?.let { md ->
            item {
                HorizontalDivider(color = c.line, modifier = Modifier.padding(top = 8.dp))
                SectionLabel(node.entries.first { it.name.lowercase() in setOf("readme.md", "context.md") }.name)
                MarkdownText(md, node, onLink, Modifier.padding(horizontal = 16.dp).padding(bottom = 24.dp))
            }
        }
    }
}

/* ---------- code ---------- */

private val Mono = FontFamily.Monospace

private fun annotate(tokens: Array<String>, c: Palette): AnnotatedString = buildAnnotatedString {
    var i = 0
    while (i + 1 < tokens.size) {
        val text = tokens[i + 1].replace("\t", "    ")
        val style = c.token(tokens[i])
        if (style == null) append(text) else withStyle(style) { append(text) }
        i += 2
    }
}

@Composable
fun CodeView(vm: AppModel, page: Page, node: Node) {
    val c = Fv.c
    val ctx = LocalContext.current
    val lines = node.lines
    val digits = lines.size.toString().length
    val style = TextStyle(fontFamily = Mono, fontSize = 12.5.sp, lineHeight = 18.sp, color = c.fg)
    val numStyle = style.copy(color = c.faint)
    val range = node.line?.let { it..(node.end ?: it) }
    LaunchedEffect(node) {
        if (!page.jumped && node.line != null) {
            page.jumped = true
            page.list.scrollToItem((node.line - 4).coerceAtLeast(0))
        }
    }
    val measurer = rememberTextMeasurer()
    val charPx = remember(style) { measurer.measure("0000000000", style).size.width / 10f }
    val density = LocalDensity.current
    val wrap = vm.wrap
    val longest = remember(lines) { lines.maxOfOrNull { l -> var n = 0; var i = 1; while (i < l.size) { n += l[i].length + l[i].count { it == '\t' } * 3; i += 2 }; n } ?: 0 }
    val width = with(density) { (charPx * (longest + digits + 4)).toDp() + 32.dp }

    @Composable
    fun list(modifier: Modifier) {
        SelectionContainer {
            LazyColumn(state = page.list, modifier = modifier, contentPadding = PaddingValues(top = 6.dp, bottom = 80.dp)) {
                if (node.note.isNotEmpty()) item { Note(node.note) }
                items(lines.size) { i ->
                    val n = i + 1
                    val text = remember(lines[i], c) { annotate(lines[i], c) }
                    val hit = range != null && n in range
                    Row(Modifier.fillMaxWidth().background(if (hit) c.sel else Color.Transparent)) {
                        Box(Modifier.width(3.dp).height(18.dp).background(if (hit) c.selEdge else Color.Transparent))
                        DisableSelection {
                            Text(
                                n.toString().padStart(digits),
                                style = numStyle,
                                modifier = Modifier
                                    .clickable { Actions.copy(ctx, node.public + android.net.Uri.encode(node.path, "/") + ":$n", "Line link") }
                                    .padding(start = 6.dp, end = 12.dp),
                            )
                        }
                        Text(text, style = style, softWrap = wrap, modifier = if (wrap) Modifier.weight(1f).padding(end = 8.dp) else Modifier)
                    }
                }
            }
        }
    }
    if (wrap) list(Modifier.fillMaxSize())
    else Box(Modifier.fillMaxSize().horizontalScroll(rememberScrollState())) { list(Modifier.width(width).fillMaxHeight()) }
}

@Composable
fun Note(text: String) {
    val c = Fv.c
    Text(
        text, fontSize = 13.sp, color = c.fg2,
        modifier = Modifier.fillMaxWidth().padding(12.dp).background(c.bg3, RoundedCornerShape(6.dp)).padding(10.dp),
    )
}

/* ---------- markdown page ---------- */

@Composable
fun MarkdownPage(page: Page, node: Node, onLink: (String) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(page.scroll).navigationBarsPadding()) {
        if (node.note.isNotEmpty()) Note(node.note)
        MarkdownText(node.text, node, onLink, Modifier.padding(horizontal = 16.dp, vertical = 12.dp).padding(bottom = 48.dp))
    }
}

/* ---------- sheets and CSV ---------- */

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun SheetView(page: Page, node: Node) {
    val c = Fv.c
    val grids = node.grids
    if (grids.isEmpty()) return Message(Icons.Outlined.TableChart, "Empty", "Nothing to show.")
    val index = page.sheet.coerceIn(0, grids.lastIndex)
    Column(Modifier.fillMaxSize().navigationBarsPadding()) {
        Box(Modifier.weight(1f)) { key(index) { GridView(grids[index]) } }
        if (grids.size > 1) {
            HorizontalDivider(color = c.line)
            ScrollableTabRow(
                selectedTabIndex = index, containerColor = c.bg2, contentColor = c.fg, edgePadding = 8.dp,
            ) {
                grids.forEachIndexed { i, g ->
                    Tab(selected = i == index, onClick = { page.sheet = i }, text = { Text(g.name, maxLines = 1) })
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun GridView(grid: Grid) {
    val c = Fv.c
    val widths = remember(grid) {
        val n = grid.header.size
        IntArray(n) { col ->
            var chars = grid.header[col].length
            for (r in grid.rows.take(300)) {
                val cell = r.cells.getOrNull(col) ?: continue
                if (cell.colSpan == 1) chars = maxOf(chars, cell.text.lines().maxOfOrNull { it.length } ?: 0)
            }
            (chars * 7.4 + 20).toInt().coerceIn(48, 280)
        }
    }
    val labelWidth = ((grid.rows.lastOrNull()?.label?.length ?: 1) * 8 + 18).coerceAtLeast(34)
    val total = labelWidth + widths.sum()
    val cellText = TextStyle(fontSize = 13.sp, lineHeight = 17.sp, color = c.fg)
    val headStyle = cellText.copy(color = c.muted, fontWeight = FontWeight.Medium, fontSize = 12.sp)
    Column(Modifier.fillMaxSize()) {
        if (grid.note.isNotEmpty()) Note(grid.note)
        Box(Modifier.fillMaxSize().horizontalScroll(rememberScrollState())) {
            LazyColumn(Modifier.width(total.dp).fillMaxHeight(), state = rememberLazyListState()) {
                stickyHeader {
                    Row(Modifier.background(c.bg3)) {
                        GridBox(labelWidth, c.bg3) {}
                        grid.header.forEachIndexed { i, h ->
                            GridBox(widths[i], c.bg3) { Text(h, style = headStyle, maxLines = 2, overflow = TextOverflow.Ellipsis) }
                        }
                    }
                }
                items(grid.rows.size) { r ->
                    val row = grid.rows[r]
                    Row(Modifier.height(IntrinsicSize.Min)) {
                        GridBox(labelWidth, c.bg2) { Text(row.label, style = headStyle) }
                        var skip = 0
                        for (i in widths.indices) {
                            if (skip > 0) { skip--; continue }
                            val cell = row.cells.getOrNull(i)
                            val span = (cell?.colSpan ?: 1).coerceAtMost(widths.size - i)
                            skip = span - 1
                            var w = 0
                            for (k in i until i + span) w += widths[k]
                            GridBox(w, cell?.bg ?: c.bg) {
                                if (cell != null && cell.text.isNotEmpty()) Text(
                                    cell.text,
                                    style = cellText.copy(
                                        color = cell.fg ?: if (cell.bg != null) Color.Black else c.fg,
                                        fontWeight = if (cell.bold) FontWeight.SemiBold else null,
                                        fontStyle = if (cell.italic) FontStyle.Italic else null,
                                        textAlign = cell.align ?: androidx.compose.ui.text.style.TextAlign.Start,
                                    ),
                                    maxLines = 4, overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth(),
                                )
                            }
                        }
                    }
                }
                item { Spacer(Modifier.height(48.dp)) }
            }
        }
    }
}

@Composable
private fun GridBox(width: Int, bg: Color, content: @Composable BoxScope.() -> Unit) {
    Box(
        Modifier.width(width.dp).fillMaxHeight().heightIn(min = 30.dp).background(bg)
            .border(0.5.dp, Fv.c.line2).padding(horizontal = 7.dp, vertical = 6.dp),
        contentAlignment = Alignment.CenterStart,
        content = content,
    )
}

/* ---------- slides, PDF and page images ---------- */

@Composable
fun PagesView(page: Page, node: Node) {
    val c = Fv.c
    val ext = node.name.substringAfterLast('.').lowercase()
    val what = if (ext in setOf("pptx", "odp")) "Slide" else "Page"
    var viewer by remember { mutableStateOf<Int?>(null) }
    val ratios = remember(node) { mutableStateMapOf<Int, Float>() }
    val guess = if (what == "Slide") 16f / 9f else 1f / 1.414f
    fun url(i: Int) = Server.url(node.path, "page=${i + 1}&v=${node.mtime}")
    LazyColumn(
        state = page.list,
        modifier = Modifier.fillMaxSize().background(c.bg2),
        contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 48.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        items(node.count) { i ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                AsyncImage(
                    model = url(i),
                    contentDescription = "$what ${i + 1}",
                    contentScale = ContentScale.FillWidth,
                    onSuccess = { s ->
                        val d = s.result.drawable
                        if (d.intrinsicHeight > 0) ratios[i] = d.intrinsicWidth.toFloat() / d.intrinsicHeight
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(ratios[i] ?: guess)
                        .clip(RoundedCornerShape(6.dp))
                        .background(if (c.dark) Color(0xFF202020) else Color.White)
                        .border(0.5.dp, c.line2, RoundedCornerShape(6.dp))
                        .clickable { viewer = i },
                )
                Text("$what ${i + 1} / ${node.count}", fontSize = 12.sp, color = c.muted, modifier = Modifier.padding(top = 6.dp))
            }
        }
    }
    viewer?.let { start ->
        Dialog(onDismissRequest = { viewer = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            val pager = rememberPagerState(start) { node.count }
            Box(Modifier.fillMaxSize().background(Color.Black)) {
                HorizontalPager(state = pager, modifier = Modifier.fillMaxSize(), beyondViewportPageCount = 1) { i ->
                    ZoomableImage(url(i), "$what ${i + 1}", dark = true)
                }
                Text(
                    "${pager.currentPage + 1} / ${node.count}", color = Color.White, fontSize = 13.sp,
                    modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(16.dp)
                        .background(Color(0x99000000), RoundedCornerShape(12.dp)).padding(horizontal = 10.dp, vertical = 4.dp),
                )
                IconButton(onClick = { viewer = null }, modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(8.dp)) {
                    Icon(Icons.Outlined.Close, "Close", tint = Color.White)
                }
            }
        }
    }
}

/* ---------- images ---------- */

@Composable
fun ZoomableImage(model: Any, description: String, dark: Boolean = false) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    Box(
        Modifier
            .fillMaxSize()
            .clipToBounds()
            .background(if (dark) Color.Black else Fv.c.bg2)
            .pointerInput(Unit) {
                detectTapGestures(onDoubleTap = { p ->
                    if (scale > 1f) {
                        scale = 1f; offset = Offset.Zero
                    } else {
                        scale = 2.5f
                        val center = Offset(size.width / 2f, size.height / 2f)
                        val max = Offset(size.width * 0.75f, size.height * 0.75f)
                        val o = (center - p) * 1.5f
                        offset = Offset(o.x.coerceIn(-max.x, max.x), o.y.coerceIn(-max.y, max.y))
                    }
                })
            }
            .pointerInput(Unit) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    do {
                        val event = awaitPointerEvent()
                        val pinch = event.changes.count { it.pressed } > 1
                        if (pinch || scale > 1f) {
                            scale = (scale * event.calculateZoom()).coerceIn(1f, 8f)
                            val pan = event.calculatePan()
                            val max = Offset(size.width * (scale - 1) / 2f, size.height * (scale - 1) / 2f)
                            offset = if (scale == 1f) Offset.Zero else Offset(
                                (offset.x + pan.x).coerceIn(-max.x, max.x),
                                (offset.y + pan.y).coerceIn(-max.y, max.y),
                            )
                            event.changes.forEach { if (it.positionChanged()) it.consume() }
                        }
                    } while (event.changes.any { it.pressed })
                }
            },
    ) {
        AsyncImage(
            model = model,
            contentDescription = description,
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize().graphicsLayer {
                scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y
            },
        )
    }
}

/* ---------- video ---------- */

@Composable
fun VideoView(url: String) {
    val ctx = LocalContext.current
    val player = remember(url) {
        ExoPlayer.Builder(ctx).build().apply {
            setMediaItem(MediaItem.fromUri(url))
            prepare()
        }
    }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(player, owner) {
        val observer = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_PAUSE) player.pause() }
        owner.lifecycle.addObserver(observer)
        onDispose {
            owner.lifecycle.removeObserver(observer)
            player.release()
        }
    }
    AndroidView(
        factory = { PlayerView(it).apply { this.player = player; setBackgroundColor(android.graphics.Color.BLACK) } },
        modifier = Modifier.fillMaxSize().navigationBarsPadding(),
    )
}

/* ---------- HTML pages ---------- */

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun HtmlView(url: String, onLink: (String) -> Unit) {
    AndroidView(
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.useWideViewPort = true
                settings.loadWithOverviewMode = true
                settings.builtInZoomControls = true
                settings.displayZoomControls = false
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        val u = request.url
                        if (u.host == Server.host && u.encodedQuery?.contains("embed") == true) return false
                        if (!request.isForMainFrame) return false
                        onLink(u.toString())
                        return true
                    }
                }
                loadUrl(url)
            }
        },
        onRelease = { it.destroy() },
        modifier = Modifier.fillMaxSize().navigationBarsPadding(),
    )
}

/* ---------- other files ---------- */

@Composable
fun FileInfo(node: Node, scope: CoroutineScope) {
    val c = Fv.c
    val ctx = LocalContext.current
    val (icon, tint) = iconFor(node.name, false, c)
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(icon, null, tint = tint, modifier = Modifier.size(56.dp))
        Spacer(Modifier.height(16.dp))
        Text(node.name, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = c.fg, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(
            listOf(human(node.size), node.note.ifEmpty { "No preview for this file type." }).joinToString(" · "),
            fontSize = 14.sp, color = c.muted, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))
        Button(onClick = { Actions.openWith(ctx, scope, node) }) {
            Icon(Icons.AutoMirrored.Outlined.OpenInNew, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("Open with…")
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = { Actions.download(ctx, node) }) {
            Icon(Icons.Outlined.Download, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("Download")
        }
    }
}
