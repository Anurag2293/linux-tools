package dev.anurag.fileview

import android.content.Context
import android.graphics.Typeface
import android.text.method.LinkMovementMethod
import android.text.Spanned
import android.text.SpannableStringBuilder
import android.text.util.Linkify
import android.view.Gravity
import android.view.View
import android.widget.HorizontalScrollView
import android.widget.TableLayout
import android.widget.TableRow
import android.widget.TextView
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.key
import androidx.compose.ui.unit.dp
import org.commonmark.ext.gfm.tables.TableBlock
import org.commonmark.ext.gfm.tables.TableCell
import org.commonmark.ext.gfm.tables.TableHead
import org.commonmark.node.Document
import org.commonmark.node.Paragraph
import org.commonmark.node.Node as CmNode
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import io.noties.markwon.AbstractMarkwonPlugin
import io.noties.markwon.Markwon
import io.noties.markwon.MarkwonConfiguration
import io.noties.markwon.core.MarkwonTheme
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.tasklist.TaskListPlugin
import io.noties.markwon.html.HtmlPlugin
import io.noties.markwon.image.ImagesPlugin
import io.noties.markwon.image.data.DataUriSchemeHandler
import io.noties.markwon.image.destination.ImageDestinationProcessor
import io.noties.markwon.image.network.OkHttpNetworkSchemeHandler
import io.noties.markwon.linkify.LinkifyPlugin

private fun markwon(ctx: Context, c: Palette, node: Node, onLink: (String) -> Unit): Markwon {
    val dir = if (node.isDir) node.path else node.path.substring(0, node.path.lastIndexOf('/') + 1)
    return Markwon.builder(ctx)
        .usePlugin(StrikethroughPlugin.create())
        .usePlugin(TablePlugin.create { t ->
            t.tableBorderColor(c.line2.toArgb())
                .tableHeaderRowBackgroundColor(c.bg3.toArgb())
                .tableOddRowBackgroundColor(c.bg.toArgb())
                .tableEvenRowBackgroundColor(c.bg2.toArgb())
                .tableCellPadding((8 * ctx.resources.displayMetrics.density).toInt())
        })
        .usePlugin(TaskListPlugin.create(c.accent.toArgb(), c.line3.toArgb(), c.bg.toArgb()))
        .usePlugin(HtmlPlugin.create())
        .usePlugin(LinkifyPlugin.create(Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES))
        .usePlugin(ImagesPlugin.create { p ->
            p.addSchemeHandler(DataUriSchemeHandler.create())
            p.addSchemeHandler(OkHttpNetworkSchemeHandler.create(Net.client))
        })
        .usePlugin(object : AbstractMarkwonPlugin() {
            override fun configureTheme(b: MarkwonTheme.Builder) {
                b.linkColor(c.accent.toArgb())
                    .isLinkUnderlined(false)
                    .codeTextColor(c.fg.toArgb())
                    .codeBlockTextColor(c.fg.toArgb())
                    .codeBackgroundColor(c.bg3.toArgb())
                    .codeBlockBackgroundColor(c.bg3.toArgb())
                    .codeTypeface(Typeface.MONOSPACE)
                    .codeTextSize((12.5f * ctx.resources.displayMetrics.scaledDensity).toInt())
                    .blockQuoteColor(c.line3.toArgb())
                    .headingBreakColor(c.line.toArgb())
                    .thematicBreakColor(c.line2.toArgb())
                    .bulletWidth((5 * ctx.resources.displayMetrics.density).toInt())
                    .headingTextSizeMultipliers(floatArrayOf(1.55f, 1.3f, 1.12f, 1f, .92f, .85f))
            }

            override fun configureConfiguration(b: MarkwonConfiguration.Builder) {
                b.linkResolver { _, link -> onLink(link) }
                b.imageDestinationProcessor(object : ImageDestinationProcessor() {
                    override fun process(destination: String): String {
                        if (Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:").containsMatchIn(destination)) return destination
                        val base = if (destination.startsWith("/")) "" else dir
                        return Server.url(normalize(base + android.net.Uri.decode(destination)), "raw")
                    }
                })
            }
        })
        .build()
}

private fun normalize(path: String): String {
    val parts = ArrayList<String>()
    for (seg in path.split('/')) when (seg) {
        "", "." -> Unit
        ".." -> if (parts.isNotEmpty()) parts.removeAt(parts.lastIndex)
        else -> parts.add(seg)
    }
    return "/" + parts.joinToString("/")
}

private sealed class Block
private class TextBlock(val text: Spanned) : Block()
private class TableBlockView(val rows: List<List<Pair<Spanned, TableCell.Alignment?>>>, val headerRows: Int) : Block()

private fun trimEnd(s: Spanned): Spanned {
    val b = SpannableStringBuilder(s)
    while (b.isNotEmpty() && b[b.length - 1].isWhitespace()) b.delete(b.length - 1, b.length)
    return b
}

private fun blocks(mw: Markwon, text: String): List<Block> {
    val doc = mw.parse(text)
    val out = ArrayList<Block>()
    var pending = Document()
    fun flush() {
        if (pending.firstChild != null) out.add(TextBlock(trimEnd(mw.render(pending))))
        pending = Document()
    }
    var n: CmNode? = doc.firstChild
    while (n != null) {
        val next = n.next
        if (n is TableBlock) {
            flush()
            out.add(table(mw, n))
        } else {
            n.unlink()
            pending.appendChild(n)
        }
        n = next
    }
    flush()
    return out
}

private fun table(mw: Markwon, block: TableBlock): TableBlockView {
    val rows = ArrayList<List<Pair<Spanned, TableCell.Alignment?>>>()
    var headerRows = 0
    var section = block.firstChild
    while (section != null) {
        var row = section.firstChild
        while (row != null) {
            val cells = ArrayList<Pair<Spanned, TableCell.Alignment?>>()
            var cell = row.firstChild
            while (cell != null) {
                val para = Paragraph()
                var child = cell.firstChild
                while (child != null) {
                    val nextChild = child.next
                    child.unlink()
                    para.appendChild(child)
                    child = nextChild
                }
                val d = Document()
                d.appendChild(para)
                cells.add(trimEnd(mw.render(d)) to (cell as? TableCell)?.alignment)
                cell = cell.next
            }
            rows.add(cells)
            if (section is TableHead) headerRows++
            row = row.next
        }
        section = section.next
    }
    return TableBlockView(rows, headerRows)
}

private fun selectable(tv: TextView, c: Palette) {
    tv.setTextIsSelectable(true)
    tv.movementMethod = LinkMovementMethod.getInstance()
    tv.setTextColor(c.fg.toArgb())
    tv.setLinkTextColor(c.accent.toArgb())
    tv.highlightColor = c.selEdge.copy(alpha = if (c.dark) 0.45f else 0.5f).toArgb()
}

private fun tableView(ctx: Context, mw: Markwon, t: TableBlockView, c: Palette): View {
    val dp = ctx.resources.displayMetrics.density
    val table = TableLayout(ctx).apply {
        setBackgroundColor(c.line2.toArgb())
        setPadding(1, 1, 1, 1)
    }
    t.rows.forEachIndexed { r, cells ->
        val header = r < t.headerRows
        val bg = when {
            header -> c.bg3
            (r - t.headerRows) % 2 == 1 -> c.bg2
            else -> c.bg
        }.toArgb()
        val row = TableRow(ctx)
        cells.forEach { (text, align) ->
            val tv = TextView(ctx).apply {
                textSize = 14f
                setLineSpacing(0f, 1.2f)
                maxWidth = (280 * dp).toInt()
                setPadding((10 * dp).toInt(), (7 * dp).toInt(), (10 * dp).toInt(), (7 * dp).toInt())
                setBackgroundColor(bg)
                if (header) setTypeface(typeface, Typeface.BOLD)
                gravity = when (align) {
                    TableCell.Alignment.CENTER -> Gravity.CENTER_HORIZONTAL
                    TableCell.Alignment.RIGHT -> Gravity.END
                    else -> Gravity.START
                }
                selectable(this, c)
            }
            mw.setParsedMarkdown(tv, text)
            row.addView(tv, TableRow.LayoutParams(TableRow.LayoutParams.WRAP_CONTENT, TableRow.LayoutParams.MATCH_PARENT).apply {
                setMargins(1, 1, 1, 1)
            })
        }
        table.addView(row)
    }
    return HorizontalScrollView(ctx).apply {
        isHorizontalScrollBarEnabled = false
        addView(table)
    }
}

@Composable
fun MarkdownText(text: String, node: Node, onLink: (String) -> Unit, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val c = Fv.c
    val link = rememberUpdatedState(onLink)
    val mw = remember(c, node.path) { markwon(ctx, c, node) { link.value(it) } }
    val parts = remember(mw, text) { blocks(mw, text) }
    Column(modifier) {
        parts.forEachIndexed { i, b ->
            if (i > 0) Spacer(Modifier.height(10.dp))
            when (b) {
                is TextBlock -> AndroidView(
                    factory = {
                        TextView(it).apply {
                            textSize = 15f
                            setLineSpacing(0f, 1.25f)
                            selectable(this, c)
                        }
                    },
                    update = { tv -> mw.setParsedMarkdown(tv, b.text) },
                    modifier = Modifier.fillMaxWidth(),
                )
                is TableBlockView -> key(b) {
                    AndroidView(factory = { tableView(it, mw, b, c) }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
}
