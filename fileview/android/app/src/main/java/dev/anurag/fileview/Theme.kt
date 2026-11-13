package dev.anurag.fileview

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight

@Immutable
data class Palette(
    val dark: Boolean,
    val bg: Color, val bg2: Color, val bg3: Color,
    val line: Color, val line2: Color, val line3: Color,
    val fg: Color, val fg2: Color, val muted: Color, val faint: Color,
    val accent: Color, val sel: Color, val selEdge: Color,
    val comment: Color, val kw: Color, val str: Color, val num: Color, val fn: Color, val type: Color, val op: Color,
    val ins: Color, val del: Color,
) {
    private val cache = HashMap<String, SpanStyle?>()

    fun token(cls: String): SpanStyle? = cache.getOrPut(cls) {
        when {
            cls.isEmpty() -> null
            cls == "cp" || cls == "cpf" -> SpanStyle(color = type)
            cls.startsWith("c") || cls == "sd" -> SpanStyle(color = comment, fontStyle = FontStyle.Italic)
            cls == "kc" || cls == "kt" -> SpanStyle(color = num)
            cls.startsWith("k") || cls == "ow" || cls == "nt" -> SpanStyle(color = kw)
            cls in setOf("no", "nb", "bp", "il") || cls.startsWith("m") -> SpanStyle(color = num)
            cls.startsWith("s") || cls == "dl" -> SpanStyle(color = str)
            cls in setOf("nf", "fm", "na", "py") -> SpanStyle(color = fn)
            cls in setOf("nc", "nn", "ne", "nd") -> SpanStyle(color = type)
            cls == "o" || cls == "p" -> SpanStyle(color = op)
            cls in setOf("gh", "gu", "gs") -> SpanStyle(fontWeight = FontWeight.SemiBold)
            cls == "ge" -> SpanStyle(fontStyle = FontStyle.Italic)
            cls == "gi" -> SpanStyle(background = ins)
            cls == "gd" -> SpanStyle(background = del)
            else -> null
        }
    }
}

private val Light = Palette(
    dark = false,
    bg = Color(0xFFFFFFFF), bg2 = Color(0xFFFAFAFA), bg3 = Color(0xFFF2F2F2),
    line = Color(0xFFEBEBEB), line2 = Color(0xFFE0E0E0), line3 = Color(0xFFC9C9C9),
    fg = Color(0xFF171717), fg2 = Color(0xFF4D4D4D), muted = Color(0xFF666666), faint = Color(0xFF8F8F8F),
    accent = Color(0xFFE11A27), sel = Color(0x33EDAB36), selEdge = Color(0xFFEDAB36),
    comment = Color(0xFF8F8F8F), kw = Color(0xFFC2185B), str = Color(0xFF2A7E3B), num = Color(0xFFA35200),
    fn = Color(0xFF7D3CC8), type = Color(0xFFA44319), op = Color(0xFF4D4D4D),
    ins = Color(0x1F2A7E3B), del = Color(0x1AE11A27),
)

private val Dark = Palette(
    dark = true,
    bg = Color(0xFF0A0A0A), bg2 = Color(0xFF0F0F0F), bg3 = Color(0xFF1A1A1A),
    line = Color(0xFF1F1F1F), line2 = Color(0xFF2E2E2E), line3 = Color(0xFF454545),
    fg = Color(0xFFEDEDED), fg2 = Color(0xFFC7C7C7), muted = Color(0xFFA1A1A1), faint = Color(0xFF6E6E6E),
    accent = Color(0xFFFF4D58), sel = Color(0x24EDAB36), selEdge = Color(0xFFEDAB36),
    comment = Color(0xFF6E6E6E), kw = Color(0xFFFF6B9A), str = Color(0xFF62C073), num = Color(0xFFFFA657),
    fn = Color(0xFFC79BF2), type = Color(0xFFF0A875), op = Color(0xFFA1A1A1),
    ins = Color(0x1F62C073), del = Color(0x1FFF4D58),
)

val LocalPalette = staticCompositionLocalOf { Light }

object Fv {
    val c: Palette @Composable get() = LocalPalette.current
}

@Composable
fun FileviewTheme(content: @Composable () -> Unit) {
    val p = if (isSystemInDarkTheme()) Dark else Light
    val scheme = if (p.dark) darkColorScheme(
        primary = p.accent, onPrimary = Color.White, secondary = p.accent, onSecondary = Color.White,
        background = p.bg, onBackground = p.fg, surface = p.bg, onSurface = p.fg,
        surfaceVariant = p.bg3, onSurfaceVariant = p.muted, outline = p.line3, outlineVariant = p.line2,
        surfaceContainerLowest = p.bg, surfaceContainerLow = p.bg2, surfaceContainer = p.bg2,
        surfaceContainerHigh = p.bg3, surfaceContainerHighest = p.bg3,
        secondaryContainer = p.bg3, onSecondaryContainer = p.fg,
    ) else lightColorScheme(
        primary = p.accent, onPrimary = Color.White, secondary = p.accent, onSecondary = Color.White,
        background = p.bg, onBackground = p.fg, surface = p.bg, onSurface = p.fg,
        surfaceVariant = p.bg3, onSurfaceVariant = p.muted, outline = p.line3, outlineVariant = p.line2,
        surfaceContainerLowest = p.bg, surfaceContainerLow = p.bg2, surfaceContainer = p.bg2,
        surfaceContainerHigh = p.bg3, surfaceContainerHighest = p.bg3,
        secondaryContainer = p.bg3, onSecondaryContainer = p.fg,
    )
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
