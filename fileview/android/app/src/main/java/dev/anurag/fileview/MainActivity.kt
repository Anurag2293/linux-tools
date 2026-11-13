package dev.anurag.fileview

import android.app.AlertDialog
import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.ImageDecoderDecoder
import coil.decode.SvgDecoder
import android.content.pm.verify.domain.DomainVerificationManager
import android.content.pm.verify.domain.DomainVerificationUserState

class FileviewApp : Application(), ImageLoaderFactory {
    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .okHttpClient(Net.client)
        .components {
            add(SvgDecoder.Factory())
            add(ImageDecoderDecoder.Factory())
        }
        .crossfade(true)
        .build()
}

class MainActivity : ComponentActivity() {
    private val vm: AppModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val target = if (savedInstanceState == null) target(intent) else null
        when {
            target != null -> {
                vm.restore()
                vm.open(target)
            }
            !vm.restore() -> vm.home()
        }
        setContent {
            FileviewTheme { AppScreen(vm, onExit = { moveTaskToBack(true) }) }
        }
        askForLinks()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        target(intent)?.let { vm.open(it) }
    }

    private fun target(intent: Intent?): Loc? = when (intent?.action) {
        Intent.ACTION_VIEW -> intent.data?.let(Server::locOf)
        Intent.ACTION_SEND -> intent.getStringExtra(Intent.EXTRA_TEXT)?.let { text ->
            Regex("""https://[^\s<>"'\])]+""").findAll(text).mapNotNull { Server.locOf(Uri.parse(it.value)) }.firstOrNull()
        }
        else -> null
    }

    private fun askForLinks() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
        val prefs = getSharedPreferences("fileview", MODE_PRIVATE)
        if (prefs.getBoolean("asked_links", false)) return
        val state = getSystemService(DomainVerificationManager::class.java)
            .getDomainVerificationUserState(packageName)?.hostToStateMap?.get(Server.host)
        if (state != DomainVerificationUserState.DOMAIN_STATE_NONE) return
        prefs.edit().putBoolean("asked_links", true).apply()
        AlertDialog.Builder(this)
            .setTitle("Open fileview links here?")
            .setMessage("Android asks once: tap \"Add link\" and tick ${Server.host}. Links from T3, Slack and the rest then open in this app instead of Chrome.")
            .setPositiveButton("Open settings") { _, _ ->
                startActivity(Intent(Settings.ACTION_APP_OPEN_BY_DEFAULT_SETTINGS, Uri.parse("package:$packageName")))
            }
            .setNegativeButton("Not now", null)
            .show()
    }
}
