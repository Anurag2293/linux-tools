package dev.anurag.fileview

import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.core.content.FileProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.io.File

object Actions {
    fun toast(ctx: Context, text: String) = Toast.makeText(ctx, text, Toast.LENGTH_SHORT).show()

    fun copy(ctx: Context, text: String, what: String = "Link") {
        ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(what, text))
        toast(ctx, "$what copied")
    }

    fun share(ctx: Context, text: String) {
        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text)
        ctx.startActivity(Intent.createChooser(send, null))
    }

    fun external(ctx: Context, uri: Uri) {
        val intent = Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE)
        if (uri.host == Server.host) browser(ctx)?.let { intent.setPackage(it) }
        try {
            ctx.startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            toast(ctx, "No app can open this link")
        }
    }

    private fun browser(ctx: Context): String? {
        val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")).addCategory(Intent.CATEGORY_BROWSABLE)
        val pm = ctx.packageManager
        return pm.resolveActivity(probe, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName
            ?.takeIf { it != "android" && it != ctx.packageName }
            ?: pm.queryIntentActivities(probe, 0).map { it.activityInfo.packageName }.firstOrNull { it != ctx.packageName }
    }

    fun mime(name: String): String =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase())
            ?: "application/octet-stream"

    fun download(ctx: Context, node: Node) {
        val request = DownloadManager.Request(Uri.parse(Server.url(node.path, "raw")))
            .setMimeType(mime(node.name))
            .setTitle(node.name)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, node.name)
        ctx.getSystemService(DownloadManager::class.java).enqueue(request)
        toast(ctx, "Downloading ${node.name}")
    }

    fun openWith(ctx: Context, scope: CoroutineScope, node: Node) {
        toast(ctx, "Fetching ${node.name}…")
        scope.launch {
            try {
                val file = File(ctx.cacheDir, "open/${node.path.hashCode()}-${node.mtime}/${node.name}")
                if (!file.exists() || file.length() != node.size) Net.fetch(node.path, file)
                val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", file)
                val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime(node.name))
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                ctx.startActivity(Intent.createChooser(view, null).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
            } catch (e: Exception) {
                toast(ctx, Net.describe(e))
            }
        }
    }
}
