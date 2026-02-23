package com.asciistudio.mobile

import android.app.Activity
import android.app.ActivityManager
import android.content.ContentValues
import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.ImageDecoder
import android.graphics.Movie
import android.graphics.Paint
import android.graphics.Typeface
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.util.LruCache
import android.view.MotionEvent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.SaveAlt
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Translate
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.pointerInteropFilter
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.ClipboardManager
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.TextUnit
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.annotation.StringRes
import com.asciistudio.mobile.core.model.PreviewQuality
import com.asciistudio.mobile.core.model.ProjectV2
import com.asciistudio.mobile.core.model.RenderSettings
import com.asciistudio.mobile.core.presets.UasPreset
import com.asciistudio.mobile.core.render.AsciiRenderEngine
import com.asciistudio.mobile.feature.ar.ArMockScreen
import com.asciistudio.mobile.feature.about.AboutScreen
import com.asciistudio.mobile.feature.home.HomeScreen
import com.asciistudio.mobile.feature.presets.PresetsScreen
import com.asciistudio.mobile.feature.theme.ThemeScreen
import com.asciistudio.mobile.feature.editor.EditorScreen
import com.asciistudio.mobile.feature.editor.EditorViewModel
import com.asciistudio.mobile.ui.theme.AppLanguage
import com.asciistudio.mobile.ui.theme.AsciiStudioMobileTheme
import com.asciistudio.mobile.ui.theme.AsciiTheme
import com.asciistudio.mobile.ui.theme.CustomThemeConfig
import com.asciistudio.mobile.ui.theme.MobileThemeMode
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import org.json.JSONArray
import org.json.JSONObject

internal data class AsciiPreset(
    val id: String,
    val titleEn: String,
    val titleRu: String,
    val titleZh: String,
    val subtitleEn: String,
    val subtitleRu: String,
    val subtitleZh: String,
    val width: Int,
    val contrast: Float,
    val brightness: Float,
    val gamma: Float,
    val saturation: Float,
    val exposure: Float = 0f,
    val sharpen: Float = 0f,
    val vignette: Float = 0f,
    val invert: Boolean,
    val charsetKey: String,
    val previewFont: Float
) {
    fun title(lang: AppLanguage) = when (lang) {
        AppLanguage.En -> titleEn
        AppLanguage.Ru -> titleRu
        AppLanguage.Zh -> titleZh
    }

    fun subtitle(lang: AppLanguage) = when (lang) {
        AppLanguage.En -> subtitleEn
        AppLanguage.Ru -> subtitleRu
        AppLanguage.Zh -> subtitleZh
    }
}

private data class LoadedBitmap(val bitmap: Bitmap, val mediaKind: String)
private data class TrailDot(val x: Float, val y: Float, val radius: Float, val life: Float)
private data class MediaPlaybackInfo(val durationMs: Long, val fps: Int)
internal data class ProjectEntry(
    val id: String,
    val title: String,
    val uri: String,
    val kind: String,
    val durationMs: Long,
    val updatedAt: Long
)
private data class QuickPresetItem(
    val name: String,
    val category: String,
    val style: String,
    val width: Int,
    val charset: String
)

private const val PREFS_NAME = "ascii_studio_mobile_prefs"
private const val PREFS_PROJECTS_KEY = "projects_v1"
private const val PREFS_STARTUP_IN_PROGRESS = "startup_in_progress"

private val CHARSETS = linkedMapOf(
    "Classic" to "@%#*+=-:. ",
    "Dense" to "@#WMBRXVYIti+=:,. ",
    "Blocks" to "█▓▒░ ",
    "Binary" to "10 ",
    "Minimal" to "#.: "
)

private val PRESETS = listOf(
    AsciiPreset(
        id = "cinematic",
        titleEn = "Cinematic",
        titleRu = "Кинематик",
        titleZh = "电影感",
        subtitleEn = "Deep contrast and dramatic details",
        subtitleRu = "Глубокий контраст и драматичные детали",
        subtitleZh = "高对比度与电影氛围细节",
        width = 170,
        contrast = 1.35f,
        brightness = -0.03f,
        gamma = 1f,
        saturation = 1.15f,
        exposure = 0.05f,
        sharpen = 0.25f,
        vignette = 0.08f,
        invert = false,
        charsetKey = "Dense",
        previewFont = 7.5f
    ),
    AsciiPreset(
        id = "clean",
        titleEn = "Clean",
        titleRu = "Чистый",
        titleZh = "清晰",
        subtitleEn = "Balanced look for social media",
        subtitleRu = "Сбалансированный вид для соцсетей",
        subtitleZh = "适合社交媒体的均衡风格",
        width = 125,
        contrast = 1f,
        brightness = 0f,
        gamma = 1f,
        saturation = 1f,
        exposure = 0f,
        sharpen = 0.1f,
        vignette = 0f,
        invert = false,
        charsetKey = "Classic",
        previewFont = 8.8f
    ),
    AsciiPreset(
        id = "retro",
        titleEn = "Retro CRT",
        titleRu = "Ретро CRT",
        titleZh = "复古 CRT",
        subtitleEn = "Chunky blocks and warmer highlights",
        subtitleRu = "Крупные блоки и тёплые акценты",
        subtitleZh = "粗颗粒字符与暖色高光",
        width = 92,
        contrast = 1.16f,
        brightness = 0.02f,
        gamma = 0.95f,
        saturation = 1.05f,
        exposure = 0.03f,
        sharpen = 0.2f,
        vignette = 0.2f,
        invert = false,
        charsetKey = "Blocks",
        previewFont = 10f
    ),
    AsciiPreset(
        id = "blueprint",
        titleEn = "Blueprint",
        titleRu = "Блюпринт",
        titleZh = "蓝图",
        subtitleEn = "Technical minimal style with inversion",
        subtitleRu = "Технический минимализм с инверсией",
        subtitleZh = "技术极简风（带反相）",
        width = 110,
        contrast = 1.22f,
        brightness = 0.05f,
        gamma = 1.08f,
        saturation = 0.82f,
        exposure = 0.02f,
        sharpen = 0.12f,
        vignette = 0f,
        invert = true,
        charsetKey = "Minimal",
        previewFont = 9f
    ),
    AsciiPreset(
        id = "noir",
        titleEn = "Noir",
        titleRu = "Нуар",
        titleZh = "黑色电影",
        subtitleEn = "Dark shadows and punchy texture",
        subtitleRu = "Тёмные тени и плотная фактура",
        subtitleZh = "更深阴影与更强纹理",
        width = 150,
        contrast = 1.28f,
        brightness = -0.06f,
        gamma = 0.94f,
        saturation = 0.92f,
        exposure = 0.01f,
        sharpen = 0.18f,
        vignette = 0.24f,
        invert = false,
        charsetKey = "Dense",
        previewFont = 8.0f
    )
)

private val QUICK_PRESETS = listOf(
    QuickPresetItem("Tokyo Blue", "Hot", "cyber", 130, "Dense"),
    QuickPresetItem("High Saturation", "Life", "soft", 120, "Classic"),
    QuickPresetItem("Old Money", "Retro", "retro", 96, "Blocks"),
    QuickPresetItem("Dark", "Scenery", "cinematic", 140, "Dense"),
    QuickPresetItem("Perfect Roast", "Hot", "vhs", 100, "Blocks"),
    QuickPresetItem("Clean", "Life", "clean", 118, "Classic"),
    QuickPresetItem("Blueprint", "Scenery", "none", 110, "Minimal"),
    QuickPresetItem("Neon Pulse", "Hot", "cyber", 138, "Dense"),
    QuickPresetItem("Night Grain", "Scenery", "cinematic", 150, "Dense"),
    QuickPresetItem("City VHS", "Retro", "vhs", 104, "Blocks"),
    QuickPresetItem("Film Soft", "Life", "soft", 122, "Classic"),
    QuickPresetItem("Mono Ink", "Edit", "clean", 112, "Minimal"),
    QuickPresetItem("Street CRT", "Retro", "retro", 98, "Blocks"),
    QuickPresetItem("Glass Noir", "Scenery", "cinematic", 142, "Dense"),
    QuickPresetItem("Studio Flat", "Edit", "clean", 126, "Classic"),
    QuickPresetItem("Signal Split", "Pro", "vhs", 108, "Blocks"),
    QuickPresetItem("Matrix Dust", "Pro", "cyber", 132, "Dense"),
    QuickPresetItem("Soft Daylight", "Life", "soft", 124, "Classic"),
    QuickPresetItem("Night Focus", "Hot", "cinematic", 144, "Dense"),
    QuickPresetItem("Terminal", "Edit", "none", 116, "Minimal")
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // Disable state restore between rapidly changing builds to prevent startup crashes
        // caused by stale rememberSaveable payloads after app updates.
        super.onCreate(null)
        enableEdgeToEdge()
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val hadStartupFailure = prefs.getBoolean(PREFS_STARTUP_IN_PROGRESS, false)
        prefs.edit().putBoolean(PREFS_STARTUP_IN_PROGRESS, true).apply()
        setContent {
            if (hadStartupFailure) {
                AsciiStudioMobileTheme(mode = MobileThemeMode.Midnight, custom = CustomThemeConfig()) {
                    SafeBootScreen(
                        onTryNormal = {
                            prefs.edit().putBoolean(PREFS_STARTUP_IN_PROGRESS, false).apply()
                            recreate()
                        },
                        onResetState = {
                            prefs.edit().clear().apply()
                            recreate()
                        }
                    )
                }
            } else {
                AsciiStudioMobileApp(
                    onAppReady = {
                        prefs.edit().putBoolean(PREFS_STARTUP_IN_PROGRESS, false).apply()
                    }
                )
            }
        }
    }
}

@Composable
private fun SafeBootScreen(
    onTryNormal: () -> Unit,
    onResetState: () -> Unit
) {
    val bg = Color(0xFF090D14)
    val bgSecondary = Color(0xFF0E1420)
    val panelStrong = Color(0xFF162235)
    val text = Color(0xFFEAF3FF)
    val textSubtle = Color(0xFFB6C8DE)
    val border = Color(0xFF274260)
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(bg, bgSecondary)))
            .padding(16.dp),
        contentAlignment = Alignment.Center
    ) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = panelStrong.copy(alpha = 0.92f)),
            border = BorderStroke(1.dp, border.copy(alpha = 0.70f)),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("ASCII Studio Mobile", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = text)
                Text("Safe boot", style = MaterialTheme.typography.titleSmall, color = textSubtle)
                Text(
                    "The previous launch failed. Start in normal mode or reset local state.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = textSubtle
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Button(onClick = onTryNormal, shape = RoundedCornerShape(12.dp), modifier = Modifier.weight(1f)) {
                        Text("Try normal")
                    }
                    OutlinedButton(onClick = onResetState, shape = RoundedCornerShape(12.dp), modifier = Modifier.weight(1f)) {
                        Text("Reset local state")
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun AsciiStudioMobileApp(onAppReady: () -> Unit = {}) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val lowRamDevice = remember {
        runCatching {
            val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
            am?.isLowRamDevice == true
        }.getOrDefault(false)
    }

    var tab by rememberSaveable { mutableIntStateOf(0) }
    var showHome by rememberSaveable { mutableStateOf(true) }
    var langName by rememberSaveable { mutableStateOf(defaultLanguage().name) }
    var themeName by rememberSaveable { mutableStateOf(MobileThemeMode.Midnight.name) }

    var bgR by rememberSaveable { mutableIntStateOf(12) }
    var bgG by rememberSaveable { mutableIntStateOf(16) }
    var bgB by rememberSaveable { mutableIntStateOf(24) }
    var panelR by rememberSaveable { mutableIntStateOf(21) }
    var panelG by rememberSaveable { mutableIntStateOf(28) }
    var panelB by rememberSaveable { mutableIntStateOf(41) }
    var accR by rememberSaveable { mutableIntStateOf(94) }
    var accG by rememberSaveable { mutableIntStateOf(200) }
    var accB by rememberSaveable { mutableIntStateOf(255) }
    var textR by rememberSaveable { mutableIntStateOf(232) }
    var textG by rememberSaveable { mutableIntStateOf(242) }
    var textB by rememberSaveable { mutableIntStateOf(255) }

    var tailEnabled by rememberSaveable { mutableStateOf(true) }
    var sourceBitmap by remember { mutableStateOf<Bitmap?>(null) }
    var sourceLabel by rememberSaveable { mutableStateOf("No media selected") }
    var sourceKind by rememberSaveable { mutableStateOf("image") }
    var sourceUriText by rememberSaveable { mutableStateOf("") }
    var sourceDurationMs by rememberSaveable { mutableLongStateOf(0L) }
    var sourcePositionMs by rememberSaveable { mutableLongStateOf(0L) }
    var sourceFps by rememberSaveable { mutableIntStateOf(24) }
    var sourcePlaying by rememberSaveable { mutableStateOf(false) }
    var sourceGifBytes by remember { mutableStateOf<ByteArray?>(null) }
    var sourceGifMovie by remember { mutableStateOf<Movie?>(null) }
    var mediaLoading by remember { mutableStateOf(false) }
    var editorFullscreen by rememberSaveable { mutableStateOf(false) }
    val projects = remember { mutableStateListOf<ProjectEntry>() }

    var widthChars by rememberSaveable { mutableIntStateOf(120) }
    var charAspectRatio by rememberSaveable { mutableFloatStateOf(0.55f) }
    var contrast by rememberSaveable { mutableFloatStateOf(1f) }
    var brightness by rememberSaveable { mutableFloatStateOf(0f) }
    var gamma by rememberSaveable { mutableFloatStateOf(1f) }
    var saturation by rememberSaveable { mutableFloatStateOf(1f) }
    var exposure by rememberSaveable { mutableFloatStateOf(0f) }
    var sharpen by rememberSaveable { mutableFloatStateOf(0f) }
    var vignette by rememberSaveable { mutableFloatStateOf(0f) }
    var bloom by rememberSaveable { mutableFloatStateOf(0f) }
    var denoise by rememberSaveable { mutableFloatStateOf(0f) }
    var edgeBoost by rememberSaveable { mutableFloatStateOf(0f) }
    var posterize by rememberSaveable { mutableIntStateOf(0) }
    var scanlines by rememberSaveable { mutableStateOf(false) }
    var scanStrength by rememberSaveable { mutableFloatStateOf(0.22f) }
    var scanStep by rememberSaveable { mutableIntStateOf(3) }
    var dither by rememberSaveable { mutableStateOf(false) }
    var curvature by rememberSaveable { mutableFloatStateOf(0f) }
    var concavity by rememberSaveable { mutableFloatStateOf(0f) }
    var curveCenterX by rememberSaveable { mutableFloatStateOf(0f) }
    var curveExpand by rememberSaveable { mutableFloatStateOf(0f) }
    var curveType by rememberSaveable { mutableIntStateOf(0) }
    var grain by rememberSaveable { mutableFloatStateOf(0f) }
    var chroma by rememberSaveable { mutableFloatStateOf(0f) }
    var ribbing by rememberSaveable { mutableFloatStateOf(0f) }
    var clarity by rememberSaveable { mutableFloatStateOf(0f) }
    var motionBlur by rememberSaveable { mutableFloatStateOf(0f) }
    var colorBoost by rememberSaveable { mutableFloatStateOf(0f) }
    var glitch by rememberSaveable { mutableFloatStateOf(0f) }
    var glitchDensity by rememberSaveable { mutableFloatStateOf(0.35f) }
    var glitchShift by rememberSaveable { mutableFloatStateOf(0.42f) }
    var glitchRgb by rememberSaveable { mutableStateOf(true) }
    var glitchBlock by rememberSaveable { mutableFloatStateOf(0.10f) }
    var glitchJitter by rememberSaveable { mutableFloatStateOf(0.10f) }
    var glitchNoise by rememberSaveable { mutableFloatStateOf(0.12f) }
    var renderFps by rememberSaveable { mutableIntStateOf(24) }
    var renderCodec by rememberSaveable { mutableStateOf("libx264") }
    var renderBitrate by rememberSaveable { mutableStateOf("2M") }
    var exportFormat by rememberSaveable { mutableStateOf("PNG") }
    var invert by rememberSaveable { mutableStateOf(false) }
    var fontSize by rememberSaveable { mutableFloatStateOf(8.5f) }
    var charsetKey by rememberSaveable { mutableStateOf("Classic") }
    var watermarkEnabled by rememberSaveable { mutableStateOf(false) }
    var watermarkText by rememberSaveable { mutableStateOf("SNERK503") }
    var preserveSourceColors by rememberSaveable { mutableStateOf(false) }
    var livePreviewEnabled by rememberSaveable { mutableStateOf(true) }
    var glassBlurStrength by rememberSaveable { mutableFloatStateOf(0.55f) }
    var tutorialTrigger by rememberSaveable { mutableIntStateOf(0) }
    var openEditorSettingsSignal by rememberSaveable { mutableIntStateOf(0) }

    var previewScale by rememberSaveable { mutableFloatStateOf(1f) }
    var previewOffsetX by rememberSaveable { mutableFloatStateOf(0f) }
    var previewOffsetY by rememberSaveable { mutableFloatStateOf(0f) }
    var previewQualityName by rememberSaveable { mutableStateOf(PreviewQuality.Normal.name) }

    val editorViewModel: EditorViewModel = viewModel()
    val renderOutput by editorViewModel.renderOutput.collectAsState()
    val isRendering by editorViewModel.isRendering.collectAsState()
    var ascii by remember { mutableStateOf("") }
    var asciiPreviewBitmap by remember { mutableStateOf<Bitmap?>(null) }

    val lang = runCatching { AppLanguage.valueOf(langName) }.getOrDefault(AppLanguage.En)
    val themeMode = runCatching { MobileThemeMode.valueOf(themeName) }.getOrDefault(MobileThemeMode.Midnight)
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val customTheme = remember(bgR, bgG, bgB, panelR, panelG, panelB, accR, accG, accB, textR, textG, textB) {
        CustomThemeConfig(
            bg = Color(bgR, bgG, bgB),
            panel = Color(panelR, panelG, panelB),
            accent = Color(accR, accG, accB),
            text = Color(textR, textG, textB)
        )
    }
    val sourceUri = remember(sourceUriText) { sourceUriText.takeIf { it.isNotBlank() }?.let { Uri.parse(it) } }
    val window = (context as? Activity)?.window
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    LaunchedEffect(Unit) { onAppReady() }

    LaunchedEffect(renderOutput, sourceBitmap, livePreviewEnabled) {
        val output = renderOutput
        ascii = output?.ascii.orEmpty()
        if (!livePreviewEnabled || output == null || output.ascii.isBlank()) {
            asciiPreviewBitmap = null
            return@LaunchedEffect
        }
        val sourceW = sourceBitmap?.width
        val sourceH = sourceBitmap?.height
        asciiPreviewBitmap = withContext(Dispatchers.Default) {
            val bmp = output.raster
            if (sourceW != null && sourceH != null && (bmp.width != sourceW || bmp.height != sourceH)) {
                Bitmap.createScaledBitmap(bmp, sourceW, sourceH, true)
            } else {
                bmp
            }
        }
    }

    LaunchedEffect(Unit) {
        projects.clear()
        projects.addAll(loadProjects(context))
    }

    val loadSelectedMedia: suspend (Uri, Boolean) -> Unit = { uri, autoPlay ->
        mediaLoading = true
        val loaded = loadBitmapSmart(context, uri, 1400)
        loaded.onSuccess {
            sourceBitmap = it.bitmap
            sourceLabel = queryDisplayName(context, uri) ?: s(R.string.media_selected)
            sourceKind = it.mediaKind
            sourceUriText = uri.toString()
            val info = probeMediaPlaybackInfo(context, uri, it.mediaKind)
            sourceDurationMs = info.durationMs
            sourceFps = info.fps
            sourcePositionMs = 0L
            sourcePlaying = autoPlay && it.mediaKind != "image" && info.durationMs > 0L
            sourceGifBytes = if (it.mediaKind == "gif") readUriBytes(context, uri) else null
            sourceGifMovie = sourceGifBytes?.let { b -> runCatching { Movie.decodeByteArray(b, 0, b.size) }.getOrNull() }
            if (it.mediaKind != "video") {
                VideoFrameCache.clear()
            }
            previewScale = 1f
            previewOffsetX = 0f
            previewOffsetY = 0f

            val title = queryDisplayName(context, uri) ?: "Project ${SimpleDateFormat("MMdd-HHmm", Locale.US).format(Date())}"
            val entry = ProjectEntry(
                id = uri.toString(),
                title = title,
                uri = uri.toString(),
                kind = it.mediaKind,
                durationMs = info.durationMs,
                updatedAt = System.currentTimeMillis()
            )
            val fresh = projects.filterNot { p -> p.id == entry.id }.toMutableList()
            fresh.add(0, entry)
            projects.clear()
            projects.addAll(fresh.take(40))
            saveProjects(context, projects.toList())
            showHome = false
            tab = 0
        }.onFailure {
            toast(context, s(R.string.import_failed))
        }
        mediaLoading = false
    }

    fun currentRenderSettings(): RenderSettings = RenderSettings(
        widthChars = widthChars,
        charAspectRatio = charAspectRatio,
        fontSizeSp = fontSize,
        contrast = contrast,
        brightness = brightness,
        gamma = gamma,
        saturation = saturation,
        exposure = exposure,
        sharpen = sharpen,
        vignette = vignette,
        bloom = bloom,
        denoise = denoise,
        edgeBoost = edgeBoost,
        posterize = posterize,
        scanlines = scanlines,
        scanStrength = scanStrength,
        scanStep = scanStep,
        dither = dither,
        curvature = curvature,
        concavity = concavity,
        curveCenterX = curveCenterX,
        curveExpand = curveExpand,
        curveType = curveType,
        grain = grain,
        chroma = chroma,
        ribbing = ribbing,
        clarity = clarity,
        motionBlur = motionBlur,
        colorBoost = colorBoost,
        glitch = glitch,
        glitchDensity = glitchDensity,
        glitchShift = glitchShift,
        glitchRgb = glitchRgb,
        glitchBlock = glitchBlock,
        glitchJitter = glitchJitter,
        glitchNoise = glitchNoise,
        invert = invert,
        preserveSourceColors = preserveSourceColors,
        charsetKey = charsetKey,
        charsetValue = CHARSETS[charsetKey] ?: CHARSETS.getValue("Classic"),
        watermarkEnabled = watermarkEnabled,
        watermarkText = watermarkText,
        renderFps = renderFps,
        renderCodec = renderCodec,
        renderBitrate = renderBitrate,
        exportFormat = exportFormat
    )

    fun applyRenderSettings(s: RenderSettings) {
        widthChars = s.widthChars
        charAspectRatio = s.charAspectRatio
        fontSize = s.fontSizeSp
        contrast = s.contrast
        brightness = s.brightness
        gamma = s.gamma
        saturation = s.saturation
        exposure = s.exposure
        sharpen = s.sharpen
        vignette = s.vignette
        bloom = s.bloom
        denoise = s.denoise
        edgeBoost = s.edgeBoost
        posterize = s.posterize
        scanlines = s.scanlines
        scanStrength = s.scanStrength
        scanStep = s.scanStep
        dither = s.dither
        curvature = s.curvature
        concavity = s.concavity
        curveCenterX = s.curveCenterX
        curveExpand = s.curveExpand
        curveType = s.curveType
        grain = s.grain
        chroma = s.chroma
        ribbing = s.ribbing
        clarity = s.clarity
        motionBlur = s.motionBlur
        colorBoost = s.colorBoost
        glitch = s.glitch
        glitchDensity = s.glitchDensity
        glitchShift = s.glitchShift
        glitchRgb = s.glitchRgb
        glitchBlock = s.glitchBlock
        glitchJitter = s.glitchJitter
        glitchNoise = s.glitchNoise
        invert = s.invert
        preserveSourceColors = s.preserveSourceColors
        charsetKey = s.charsetKey
        watermarkEnabled = s.watermarkEnabled
        watermarkText = s.watermarkText
        renderFps = s.renderFps
        renderCodec = s.renderCodec
        renderBitrate = s.renderBitrate
        exportFormat = s.exportFormat
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            loadSelectedMedia(uri, true)
        }
    }

    val loadPresetLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val raw = readUtf8FromUri(context, uri)
        if (raw.isNullOrBlank()) {
            toast(context, s(R.string.import_failed))
            return@rememberLauncherForActivityResult
        }
        runCatching { UasPreset.fromJsonString(raw) }
            .onSuccess {
                applyRenderSettings(it.settings)
                toast(context, s(R.string.preset_loaded))
            }
            .onFailure {
                toast(context, s(R.string.import_failed))
            }
    }

    val loadLegacyProjectsLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val raw = readUtf8FromUri(context, uri)
        if (raw.isNullOrBlank()) {
            toast(context, s(R.string.import_failed))
            return@rememberLauncherForActivityResult
        }
        val imported = runCatching { ProjectV2.parseList(raw) }.getOrElse { emptyList() }
        if (imported.isEmpty()) {
            toast(context, s(R.string.import_failed))
            return@rememberLauncherForActivityResult
        }
        val merged = projects.toMutableList()
        imported.forEach { p ->
            val entry = ProjectEntry(
                id = p.id,
                title = p.title,
                uri = p.sourceUri,
                kind = p.mediaKind,
                durationMs = p.durationMs,
                updatedAt = p.updatedAt
            )
            val idx = merged.indexOfFirst { it.id == entry.id }
            if (idx >= 0) merged[idx] = entry else merged.add(entry)
        }
        val sorted = merged.sortedByDescending { it.updatedAt }.take(40)
        projects.clear()
        projects.addAll(sorted)
        saveProjects(context, projects.toList())
        toast(context, s(R.string.projects_imported))
    }

    LaunchedEffect(
        sourceBitmap,
        widthChars,
        charAspectRatio,
        contrast,
        brightness,
        gamma,
        saturation,
        exposure,
        sharpen,
        vignette,
        bloom,
        denoise,
        edgeBoost,
        posterize,
        scanlines,
        scanStrength,
        scanStep,
        dither,
        curvature,
        concavity,
        curveCenterX,
        curveExpand,
        curveType,
        grain,
        chroma,
        ribbing,
        clarity,
        motionBlur,
        colorBoost,
        glitch,
        glitchDensity,
        glitchShift,
        glitchRgb,
        glitchBlock,
        glitchJitter,
        glitchNoise,
        invert,
        preserveSourceColors,
        charsetKey,
        previewQualityName,
        watermarkEnabled,
        watermarkText
    ) {
        val bmp = sourceBitmap
        if (bmp == null) {
            ascii = ""
            return@LaunchedEffect
        }
        val selectedQuality = runCatching { PreviewQuality.valueOf(previewQualityName) }.getOrDefault(PreviewQuality.Normal)
        val runtimeQuality = if (sourcePlaying) selectedQuality else PreviewQuality.High
        editorViewModel.submitRender(
            bitmap = bmp,
            settings = currentRenderSettings().copy(
                charsetValue = CHARSETS[charsetKey] ?: CHARSETS.getValue("Classic")
            ),
            quality = runtimeQuality
        )
    }

    LaunchedEffect(sourcePlaying, sourceUriText, sourceKind, sourceFps, sourceDurationMs, sourceGifBytes) {
        val uri = sourceUri ?: return@LaunchedEffect
        if (!sourcePlaying) return@LaunchedEffect
        if (sourceKind == "image") return@LaunchedEffect

        val fps = sourceFps.coerceIn(6, 60)
        val stepMs = (1000f / fps.toFloat()).roundToInt().toLong().coerceAtLeast(16L)
        while (isActive && sourcePlaying) {
            val frame = decodeMediaFrame(context, uri, sourceKind, sourcePositionMs, 1400, sourceGifBytes, sourceGifMovie)
            if (frame != null) sourceBitmap = frame

            val duration = sourceDurationMs.coerceAtLeast(0L)
            val next = sourcePositionMs + stepMs
            if (sourceKind == "gif" && duration > 0L) {
                sourcePositionMs = next % duration
            } else {
                if (duration > 0L && next >= duration) {
                    sourcePositionMs = duration
                    sourcePlaying = false
                    break
                }
                sourcePositionMs = next
            }
            delay(stepMs)
        }
    }

    LaunchedEffect(sourcePositionMs, sourcePlaying, sourceUriText, sourceKind, sourceGifBytes) {
        val uri = sourceUri ?: return@LaunchedEffect
        if (sourcePlaying) return@LaunchedEffect
        if (sourceKind == "image") return@LaunchedEffect
        val frame = decodeMediaFrame(context, uri, sourceKind, sourcePositionMs, 1400, sourceGifBytes, sourceGifMovie)
        if (frame != null) sourceBitmap = frame
    }

    AsciiStudioMobileTheme(mode = themeMode, custom = customTheme) {
        val p = AsciiTheme.palette
        val bg = remember(p.bg, p.bgSecondary, p.accent) {
            Brush.verticalGradient(
                listOf(
                    mixColor(p.bg, p.accent2, 0.06f),
                    mixColor(p.bgSecondary, p.accent, 0.12f),
                    p.bg
                )
            )
        }

        Box(Modifier.fillMaxSize().background(bg)) {
            if (!lowRamDevice) {
                LiveThemeBackground(Modifier.matchParentSize(), themeMode)
            }
            val hideSystemUi = (tab == 0 && editorFullscreen && !showHome)
            val showAppShell = !hideSystemUi
            LaunchedEffect(hideSystemUi, window) {
                val w = window ?: return@LaunchedEffect
                val controller = WindowCompat.getInsetsController(w, w.decorView)
                if (hideSystemUi) {
                    controller.hide(WindowInsetsCompat.Type.systemBars())
                    controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                } else {
                    controller.show(WindowInsetsCompat.Type.systemBars())
                }
            }
            ModalNavigationDrawer(
                drawerState = drawerState,
                gesturesEnabled = showAppShell,
                drawerContent = {
                    ModalDrawerSheet(
                        drawerContainerColor = p.panelStrong.copy(alpha = 0.96f),
                        drawerContentColor = p.text
                    ) {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp).verticalScroll(rememberScrollState()),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Icon(Icons.Filled.Settings, null, tint = p.accent)
                                Text(
                                    s(R.string.settings_menu),
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                            HorizontalDivider(color = p.border.copy(alpha = 0.4f))
                            Text(
                                s(R.string.project_page),
                                style = MaterialTheme.typography.labelMedium,
                                color = p.textSubtle
                            )
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedButton(
                                    onClick = {
                                        showHome = false
                                        tab = 0
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Icon(Icons.Filled.Tune, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.editor), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                                OutlinedButton(
                                    onClick = {
                                        tab = 1
                                        showHome = false
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Icon(Icons.Filled.AutoAwesome, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.presets), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                                OutlinedButton(
                                    onClick = {
                                        tab = 3
                                        showHome = false
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Icon(Icons.Filled.Info, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.about), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                                OutlinedButton(
                                    onClick = {
                                        showHome = true
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Icon(Icons.Filled.Image, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.projects), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                                OutlinedButton(
                                    onClick = {
                                        tab = 0
                                        showHome = false
                                        openEditorSettingsSignal += 1
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Icon(Icons.Filled.Settings, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.settings_menu), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(s(R.string.live_preview), color = p.text)
                                Switch(checked = livePreviewEnabled, onCheckedChange = { livePreviewEnabled = it })
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(s(R.string.keep_source_colors), color = p.text)
                                Switch(checked = preserveSourceColors, onCheckedChange = { preserveSourceColors = it })
                            }
                            Text(
                                s(R.string.glass_blur) + ": " + "%.2f".format(Locale.US, glassBlurStrength),
                                color = p.textSubtle,
                                style = MaterialTheme.typography.labelMedium
                            )
                            Slider(
                                value = glassBlurStrength,
                                onValueChange = { glassBlurStrength = it.coerceIn(0f, 1f) },
                                valueRange = 0f..1f
                            )
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedButton(
                                    onClick = {
                                        tutorialTrigger += 1
                                        showHome = false
                                        tab = 0
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.weight(1f)
                                ) {
                                    Icon(Icons.Filled.Info, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.start_tutorial))
                                }
                                OutlinedButton(
                                    onClick = {
                                        showHome = false
                                        tab = 0
                                        scope.launch { drawerState.close() }
                                    },
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.weight(1f)
                                ) {
                                    Icon(Icons.Filled.Tune, null, Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(s(R.string.editor))
                                }
                            }
                        }
                    }
                }
            ) {
            Scaffold(
                containerColor = p.bg,
                topBar = {
                    if (showAppShell) TopAppBar(
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = p.panelStrong.copy(alpha = 0.58f),
                            titleContentColor = p.text,
                            actionIconContentColor = p.text
                        ),
                        title = {
                            Column {
                                AsciiAnimatedWordmark(
                                    modifier = Modifier.fillMaxWidth(),
                                    fontSize = 13.sp
                                )
                                Text(
                                    s(R.string.mobile_ascii_editor),
                                    fontSize = 12.sp,
                                    color = p.textSubtle
                                )
                            }
                        },
                        actions = {
                            IconButton(
                                onClick = { scope.launch { drawerState.open() } }
                            ) {
                                Icon(Icons.Filled.Menu, contentDescription = s(R.string.settings_menu))
                            }
                            AssistChip(
                                onClick = {
                                    langName = when (lang) {
                                        AppLanguage.En -> AppLanguage.Ru.name
                                        AppLanguage.Ru -> AppLanguage.Zh.name
                                        AppLanguage.Zh -> AppLanguage.En.name
                                    }
                                },
                                label = { Text(lang.name.uppercase(Locale.US)) },
                                leadingIcon = { Icon(Icons.Filled.Translate, null, Modifier.size(16.dp)) }
                            )
                        }
                    )
                },
                bottomBar = {}
                ) { pad ->
                Box(Modifier.fillMaxSize().padding(pad)) {
                    if (showHome) {
                        HomeScreen(
                            lang = lang,
                            projects = projects,
                            onPickVideo = {
                                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                            },
                            onPickPhoto = {
                                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            },
                            onOpenProject = { entry ->
                                scope.launch {
                                    loadSelectedMedia(Uri.parse(entry.uri), false)
                                    showHome = false
                                    tab = 0
                                }
                            },
                            onOpenSettings = { scope.launch { drawerState.open() } },
                            onStartTutorial = {
                                tutorialTrigger += 1
                                showHome = false
                                tab = 0
                            },
                            onOpenPresets = {
                                showHome = false
                                tab = 1
                            }
                        )
                    } else when (tab) {
                        0 -> EditorScreen {
                            EditorTab(
                                vm = EditorVm(
                            lang = lang,
                            sourceBitmap = sourceBitmap,
                            asciiRaster = asciiPreviewBitmap,
                            sourceLabel = sourceLabel,
                            sourceKind = sourceKind,
                            sourceDurationMs = sourceDurationMs,
                            sourcePositionMs = sourcePositionMs,
                            sourcePlaying = sourcePlaying,
                            sourceFps = sourceFps,
                            onTogglePlay = { sourcePlaying = !sourcePlaying },
                            isFullscreen = editorFullscreen,
                            onToggleFullscreen = { editorFullscreen = !editorFullscreen },
                            onOpenGallery = { showHome = true },
                            onSeekMs = { ms ->
                                val d = sourceDurationMs.coerceAtLeast(0L)
                                sourcePositionMs = if (d > 0L) ms.coerceIn(0L, d) else 0L
                            },
                            onStepFrame = { dir ->
                                val frameMs = (1000f / sourceFps.coerceIn(6, 60)).roundToInt().toLong().coerceAtLeast(16L)
                                val d = sourceDurationMs.coerceAtLeast(0L)
                                val p = sourcePositionMs + (frameMs * dir.toLong())
                                sourcePositionMs = if (d > 0L) p.coerceIn(0L, d) else p.coerceAtLeast(0L)
                            },
                            mediaLoading = mediaLoading,
                            widthChars = widthChars,
                            onWidthChars = { widthChars = it },
                            charAspectRatio = charAspectRatio,
                            onCharAspectRatio = { charAspectRatio = it },
                            contrast = contrast,
                            onContrast = { contrast = it },
                            brightness = brightness,
                            onBrightness = { brightness = it },
                            gamma = gamma,
                            onGamma = { gamma = it },
                            saturation = saturation,
                            onSaturation = { saturation = it },
                            exposure = exposure,
                            onExposure = { exposure = it },
                            sharpen = sharpen,
                            onSharpen = { sharpen = it },
                            vignette = vignette,
                            onVignette = { vignette = it },
                            bloom = bloom,
                            onBloom = { bloom = it },
                            denoise = denoise,
                            onDenoise = { denoise = it },
                            edgeBoost = edgeBoost,
                            onEdgeBoost = { edgeBoost = it },
                            posterize = posterize,
                            onPosterize = { posterize = it },
                            scanlines = scanlines,
                            onScanlines = { scanlines = it },
                            scanStrength = scanStrength,
                            onScanStrength = { scanStrength = it },
                            scanStep = scanStep,
                            onScanStep = { scanStep = it },
                            dither = dither,
                            onDither = { dither = it },
                            curvature = curvature,
                            onCurvature = { curvature = it },
                            concavity = concavity,
                            onConcavity = { concavity = it },
                            curveCenterX = curveCenterX,
                            onCurveCenterX = { curveCenterX = it },
                            curveExpand = curveExpand,
                            onCurveExpand = { curveExpand = it },
                            curveType = curveType,
                            onCurveType = { curveType = it },
                            grain = grain,
                            onGrain = { grain = it },
                            chroma = chroma,
                            onChroma = { chroma = it },
                            ribbing = ribbing,
                            onRibbing = { ribbing = it },
                            clarity = clarity,
                            onClarity = { clarity = it },
                            motionBlur = motionBlur,
                            onMotionBlur = { motionBlur = it },
                            colorBoost = colorBoost,
                            onColorBoost = { colorBoost = it },
                            glitch = glitch,
                            onGlitch = { glitch = it },
                            glitchDensity = glitchDensity,
                            onGlitchDensity = { glitchDensity = it },
                            glitchShift = glitchShift,
                            onGlitchShift = { glitchShift = it },
                            glitchRgb = glitchRgb,
                            onGlitchRgb = { glitchRgb = it },
                            glitchBlock = glitchBlock,
                            onGlitchBlock = { glitchBlock = it },
                            glitchJitter = glitchJitter,
                            onGlitchJitter = { glitchJitter = it },
                            glitchNoise = glitchNoise,
                            onGlitchNoise = { glitchNoise = it },
                            renderFps = renderFps,
                            onRenderFps = { renderFps = it },
                            renderCodec = renderCodec,
                            onRenderCodec = { renderCodec = it },
                            renderBitrate = renderBitrate,
                            onRenderBitrate = { renderBitrate = it },
                            exportFormat = exportFormat,
                            onExportFormat = { exportFormat = it },
                            invert = invert,
                            onInvert = { invert = it },
                            preserveSourceColors = preserveSourceColors,
                            onPreserveSourceColors = { preserveSourceColors = it },
                            livePreviewEnabled = livePreviewEnabled,
                            onLivePreviewEnabled = { livePreviewEnabled = it },
                            glassBlurStrength = glassBlurStrength,
                            onGlassBlurStrength = { glassBlurStrength = it },
                            tutorialTrigger = tutorialTrigger,
                            settingsTrigger = openEditorSettingsSignal,
                            fontSize = fontSize,
                            onFontSize = { fontSize = it },
                            charsetKey = charsetKey,
                            onCharsetKey = { charsetKey = it },
                            watermarkEnabled = watermarkEnabled,
                            onWatermarkEnabled = { watermarkEnabled = it },
                            watermarkText = watermarkText,
                            onWatermarkText = { watermarkText = it },
                            previewScale = previewScale,
                            previewOffsetX = previewOffsetX,
                            previewOffsetY = previewOffsetY,
                            previewQualityName = previewQualityName,
                            onPreviewScale = { previewScale = it },
                            onPreviewOffsetX = { previewOffsetX = it },
                            onPreviewOffsetY = { previewOffsetY = it },
                            onPreviewQualityName = { previewQualityName = it },
                            ascii = ascii,
                            isRendering = isRendering,
                            onPick = {
                                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                            },
                            onClear = {
                                sourceBitmap = null
                                sourceLabel = s(R.string.no_media_selected)
                                sourceKind = "image"
                                sourceUriText = ""
                                sourceDurationMs = 0L
                                sourcePositionMs = 0L
                                sourceFps = 24
                                sourcePlaying = false
                                sourceGifBytes = null
                                sourceGifMovie = null
                                VideoFrameCache.clear()
                                ascii = ""
                                asciiPreviewBitmap = null
                                previewScale = 1f
                                previewOffsetX = 0f
                                previewOffsetY = 0f
                            },
                            onCopy = {
                                clipboard.copyAscii(ascii)
                                toast(context, s(R.string.ascii_copied))
                            },
                            onExport = {
                                if (ascii.isBlank()) {
                                    toast(context, s(R.string.nothing_to_export))
                                } else {
                                    val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
                                    val fmt = exportFormat.uppercase(Locale.US)
                                    val result = when (fmt) {
                                        "TXT" -> saveAsciiText(context, "ascii_$stamp.txt", ascii)
                                        "HTML" -> saveAsciiHtml(context, "ascii_$stamp.html", ascii)
                                        "SVG" -> saveAsciiSvg(
                                            context = context,
                                            fileName = "ascii_$stamp.svg",
                                            ascii = ascii,
                                            settings = RenderSettings(
                                                widthChars = widthChars,
                                                charAspectRatio = charAspectRatio,
                                                fontSizeSp = fontSize,
                                                charsetKey = charsetKey,
                                                charsetValue = CHARSETS[charsetKey] ?: CHARSETS.getValue("Classic")
                                            )
                                        )
                                        "JPG", "WEBP", "PNG" -> {
                                            val ext = if (fmt == "JPG") "jpg" else fmt.lowercase(Locale.US)
                                            saveAsciiRaster(
                                                context = context,
                                                fileName = "ascii_$stamp.$ext",
                                                ascii = ascii,
                                                fontSizeSp = fontSize,
                                                fgArgb = p.text.toArgb(),
                                                bgArgb = p.bg.toArgb(),
                                                format = ext,
                                                renderBitmap = renderOutput?.raster,
                                                targetWidth = sourceBitmap?.width,
                                                targetHeight = sourceBitmap?.height
                                            )
                                        }
                                        else -> saveAsciiText(context, "ascii_$stamp.txt", ascii)
                                    }
                                    when (fmt) {
                                        "HTML" -> if (result.isSuccess) toast(context, s(R.string.html_exported))
                                        "SVG" -> if (result.isSuccess) toast(context, s(R.string.svg_exported))
                                        "JPG", "WEBP", "PNG" -> if (result.isSuccess) toast(context, s(R.string.image_exported))
                                        else -> if (result.isSuccess) toast(context, s(R.string.txt_exported))
                                    }
                                    if (result.isFailure) {
                                        toast(context, s(R.string.export_failed))
                                    }
                                }
                            },
                            onSavePreset = {
                                val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
                                val preset = UasPreset(
                                    name = "mobile_$stamp",
                                    description = "ASCII Studio Mobile preset",
                                    settings = currentRenderSettings()
                                )
                                val result = savePresetFile(context, "mobile_$stamp.uaspreset", preset.toJsonString())
                                if (result.isSuccess) {
                                    toast(context, s(R.string.preset_saved))
                                } else {
                                    toast(context, s(R.string.export_failed))
                                }
                            },
                            onLoadPreset = {
                                loadPresetLauncher.launch(arrayOf("application/json", "text/plain", "*/*"))
                            }
                                )
                            )
                        }
                        1 -> PresetsScreen(lang) { preset ->
                            widthChars = preset.width
                            contrast = preset.contrast
                            brightness = preset.brightness
                            gamma = preset.gamma
                            saturation = preset.saturation
                            exposure = preset.exposure
                            sharpen = preset.sharpen
                            vignette = preset.vignette
                            bloom = 0f
                            denoise = 0f
                            edgeBoost = 0f
                            posterize = 0
                            scanlines = false
                            scanStrength = 0.22f
                            scanStep = 3
                            dither = false
                            curvature = 0f
                            concavity = 0f
                            curveCenterX = 0f
                            curveExpand = 0f
                            curveType = 0
                            grain = 0f
                            chroma = 0f
                            ribbing = 0f
                            clarity = 0f
                            motionBlur = 0f
                            colorBoost = 0f
                            glitch = 0f
                            glitchDensity = 0.35f
                            glitchShift = 0.42f
                            glitchRgb = true
                            glitchBlock = 0.10f
                            glitchJitter = 0.10f
                            glitchNoise = 0.12f
                            invert = preset.invert
                            charsetKey = preset.charsetKey
                            fontSize = preset.previewFont
                            tab = 0
                        }
                        2 -> ThemeScreen(lang, themeMode, { themeName = it.name }, tailEnabled, { tailEnabled = it },
                            bgR, bgG, bgB, panelR, panelG, panelB, accR, accG, accB, textR, textG, textB,
                            { bgR = it }, { bgG = it }, { bgB = it }, { panelR = it }, { panelG = it }, { panelB = it },
                            { accR = it }, { accG = it }, { accB = it }, { textR = it }, { textG = it }, { textB = it })
                        3 -> AboutScreen(lang) { uriHandler.openUri("https://github.com/SnerkK5/ultra_ascii_studio") }
                        else -> ArMockScreen()
                    }
                    TapTrailOverlay(tailEnabled, p.accent, Modifier.fillMaxSize())
                }
            }
        }
    }
}
}


private data class EditorVm(
    val lang: AppLanguage,
    val sourceBitmap: Bitmap?,
    val asciiRaster: Bitmap?,
    val sourceLabel: String,
    val sourceKind: String,
    val sourceDurationMs: Long,
    val sourcePositionMs: Long,
    val sourcePlaying: Boolean,
    val sourceFps: Int,
    val onTogglePlay: () -> Unit,
    val isFullscreen: Boolean,
    val onToggleFullscreen: () -> Unit,
    val onOpenGallery: () -> Unit,
    val onSeekMs: (Long) -> Unit,
    val onStepFrame: (Int) -> Unit,
    val mediaLoading: Boolean,
    val widthChars: Int,
    val onWidthChars: (Int) -> Unit,
    val charAspectRatio: Float,
    val onCharAspectRatio: (Float) -> Unit,
    val contrast: Float,
    val onContrast: (Float) -> Unit,
    val brightness: Float,
    val onBrightness: (Float) -> Unit,
    val gamma: Float,
    val onGamma: (Float) -> Unit,
    val saturation: Float,
    val onSaturation: (Float) -> Unit,
    val exposure: Float,
    val onExposure: (Float) -> Unit,
    val sharpen: Float,
    val onSharpen: (Float) -> Unit,
    val vignette: Float,
    val onVignette: (Float) -> Unit,
    val bloom: Float,
    val onBloom: (Float) -> Unit,
    val denoise: Float,
    val onDenoise: (Float) -> Unit,
    val edgeBoost: Float,
    val onEdgeBoost: (Float) -> Unit,
    val posterize: Int,
    val onPosterize: (Int) -> Unit,
    val scanlines: Boolean,
    val onScanlines: (Boolean) -> Unit,
    val scanStrength: Float,
    val onScanStrength: (Float) -> Unit,
    val scanStep: Int,
    val onScanStep: (Int) -> Unit,
    val dither: Boolean,
    val onDither: (Boolean) -> Unit,
    val curvature: Float,
    val onCurvature: (Float) -> Unit,
    val concavity: Float,
    val onConcavity: (Float) -> Unit,
    val curveCenterX: Float,
    val onCurveCenterX: (Float) -> Unit,
    val curveExpand: Float,
    val onCurveExpand: (Float) -> Unit,
    val curveType: Int,
    val onCurveType: (Int) -> Unit,
    val grain: Float,
    val onGrain: (Float) -> Unit,
    val chroma: Float,
    val onChroma: (Float) -> Unit,
    val ribbing: Float,
    val onRibbing: (Float) -> Unit,
    val clarity: Float,
    val onClarity: (Float) -> Unit,
    val motionBlur: Float,
    val onMotionBlur: (Float) -> Unit,
    val colorBoost: Float,
    val onColorBoost: (Float) -> Unit,
    val glitch: Float,
    val onGlitch: (Float) -> Unit,
    val glitchDensity: Float,
    val onGlitchDensity: (Float) -> Unit,
    val glitchShift: Float,
    val onGlitchShift: (Float) -> Unit,
    val glitchRgb: Boolean,
    val onGlitchRgb: (Boolean) -> Unit,
    val glitchBlock: Float,
    val onGlitchBlock: (Float) -> Unit,
    val glitchJitter: Float,
    val onGlitchJitter: (Float) -> Unit,
    val glitchNoise: Float,
    val onGlitchNoise: (Float) -> Unit,
    val renderFps: Int,
    val onRenderFps: (Int) -> Unit,
    val renderCodec: String,
    val onRenderCodec: (String) -> Unit,
    val renderBitrate: String,
    val onRenderBitrate: (String) -> Unit,
    val exportFormat: String,
    val onExportFormat: (String) -> Unit,
    val invert: Boolean,
    val onInvert: (Boolean) -> Unit,
    val preserveSourceColors: Boolean,
    val onPreserveSourceColors: (Boolean) -> Unit,
    val livePreviewEnabled: Boolean,
    val onLivePreviewEnabled: (Boolean) -> Unit,
    val glassBlurStrength: Float,
    val onGlassBlurStrength: (Float) -> Unit,
    val tutorialTrigger: Int,
    val settingsTrigger: Int,
    val fontSize: Float,
    val onFontSize: (Float) -> Unit,
    val charsetKey: String,
    val onCharsetKey: (String) -> Unit,
    val watermarkEnabled: Boolean,
    val onWatermarkEnabled: (Boolean) -> Unit,
    val watermarkText: String,
    val onWatermarkText: (String) -> Unit,
    val previewScale: Float,
    val previewOffsetX: Float,
    val previewOffsetY: Float,
    val previewQualityName: String,
    val onPreviewScale: (Float) -> Unit,
    val onPreviewOffsetX: (Float) -> Unit,
    val onPreviewOffsetY: (Float) -> Unit,
    val onPreviewQualityName: (String) -> Unit,
    val ascii: String,
    val isRendering: Boolean,
    val onPick: () -> Unit,
    val onClear: () -> Unit,
    val onCopy: () -> Unit,
    val onExport: () -> Unit,
    val onSavePreset: () -> Unit,
    val onLoadPreset: () -> Unit
)

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun EditorTab(vm: EditorVm) {
    with(vm) {
    val context = LocalContext.current
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val p = AsciiTheme.palette
    var settingsPage by rememberSaveable { mutableIntStateOf(0) }
    var showAdvanced by rememberSaveable { mutableStateOf(false) }
    var previewMode by rememberSaveable { mutableIntStateOf(1) }
    var previewFill by rememberSaveable { mutableStateOf(false) }
    var activeCategory by rememberSaveable { mutableStateOf("Hot") }
    var activePreset by rememberSaveable { mutableStateOf(QUICK_PRESETS.firstOrNull()?.name ?: "") }
    var tutorialStep by rememberSaveable { mutableIntStateOf(0) }
    var showSettingsSheet by rememberSaveable { mutableStateOf(false) }
    val settingsScroll = rememberScrollState()
    val presetScroll = rememberScrollState()
    val asciiVScroll = rememberScrollState()
    val asciiHScroll = rememberScrollState()

    LaunchedEffect(tutorialTrigger) {
        if (tutorialTrigger > 0) {
            tutorialStep = 1
        }
    }
    LaunchedEffect(settingsTrigger) {
        if (settingsTrigger > 0) {
            settingsPage = 0
            showSettingsSheet = true
        }
    }

    var stageWidthPx by remember { mutableFloatStateOf(1f) }
    var stageHeightPx by remember { mutableFloatStateOf(1f) }

    fun clampX(value: Float, scale: Float): Float {
        val pad = 32f
        val maxOffset = ((scale - 1f) * stageWidthPx * 0.5f + pad).coerceAtLeast(0f)
        return value.coerceIn(-maxOffset, maxOffset)
    }

    fun clampY(value: Float, scale: Float): Float {
        val pad = 32f
        val maxOffset = ((scale - 1f) * stageHeightPx * 0.5f + pad).coerceAtLeast(0f)
        return value.coerceIn(-maxOffset, maxOffset)
    }

    val smoothScale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = previewScale,
        animationSpec = tween(durationMillis = 140),
        label = "smooth-preview-scale"
    )

    val transformState = rememberTransformableState { zoomChange, panChange, _ ->
        val nextScale = (previewScale * zoomChange).coerceIn(1f, 5f)
        onPreviewScale(nextScale)
        onPreviewOffsetX(clampX(previewOffsetX + panChange.x, nextScale))
        onPreviewOffsetY(clampY(previewOffsetY + panChange.y, nextScale))
    }

    val panModifier = Modifier.pointerInput(previewScale, stageWidthPx, stageHeightPx) {
        detectDragGestures { _: PointerInputChange, dragAmount: Offset ->
            onPreviewOffsetX(clampX(previewOffsetX + dragAmount.x, previewScale))
            onPreviewOffsetY(clampY(previewOffsetY + dragAmount.y, previewScale))
        }
    }

    fun applyStylePreset(name: String) {
        when (name.lowercase(Locale.US)) {
            "soft" -> {
                onBloom(0.12f)
                onVignette(0.10f)
                onGrain(0.10f)
                onClarity(0.08f)
                onGlitch(0f)
                onScanlines(false)
                onDither(false)
                onColorBoost(0.12f)
            }
            "cyber" -> {
                onBloom(0.22f)
                onVignette(0.20f)
                onGrain(0.08f)
                onClarity(0.28f)
                onScanlines(true)
                onScanStrength(0.30f)
                onDither(true)
                onColorBoost(0.35f)
                onGlitch(0.22f)
            }
            "cinematic" -> {
                onContrast(1.25f)
                onGamma(0.95f)
                onBloom(0.18f)
                onVignette(0.26f)
                onColorBoost(0.18f)
                onGrain(0.12f)
                onClarity(0.16f)
                onGlitch(0f)
            }
            "retro" -> {
                onScanlines(true)
                onScanStrength(0.34f)
                onScanStep(3)
                onDither(true)
                onCurvature(0.28f)
                onConcavity(0.12f)
                onRibbing(0.22f)
                onPosterize(3)
                onBloom(0.10f)
                onVignette(0.18f)
            }
            "vhs" -> {
                onScanlines(true)
                onScanStrength(0.40f)
                onScanStep(2)
                onDither(true)
                onChroma(0.30f)
                onGrain(0.24f)
                onMotionBlur(0.20f)
                onRibbing(0.26f)
                onGlitch(0.32f)
            }
            "clean" -> {
                onBloom(0f)
                onVignette(0f)
                onGrain(0f)
                onRibbing(0f)
                onMotionBlur(0f)
                onGlitch(0f)
                onDither(false)
                onScanlines(false)
                onColorBoost(0.05f)
                onClarity(0.12f)
                onPosterize(0)
                onDenoise(0.10f)
                onSharpen(0.10f)
            }
        }
    }

    fun applyQuickPreset(item: QuickPresetItem) {
        activePreset = item.name
        onWidthChars(item.width.coerceIn(64, 260))
        onCharsetKey(item.charset)
        applyStylePreset(item.style)
    }

    val categories = listOf("Hot", "Retro", "Scenery", "Life", "Pro", "Edit")
    val visiblePresets = if (activeCategory == "Edit" || activeCategory == "Pro") QUICK_PRESETS else QUICK_PRESETS.filter { it.category == activeCategory }
    val thumbBase = remember(context) { generatePresetSampleBitmap(context, 320, 520) }
    val presetThumbs by produceState<Map<String, Bitmap>>(
        initialValue = emptyMap(),
        activeCategory,
        p.text,
        p.bg
    ) {
        val toRender = visiblePresets.take(10)
        value = withContext(Dispatchers.Default) {
            toRender.associate { item ->
                val art = buildQuickPresetPreviewAscii(item, thumbBase)
                item.name to rasterizeAsciiToBitmap(
                    context = context,
                    ascii = art,
                    fontSizeSp = 7.6f,
                    fgArgb = Color(0xFFF2F7FF).toArgb(),
                    bgArgb = Color(0xFF0A0F18).toArgb(),
                    targetWidth = 168,
                    targetHeight = 96
                )
            }
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.56f)),
            border = BorderStroke(1.dp, p.border.copy(alpha = 0.78f)),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onOpenGallery,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Icon(Icons.Filled.Tune, null, Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.projects), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    OutlinedButton(
                        onClick = onPick,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Icon(Icons.Filled.Image, null, Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.import_action), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    OutlinedButton(
                        onClick = onToggleFullscreen,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Text(
                            if (isFullscreen) s(R.string.windowed) else s(R.string.fullscreen),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = { tutorialStep = 1 },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Icon(Icons.Filled.Info, null, Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.tutorial_title), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    OutlinedButton(
                        onClick = { showSettingsSheet = true },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Icon(Icons.Filled.Settings, null, Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.full_settings), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    Button(
                        onClick = onExport,
                        enabled = ascii.isNotBlank(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB7FF2A), contentColor = Color.Black),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.weight(1f).heightIn(min = 36.dp)
                    ) {
                        Icon(Icons.Filled.SaveAlt, null, Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.export), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }

        Card(
            shape = RoundedCornerShape(22.dp),
            colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.60f)),
            border = BorderStroke(1.dp, p.border.copy(alpha = 0.74f)),
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .heightIn(min = 220.dp)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(p.bg.copy(alpha = 0.88f), RoundedCornerShape(22.dp))
                    .border(1.dp, p.border.copy(alpha = 0.55f), RoundedCornerShape(22.dp))
                    .clip(RoundedCornerShape(22.dp))
                    .onSizeChanged {
                        stageWidthPx = it.width.toFloat().coerceAtLeast(1f)
                        stageHeightPx = it.height.toFloat().coerceAtLeast(1f)
                    }
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .pointerInput(Unit) {
                            detectTapGestures(onDoubleTap = {
                                onPreviewScale(1f)
                                onPreviewOffsetX(0f)
                                onPreviewOffsetY(0f)
                            })
                        }
                        .then(panModifier)
                        .transformable(transformState)
                ) {
                    if (sourceBitmap == null) {
                        Column(
                            modifier = Modifier.align(Alignment.Center).padding(16.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(s(R.string.import_media_to_start_editing), color = p.textSubtle)
                            Button(onClick = onPick, shape = RoundedCornerShape(12.dp)) {
                                Icon(Icons.Filled.Image, null)
                                Spacer(Modifier.width(6.dp))
                                Text(s(R.string.import_media))
                            }
                        }
                    } else {
                        if (previewMode != 2) {
                            Image(
                                bitmap = sourceBitmap.asImageBitmap(),
                                contentDescription = null,
                                contentScale = if (previewFill) ContentScale.Crop else ContentScale.Fit,
                                modifier = Modifier.fillMaxSize().graphicsLayer {
                                    scaleX = smoothScale
                                    scaleY = smoothScale
                                    translationX = previewOffsetX
                                    translationY = previewOffsetY
                                }
                            )
                        }
                        if (livePreviewEnabled && previewMode != 0 && asciiRaster != null) {
                            Image(
                                bitmap = asciiRaster.asImageBitmap(),
                                contentDescription = null,
                                contentScale = if (previewFill) ContentScale.Crop else ContentScale.Fit,
                                modifier = Modifier.fillMaxSize().graphicsLayer {
                                    scaleX = smoothScale
                                    scaleY = smoothScale
                                    translationX = previewOffsetX
                                    translationY = previewOffsetY
                                    alpha = if (previewMode == 1) 0.74f else 1f
                                }
                            )
                        }
                        if (livePreviewEnabled && previewMode != 0 && ascii.isNotBlank() && asciiRaster == null) {
                            SelectionContainer {
                                Text(
                                    ascii,
                                    modifier = Modifier.fillMaxSize().padding(8.dp).verticalScroll(asciiVScroll).horizontalScroll(asciiHScroll).graphicsLayer {
                                        scaleX = smoothScale
                                        scaleY = smoothScale
                                        translationX = previewOffsetX
                                        translationY = previewOffsetY
                                    },
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = fontSize.sp,
                                    lineHeight = (fontSize * 1.08f).sp,
                                    color = if (previewMode == 1) p.text.copy(alpha = 0.72f) else p.text
                                )
                            }
                        }
                    }
                }

                if (mediaLoading || isRendering) {
                    CircularProgressIndicator(Modifier.align(Alignment.TopEnd).padding(10.dp).size(20.dp), strokeWidth = 2.dp)
                }
                if (!livePreviewEnabled && sourceBitmap != null) {
                    Card(
                        modifier = Modifier.align(Alignment.TopStart).padding(10.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.8f)),
                        border = BorderStroke(1.dp, p.border.copy(alpha = 0.45f))
                    ) {
                        Text(
                            s(R.string.live_preview_disabled_hint),
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = p.textSubtle
                        )
                    }
                }

                Card(
                    modifier = Modifier.align(Alignment.BottomStart).padding(10.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.70f)),
                    border = BorderStroke(1.dp, p.border.copy(alpha = 0.45f))
                ) {
                    Column(modifier = Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilterChip(selected = previewMode == 0, onClick = { previewMode = 0 }, label = { Text(s(R.string.media_mode)) })
                            FilterChip(selected = previewMode == 1, onClick = { previewMode = 1 }, label = { Text(s(R.string.mix_mode)) })
                            FilterChip(selected = previewMode == 2, onClick = { previewMode = 2 }, label = { Text(s(R.string.ascii_mode)) })
                            AssistChip(onClick = { previewFill = !previewFill }, label = { Text(if (previewFill) s(R.string.fill) else s(R.string.fit)) })
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(s(R.string.zoom) + " ${"%.2f".format(Locale.US, previewScale)}x", style = MaterialTheme.typography.labelSmall, color = p.textSubtle)
                            Slider(value = previewScale, onValueChange = { onPreviewScale(it.coerceIn(1f, 5f)) }, valueRange = 1f..5f, modifier = Modifier.width(150.dp))
                            TextButton(onClick = {
                                onPreviewScale(1f)
                                onPreviewOffsetX(0f)
                                onPreviewOffsetY(0f)
                            }) {
                                Text(s(R.string.reset))
                            }
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Preview", style = MaterialTheme.typography.labelSmall, color = p.textSubtle)
                            FilterChip(
                                selected = previewQualityName == PreviewQuality.Draft.name,
                                onClick = { onPreviewQualityName(PreviewQuality.Draft.name) },
                                label = { Text(s(R.string.quality_draft)) }
                            )
                            FilterChip(
                                selected = previewQualityName == PreviewQuality.Normal.name,
                                onClick = { onPreviewQualityName(PreviewQuality.Normal.name) },
                                label = { Text(s(R.string.quality_normal)) }
                            )
                            FilterChip(
                                selected = previewQualityName == PreviewQuality.High.name,
                                onClick = { onPreviewQualityName(PreviewQuality.High.name) },
                                label = { Text(s(R.string.quality_high)) }
                            )
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            AssistChip(
                                onClick = { onLivePreviewEnabled(!livePreviewEnabled) },
                                label = { Text(if (livePreviewEnabled) s(R.string.live_preview_on) else s(R.string.live_preview_off)) }
                            )
                            AssistChip(
                                onClick = { onPreserveSourceColors(!preserveSourceColors) },
                                label = { Text(if (preserveSourceColors) s(R.string.keep_source_colors_on) else s(R.string.keep_source_colors_off)) }
                            )
                        }
                    }
                }
            }
        }

        if (sourceKind != "image" && sourceDurationMs > 0L) {
            Card(
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.52f)),
                border = BorderStroke(1.dp, p.border.copy(alpha = 0.64f)),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = { onStepFrame(-1) }, shape = RoundedCornerShape(10.dp)) { Text("-1f") }
                        Button(onClick = onTogglePlay, shape = RoundedCornerShape(10.dp)) {
                            Text(if (sourcePlaying) s(R.string.pause) else s(R.string.play))
                        }
                        OutlinedButton(onClick = { onStepFrame(1) }, shape = RoundedCornerShape(10.dp)) { Text("+1f") }
                        Text("${formatMs(sourcePositionMs)} / ${formatMs(sourceDurationMs)}", color = p.textSubtle, style = MaterialTheme.typography.labelSmall)
                        Spacer(Modifier.weight(1f))
                        Text("${sourceFps} FPS", color = p.textSubtle, style = MaterialTheme.typography.labelSmall)
                    }
                    Slider(value = sourcePositionMs.coerceIn(0L, sourceDurationMs).toFloat(), onValueChange = { onSeekMs(it.roundToInt().toLong()) }, valueRange = 0f..sourceDurationMs.toFloat().coerceAtLeast(1f))
                }
            }
        }
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.58f)),
            border = BorderStroke(1.dp, p.border.copy(alpha = 0.70f)),
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 180.dp, max = 336.dp)
        ) {
            Box {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(p.panel.copy(alpha = 0.24f))
                        .blur((10f + glassBlurStrength * 14f).dp)
                )
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(10.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(s(R.string.style_filters), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.weight(1f))
                        AssistChip(onClick = { showAdvanced = !showAdvanced }, label = { Text(if (showAdvanced) s(R.string.advanced_on) else s(R.string.advanced_off)) })
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        categories.forEach { cat ->
                            FilterChip(selected = activeCategory == cat, onClick = { activeCategory = cat }, label = { Text(cat) })
                        }
                    }
                    Row(modifier = Modifier.fillMaxWidth().horizontalScroll(presetScroll), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        visiblePresets.forEach { item ->
                            Card(
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(containerColor = if (activePreset == item.name) p.accent.copy(alpha = 0.18f) else p.panel.copy(alpha = 0.68f)),
                                border = BorderStroke(1.dp, if (activePreset == item.name) p.accent else p.border.copy(alpha = 0.48f)),
                                modifier = Modifier.width(146.dp).pointerInput(item.name) { detectTapGestures(onTap = { applyQuickPreset(item) }) }
                            ) {
                                Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                    val thumb = presetThumbs[item.name]
                                    if (thumb != null) {
                                        Image(
                                            bitmap = thumb.asImageBitmap(),
                                            contentDescription = item.name,
                                            contentScale = ContentScale.Crop,
                                            modifier = Modifier.fillMaxWidth().height(80.dp).clip(RoundedCornerShape(8.dp))
                                        )
                                    }
                                    Text(item.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(item.category, style = MaterialTheme.typography.labelSmall, color = p.textSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                            }
                        }
                    }
                    HorizontalDivider(color = p.border.copy(alpha = 0.32f))
                    Text(s(R.string.preview_controls), style = MaterialTheme.typography.labelLarge, color = p.textSubtle)
                    QuickSliderRow(
                        icon = { Icon(Icons.Filled.Tune, null, Modifier.size(16.dp), tint = p.textSubtle) },
                        label = tr(lang, "Contrast", "Контраст", "对比度"),
                        value = contrast,
                        valueRange = 0.4f..2.2f,
                        onValueChange = { onContrast(it.coerceIn(0.4f, 2.2f)) }
                    )
                    QuickSliderRow(
                        icon = { Icon(Icons.Filled.Image, null, Modifier.size(16.dp), tint = p.textSubtle) },
                        label = tr(lang, "Brightness", "Яркость", "亮度"),
                        value = brightness,
                        valueRange = -0.6f..0.6f,
                        onValueChange = { onBrightness(it.coerceIn(-0.6f, 0.6f)) }
                    )
                    QuickSliderRow(
                        icon = { Icon(Icons.Filled.AutoAwesome, null, Modifier.size(16.dp), tint = p.textSubtle) },
                        label = tr(lang, "Noise", "Шум", "噪点"),
                        value = grain,
                        valueRange = 0f..1f,
                        onValueChange = { onGrain(it.coerceIn(0f, 1f)) }
                    )
                    FlowRow(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedButton(
                            onClick = { applyStylePreset(activePreset) },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.widthIn(min = 84.dp)
                        ) {
                            Text(s(R.string.tool_auto), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        OutlinedButton(
                            onClick = { previewFill = !previewFill },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.widthIn(min = 84.dp)
                        ) {
                            Text(s(R.string.tool_crop), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        OutlinedButton(
                            onClick = { onPreviewScale((previewScale + 0.15f).coerceIn(1f, 5f)) },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.widthIn(min = 84.dp)
                        ) {
                            Text(s(R.string.tool_ratio), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        OutlinedButton(
                            onClick = { settingsPage = 2; showSettingsSheet = true },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.widthIn(min = 84.dp)
                        ) {
                            Text(s(R.string.tool_draw), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Button(
                            onClick = {
                                settingsPage = (settingsPage + 1) % 5
                                showSettingsSheet = true
                            },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.widthIn(min = 84.dp)
                        ) {
                            Text(s(R.string.next_action), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }

        if (showSettingsSheet) {
            ModalBottomSheet(
                onDismissRequest = { showSettingsSheet = false },
                containerColor = p.panelStrong.copy(alpha = 0.96f)
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).verticalScroll(settingsScroll),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(s(R.string.full_settings), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf(s(R.string.basic), s(R.string.color), s(R.string.fx), s(R.string.pro), s(R.string.render)).forEachIndexed { idx, label ->
                            FilterChip(selected = settingsPage == idx, onClick = { settingsPage = idx }, label = { Text(label) })
                        }
                    }
                    when (settingsPage) {
                        0 -> {
                            SliderRow(tr(lang, "Width", "Ширина", "宽度"), widthChars.toFloat(), { onWidthChars(it.roundToInt().coerceIn(64, 260)) }, 64f..260f, widthChars.toString())
                            SliderRow(s(R.string.char_aspect), charAspectRatio, { onCharAspectRatio(it.coerceIn(0.30f, 1.20f)) }, 0.30f..1.20f, "%.2f".format(Locale.US, charAspectRatio))
                            SliderRow(tr(lang, "Font", "Шрифт", "字体"), fontSize, { onFontSize(it.coerceIn(5f, 14f)) }, 5f..14f, "%.1f".format(Locale.US, fontSize))
                            SliderRow(tr(lang, "Contrast", "Контраст", "对比度"), contrast, { onContrast(it.coerceIn(0.4f, 2.2f)) }, 0.4f..2.2f, "%.2f".format(Locale.US, contrast))
                            SliderRow(tr(lang, "Brightness", "Яркость", "亮度"), brightness, { onBrightness(it.coerceIn(-0.6f, 0.6f)) }, -0.6f..0.6f, "%.2f".format(Locale.US, brightness))
                            SliderRow(tr(lang, "Saturation", "Насыщенность", "饱和度"), saturation, { onSaturation(it.coerceIn(0f, 2f)) }, 0f..2f, "%.2f".format(Locale.US, saturation))
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                CHARSETS.keys.forEach { key ->
                                    FilterChip(selected = charsetKey == key, onClick = { onCharsetKey(key) }, label = { Text(key) })
                                }
                            }
                            ToggleRow(tr(lang, "Invert", "Инверсия", "反色"), invert, onInvert)
                            ToggleRow(s(R.string.live_preview), livePreviewEnabled, onLivePreviewEnabled)
                            ToggleRow(s(R.string.keep_source_colors), preserveSourceColors, onPreserveSourceColors)
                        }
                        1 -> {
                            SliderRow(tr(lang, "Exposure", "Экспозиция", "曝光"), exposure, { onExposure(it.coerceIn(-0.8f, 0.8f)) }, -0.8f..0.8f, "%.2f".format(Locale.US, exposure))
                            SliderRow(tr(lang, "Sharpen", "Резкость", "锐化"), sharpen, { onSharpen(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, sharpen))
                            SliderRow(tr(lang, "Denoise", "Шумоподавление", "降噪"), denoise, { onDenoise(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, denoise))
                            SliderRow(tr(lang, "Edge Boost", "Усиление краёв", "边缘增强"), edgeBoost, { onEdgeBoost(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, edgeBoost))
                            SliderRow(tr(lang, "Color Boost", "Усиление цвета", "色彩增强"), colorBoost, { onColorBoost(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, colorBoost))
                            SliderRow(tr(lang, "Posterize", "Постеризация", "色阶减少"), posterize.toFloat(), { onPosterize(it.roundToInt().coerceIn(0, 8)) }, 0f..8f, posterize.toString())
                        }
                        2 -> {
                            SliderRow(tr(lang, "Bloom", "Свечение", "泛光"), bloom, { onBloom(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, bloom))
                            SliderRow(tr(lang, "Motion Blur", "Размытие движения", "运动模糊"), motionBlur, { onMotionBlur(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, motionBlur))
                            ToggleRow(tr(lang, "Scanlines", "Скан-линии", "扫描线"), scanlines, onScanlines)
                            if (scanlines) {
                                SliderRow(tr(lang, "Scan Strength", "Сила скан-линий", "扫描强度"), scanStrength, { onScanStrength(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, scanStrength))
                                SliderRow(tr(lang, "Scan Step", "Шаг скан-линий", "扫描间隔"), scanStep.toFloat(), { onScanStep(it.roundToInt().coerceIn(1, 8)) }, 1f..8f, scanStep.toString())
                            }
                            SliderRow(tr(lang, "Glitch", "Глитч", "故障"), glitch, { onGlitch(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, glitch))
                            if (showAdvanced || glitch > 0f) {
                                SliderRow(tr(lang, "Glitch Density", "Плотность глитча", "故障密度"), glitchDensity, { onGlitchDensity(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, glitchDensity))
                                SliderRow(tr(lang, "Glitch Shift", "Смещение глитча", "故障偏移"), glitchShift, { onGlitchShift(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, glitchShift))
                            }
                        }
                        3 -> {
                            SliderRow(tr(lang, "Curvature", "Выпуклость", "凸面"), curvature, { onCurvature(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, curvature))
                            SliderRow(tr(lang, "Concavity", "Вогнутость", "凹面"), concavity, { onConcavity(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, concavity))
                            SliderRow(tr(lang, "Center X", "Центр X", "中心 X"), curveCenterX, { onCurveCenterX(it.coerceIn(-1f, 1f)) }, -1f..1f, "%.2f".format(Locale.US, curveCenterX))
                            SliderRow(tr(lang, "Expand", "Расширение", "扩展"), curveExpand, { onCurveExpand(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, curveExpand))
                            SliderRow(s(R.string.glass_blur), glassBlurStrength, { onGlassBlurStrength(it.coerceIn(0f, 1f)) }, 0f..1f, "%.2f".format(Locale.US, glassBlurStrength))
                            ToggleRow(s(R.string.watermark), watermarkEnabled, onWatermarkEnabled)
                            if (watermarkEnabled) {
                                OutlinedTextField(
                                    value = watermarkText,
                                    onValueChange = { onWatermarkText(it.take(24)) },
                                    modifier = Modifier.fillMaxWidth(),
                                    singleLine = true,
                                    label = { Text(s(R.string.watermark_text)) }
                                )
                            }
                        }
                        else -> {
                            SliderRow(tr(lang, "FPS", "FPS", "FPS"), renderFps.toFloat(), { onRenderFps(it.roundToInt().coerceIn(12, 60)) }, 12f..60f, renderFps.toString())
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                listOf("libx264", "mpeg4", "libvpx", "h264").forEach { c -> FilterChip(selected = renderCodec == c, onClick = { onRenderCodec(c) }, label = { Text(c) }) }
                            }
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                listOf("500k", "1M", "2M", "4M", "8M", "10M").forEach { b -> FilterChip(selected = renderBitrate == b, onClick = { onRenderBitrate(b) }, label = { Text(b) }) }
                            }
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                listOf("PNG", "JPG", "WEBP", "TXT", "HTML", "SVG").forEach { f -> FilterChip(selected = exportFormat == f, onClick = { onExportFormat(f) }, label = { Text(f) }) }
                            }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = onSavePreset, shape = RoundedCornerShape(10.dp)) { Text(s(R.string.save_uaspreset)) }
                        OutlinedButton(onClick = onLoadPreset, shape = RoundedCornerShape(10.dp)) { Text(s(R.string.load_uaspreset)) }
                        Spacer(Modifier.weight(1f))
                        Button(onClick = { showSettingsSheet = false }, shape = RoundedCornerShape(10.dp)) { Text(s(R.string.done)) }
                    }
                    Spacer(Modifier.height(18.dp))
                }
            }
        }

        Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.56f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.66f)), modifier = Modifier.fillMaxWidth()) {
            Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = onClear, shape = RoundedCornerShape(12.dp)) { Text(s(R.string.reset)) }
                Button(onClick = onCopy, enabled = ascii.isNotBlank(), shape = RoundedCornerShape(12.dp)) {
                    Icon(Icons.Filled.ContentCopy, null)
                    Spacer(Modifier.width(4.dp))
                    Text(s(R.string.copy))
                }
                Spacer(Modifier.weight(1f))
                Button(onClick = onExport, enabled = ascii.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB7FF2A), contentColor = Color.Black), shape = RoundedCornerShape(12.dp)) {
                    Icon(Icons.Filled.SaveAlt, null)
                    Spacer(Modifier.width(4.dp))
                    Text(s(R.string.export))
                }
            }
        }

        AnimatedVisibility(
            visible = tutorialStep in 1..5,
            enter = fadeIn(animationSpec = tween(160)),
            exit = fadeOut(animationSpec = tween(130))
        ) {
            val tutorialText = when (tutorialStep) {
                1 -> s(R.string.tutorial_step_1)
                2 -> s(R.string.tutorial_step_2)
                3 -> s(R.string.tutorial_step_3)
                4 -> s(R.string.tutorial_step_4)
                else -> s(R.string.tutorial_step_5)
            }
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.62f))
                    .pointerInput(tutorialStep) {
                        detectTapGestures(onTap = {
                            tutorialStep = if (tutorialStep >= 5) 0 else tutorialStep + 1
                        })
                    }
            ) {
                Card(
                    shape = RoundedCornerShape(18.dp),
                    colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.94f)),
                    border = BorderStroke(1.dp, p.border.copy(alpha = 0.72f)),
                    modifier = Modifier.align(Alignment.Center).padding(horizontal = 18.dp).fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(s(R.string.tutorial_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        Text(tutorialText, color = p.textSubtle)
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                s(R.string.tutorial_tap_continue),
                                style = MaterialTheme.typography.labelSmall,
                                color = p.textSubtle,
                                modifier = Modifier.weight(1f),
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            OutlinedButton(
                                onClick = { tutorialStep = if (tutorialStep >= 5) 0 else tutorialStep + 1 },
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Text(s(R.string.next_action))
                            }
                            TextButton(onClick = { tutorialStep = 0 }) {
                                Text(s(R.string.tutorial_skip))
                            }
                        }
                    }
                }
            }
        }
}
}
}
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun HomeTab(
    lang: AppLanguage,
    projects: List<ProjectEntry>,
    onPickVideo: () -> Unit,
    onPickPhoto: () -> Unit,
    onOpenProject: (ProjectEntry) -> Unit,
    onOpenSettings: () -> Unit,
    onStartTutorial: () -> Unit,
    onOpenPresets: () -> Unit
) {
    val context = LocalContext.current
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val p = AsciiTheme.palette
    val latestProject = projects.firstOrNull()
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.66f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.68f))) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                AsciiAnimatedWordmark(
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 20.sp
                )
                Text(s(R.string.create_or_continue), color = p.textSubtle)
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    OutlinedButton(onClick = onStartTutorial, shape = RoundedCornerShape(10.dp)) {
                        Icon(Icons.Filled.Info, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.tutorial_title), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    OutlinedButton(onClick = onOpenSettings, shape = RoundedCornerShape(10.dp)) {
                        Icon(Icons.Filled.Settings, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.settings_menu), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    OutlinedButton(onClick = onOpenPresets, shape = RoundedCornerShape(10.dp)) {
                        Icon(Icons.Filled.AutoAwesome, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(s(R.string.presets), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    HomeActionCard(
                        title = s(R.string.new_video),
                        subtitle = tr(lang, "Video / GIF / audio-ready", "Video / GIF / audio-ready", "Video / GIF / audio-ready"),
                        icon = { Icon(Icons.Filled.AutoAwesome, null) },
                        onClick = onPickVideo,
                        modifier = Modifier.weight(1f)
                    )
                    HomeActionCard(
                        title = s(R.string.edit_photo),
                        subtitle = tr(lang, "Image editor workflow", "Image editor workflow", "Image editor workflow"),
                        icon = { Icon(Icons.Filled.Image, null) },
                        onClick = onPickPhoto,
                        modifier = Modifier.weight(1f)
                    )
                }
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = p.bgSecondary.copy(alpha = 0.42f)),
                    border = BorderStroke(1.dp, p.border.copy(alpha = 0.45f))
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("${s(R.string.projects)}: ${projects.size}", style = MaterialTheme.typography.labelMedium, color = p.textSubtle)
                        Spacer(Modifier.weight(1f))
                        if (latestProject != null) {
                            Text(
                                formatProjectDate(latestProject.updatedAt),
                                style = MaterialTheme.typography.labelSmall,
                                color = p.textSubtle,
                                maxLines = 1
                            )
                        }
                    }
                }
            }
        }

        if (latestProject != null) {
            Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.58f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.5f))) {
                Row(modifier = Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp), modifier = Modifier.weight(1f)) {
                        Text(s(R.string.continue_project), fontWeight = FontWeight.SemiBold)
                        Text("${latestProject.title} | ${formatMs(latestProject.durationMs)}", color = p.textSubtle, style = MaterialTheme.typography.bodySmall)
                    }
                    Button(onClick = { onOpenProject(latestProject) }, shape = RoundedCornerShape(10.dp)) {
                        Text(s(R.string.open))
                    }
                }
            }
        }

        Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.54f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.48f))) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(s(R.string.projects), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                if (projects.isEmpty()) {
                    Text(s(R.string.no_recent_projects), color = p.textSubtle)
                } else {
                    projects.take(40).forEach { entry ->
                        Row(
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(p.bgSecondary.copy(alpha = 0.45f)).pointerInput(entry.id) { detectTapGestures(onTap = { onOpenProject(entry) }) }.padding(10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(entry.title, maxLines = 1)
                                Text("${entry.kind.uppercase(Locale.US)} | ${formatMs(entry.durationMs)} | ${formatProjectDate(entry.updatedAt)}", color = p.textSubtle, style = MaterialTheme.typography.labelSmall)
                            }
                            OutlinedButton(onClick = { onOpenProject(entry) }, shape = RoundedCornerShape(10.dp)) {
                                Text(s(R.string.open))
                            }
                        }
                    }
                }
            }
        }

    }
}

@Composable
private fun HomeActionCard(
    title: String,
    subtitle: String,
    icon: @Composable () -> Unit,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val p = AsciiTheme.palette
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = p.panel.copy(alpha = 0.70f)),
        border = BorderStroke(1.dp, p.border.copy(alpha = 0.62f)),
        modifier = modifier.pointerInput(title) { detectTapGestures(onTap = { onClick() }) }
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            icon()
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(subtitle, color = p.textSubtle, style = MaterialTheme.typography.labelSmall)
        }
    }
}

private fun formatProjectDate(timestampMs: Long): String {
    val fmt = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault())
    return fmt.format(Date(timestampMs))
}

@Composable
private fun AsciiAnimatedWordmark(
    modifier: Modifier = Modifier,
    fontSize: TextUnit = 16.sp
) {
    val p = AsciiTheme.palette
    val frames = remember {
        listOf(
            "I5CII STUDIO",
            "IS[II STUDIO",
            "ISC!I STUDIO",
            "ISCII STUDIO",
            "ISCII STVDIO",
            "ISCII STUDIO"
        )
    }
    var frameIndex by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        while (isActive) {
            delay(180L)
            frameIndex = (frameIndex + 1) % frames.size
        }
    }
    Text(
        text = frames[frameIndex],
        modifier = modifier,
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.SemiBold,
        fontSize = fontSize,
        letterSpacing = 0.7.sp,
        color = p.text,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis
    )
}

@Composable
internal fun PresetsTab(lang: AppLanguage, onApply: (AsciiPreset) -> Unit) {
    val context = LocalContext.current
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val p = AsciiTheme.palette
    val sample = remember(context) { generatePresetSampleBitmap(context, 640, 360) }
    val previewByPreset = remember(sample) {
        PRESETS.associate { preset ->
            val charset = CHARSETS[preset.charsetKey] ?: CHARSETS.getValue("Classic")
            preset.id to bitmapToAsciiSync(
                bitmap = sample,
                widthChars = preset.width.coerceIn(70, 110),
                contrast = preset.contrast,
                brightness = preset.brightness,
                gamma = preset.gamma,
                saturation = preset.saturation,
                exposure = preset.exposure,
                sharpen = preset.sharpen,
                vignette = preset.vignette,
                invert = preset.invert,
                charset = charset
            )
        }
    }
    val previewImageByPreset = remember(sample, p.text, p.bg) {
        PRESETS.associate { preset ->
            val art = previewByPreset[preset.id].orEmpty()
            val bmp = rasterizeAsciiToBitmap(context, art, 7.4f, p.text.toArgb(), p.bg.toArgb())
            preset.id to Bitmap.createScaledBitmap(bmp, 640, 360, true)
        }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(s(R.string.preset_gallery), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(tr(lang, "Every preset has a rendered preview. Tap to apply and continue editing.", "Every preset has a rendered preview. Tap to apply and continue editing.", "Every preset has a rendered preview. Tap to apply and continue editing."), color = p.textSubtle)

        PRESETS.forEach { preset ->
            Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.60f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.58f))) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(preset.title(lang), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(preset.subtitle(lang), style = MaterialTheme.typography.bodySmall, color = p.textSubtle)
                    Text("W ${preset.width} | C ${"%.2f".format(Locale.US, preset.contrast)} | ${preset.charsetKey}", style = MaterialTheme.typography.labelSmall, color = p.textSubtle)
                    Box(modifier = Modifier.fillMaxWidth().height(170.dp).background(p.bg.copy(alpha = 0.78f), RoundedCornerShape(12.dp)).border(1.dp, p.border.copy(alpha = 0.48f), RoundedCornerShape(12.dp))) {
                        val pb = previewImageByPreset[preset.id]
                        if (pb != null) {
                            Image(pb.asImageBitmap(), preset.id, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                        } else {
                            SelectionContainer {
                                Text(previewByPreset[preset.id].orEmpty(), Modifier.padding(8.dp).verticalScroll(rememberScrollState()), fontFamily = FontFamily.Monospace, fontSize = 6.4.sp, lineHeight = 6.8.sp, color = p.text)
                            }
                        }
                    }
                    Text(s(R.string.preview_example_for_preset), style = MaterialTheme.typography.labelSmall, color = p.textSubtle)
                    Button(onClick = { onApply(preset) }, shape = RoundedCornerShape(14.dp)) {
                        Text(s(R.string.apply_preset))
                    }
                }
            }
        }
    }
}
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun ThemeTab(
    lang: AppLanguage,
    themeMode: MobileThemeMode,
    onThemeMode: (MobileThemeMode) -> Unit,
    tailEnabled: Boolean,
    onTailEnabled: (Boolean) -> Unit,
    bgR: Int,
    bgG: Int,
    bgB: Int,
    panelR: Int,
    panelG: Int,
    panelB: Int,
    accR: Int,
    accG: Int,
    accB: Int,
    textR: Int,
    textG: Int,
    textB: Int,
    onBgR: (Int) -> Unit,
    onBgG: (Int) -> Unit,
    onBgB: (Int) -> Unit,
    onPanelR: (Int) -> Unit,
    onPanelG: (Int) -> Unit,
    onPanelB: (Int) -> Unit,
    onAccR: (Int) -> Unit,
    onAccG: (Int) -> Unit,
    onAccB: (Int) -> Unit,
    onTextR: (Int) -> Unit,
    onTextG: (Int) -> Unit,
    onTextB: (Int) -> Unit
) {
    val context = LocalContext.current
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val p = AsciiTheme.palette
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.60f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.56f))) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(s(R.string.theme), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(s(R.string.pick_global_style), color = p.textSubtle)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    MobileThemeMode.entries.forEach { mode ->
                        FilterChip(selected = themeMode == mode, onClick = { onThemeMode(mode) }, label = { Text(mode.label(lang)) })
                    }
                }
                ToggleRow(s(R.string.interactive_touch_tail), tailEnabled, onTailEnabled)
            }
        }

        AnimatedVisibility(themeMode == MobileThemeMode.Custom, enter = fadeIn(), exit = fadeOut()) {
            Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.60f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.56f))) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(s(R.string.custom_theme_colors), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    ColorTripleSliders(lang, tr(lang, "Background", "Background", "Background"), bgR, bgG, bgB, onBgR, onBgG, onBgB)
                    ColorTripleSliders(lang, tr(lang, "Panel", "Panel", "Panel"), panelR, panelG, panelB, onPanelR, onPanelG, onPanelB)
                    ColorTripleSliders(lang, tr(lang, "Accent", "Accent", "Accent"), accR, accG, accB, onAccR, onAccG, onAccB)
                    ColorTripleSliders(lang, tr(lang, "Text", "Text", "Text"), textR, textG, textB, onTextR, onTextG, onTextB)
                }
            }
        }

    }
}

@Composable
private fun ColorTripleSliders(lang: AppLanguage, title: String, r: Int, g: Int, b: Int, onR: (Int) -> Unit, onG: (Int) -> Unit, onB: (Int) -> Unit) {
    val p = AsciiTheme.palette
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, color = p.textSubtle)
        SliderRow("${tr(lang, "Red", "Red", "Red")}: $r", r.toFloat(), { onR(it.roundToInt().coerceIn(0, 255)) }, 0f..255f, "")
        SliderRow("${tr(lang, "Green", "Green", "Green")}: $g", g.toFloat(), { onG(it.roundToInt().coerceIn(0, 255)) }, 0f..255f, "")
        SliderRow("${tr(lang, "Blue", "Blue", "Blue")}: $b", b.toFloat(), { onB(it.roundToInt().coerceIn(0, 255)) }, 0f..255f, "")
    }
}

@Composable
internal fun AboutTab(lang: AppLanguage, onOpenRepo: () -> Unit) {
    val context = LocalContext.current
    fun s(@StringRes id: Int): String = localizedString(context, lang, id)
    val p = AsciiTheme.palette
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.62f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.54f))) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("ASCII Studio Mobile", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text(tr(lang, "Modern mobile ASCII editor with real-time preview, presets, theme engine and export.", "Modern mobile ASCII editor with real-time preview, presets, theme engine and export.", "Modern mobile ASCII editor with real-time preview, presets, theme engine and export."), color = p.textSubtle)
                HorizontalDivider()
                Text(tr(lang, "Authors", "Authors", "Authors"), fontWeight = FontWeight.SemiBold)
                Text("SnerkK5 / SNERK503")
                Text(s(R.string.project_page), fontWeight = FontWeight.SemiBold)
                TextButton(onOpenRepo) { Text("https://github.com/SnerkK5/ultra_ascii_studio") }
            }
        }

        Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.62f)), border = BorderStroke(1.dp, p.border.copy(alpha = 0.54f))) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(s(R.string.current_mobile_features), fontWeight = FontWeight.SemiBold)
                Text("- " + s(R.string.feature_import))
                Text("- " + s(R.string.feature_live_ascii))
                Text("- " + s(R.string.feature_preset_gallery))
                Text("- " + s(R.string.feature_theme_system))
                Text("- " + s(R.string.feature_export_all))
                Text("- " + s(R.string.feature_touch_tail))
            }
        }
    }
}

@Composable
private fun SliderRow(label: String, value: Float, onValueChange: (Float) -> Unit, range: ClosedFloatingPointRange<Float>, valueText: String) {
    val p = AsciiTheme.palette
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = p.textSubtle,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (valueText.isNotBlank()) {
                Text(valueText, style = MaterialTheme.typography.labelSmall, color = p.textSubtle, maxLines = 1)
            }
        }
        Slider(value = value, onValueChange = onValueChange, valueRange = range)
    }
}

@Composable
private fun QuickSliderRow(
    icon: @Composable () -> Unit,
    label: String,
    value: Float,
    valueRange: ClosedFloatingPointRange<Float>,
    onValueChange: (Float) -> Unit
) {
    val p = AsciiTheme.palette
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        icon()
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = p.text,
            modifier = Modifier.width(96.dp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = valueRange,
            modifier = Modifier.weight(1f)
        )
        Text(
            "%.2f".format(Locale.US, value),
            style = MaterialTheme.typography.labelSmall,
            color = p.textSubtle
        )
    }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChecked: (Boolean) -> Unit) {
    val p = AsciiTheme.palette
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = p.textSubtle, style = MaterialTheme.typography.labelSmall)
        Switch(checked = checked, onCheckedChange = onChecked)
    }
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun TapTrailOverlay(enabled: Boolean, accent: Color, modifier: Modifier = Modifier) {
    val dots = remember { mutableStateListOf<TrailDot>() }
    var lastEmitMs by remember { mutableLongStateOf(0L) }

    LaunchedEffect(enabled) {
        while (isActive) {
            if (!enabled) {
                dots.clear()
                delay(64L)
                continue
            }
            if (dots.isNotEmpty()) {
                for (i in dots.lastIndex downTo 0) {
                    val d = dots[i]
                    val next = d.copy(y = d.y - 0.6f, radius = d.radius * 0.985f, life = d.life - 0.035f)
                    if (next.life <= 0f || next.radius < 1f) dots.removeAt(i) else dots[i] = next
                }
                delay(16L)
            } else {
                delay(42L)
            }
        }
    }

    Canvas(modifier.pointerInteropFilter { event ->
        if (!enabled) return@pointerInteropFilter false
        if (event.actionMasked == MotionEvent.ACTION_DOWN || event.actionMasked == MotionEvent.ACTION_MOVE) {
            val now = System.currentTimeMillis()
            if (now - lastEmitMs >= 12L) {
                lastEmitMs = now
                dots.add(TrailDot(event.x, event.y, 22f + event.pressure.coerceAtLeast(0.1f) * 14f, 1f))
                while (dots.size > 84) dots.removeAt(0)
            }
        }
        false
    }) {
        dots.forEach { d ->
            val center = Offset(d.x, d.y)
            drawCircle(color = accent.copy(alpha = 0.30f * d.life), radius = d.radius, center = center)
            drawCircle(color = Color.White.copy(alpha = 0.08f * d.life), radius = d.radius * 0.52f, center = center)
        }
    }
}

@Composable
private fun LiveThemeBackground(modifier: Modifier = Modifier, mode: MobileThemeMode) {
    val p = AsciiTheme.palette
    val transition = rememberInfiniteTransition(label = "live-bg")
    val t1 by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = if (mode == MobileThemeMode.Cyberpunk2077) 5200 else 7600, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "t1"
    )
    val t2 by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = if (mode == MobileThemeMode.Dedsec) 4300 else 6400, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "t2"
    )

    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val cx1 = w * (0.22f + t1 * 0.56f)
        val cy1 = h * (0.20f + t2 * 0.22f)
        val cx2 = w * (0.78f - t2 * 0.52f)
        val cy2 = h * (0.72f - t1 * 0.26f)
        val cx3 = w * (0.30f + t2 * 0.42f)
        val cy3 = h * (0.84f - t1 * 0.50f)
        val baseR = minOf(w, h) * 0.64f

        drawCircle(color = p.accent.copy(alpha = 0.18f), radius = baseR, center = Offset(cx1, cy1))
        drawCircle(color = p.accent2.copy(alpha = 0.14f), radius = baseR * 0.78f, center = Offset(cx2, cy2))
        drawCircle(color = p.border.copy(alpha = 0.12f), radius = baseR * 0.62f, center = Offset(cx3, cy3))

        val step = (48f + t1 * 20f)
        var x = -w
        while (x < w * 2f) {
            val alpha = 0.035f + ((x / w) * 0.01f).coerceIn(0f, 0.02f)
            drawLine(
                color = p.accent.copy(alpha = alpha),
                start = Offset(x + t2 * 120f, 0f),
                end = Offset(x - h * 0.55f + t2 * 120f, h),
                strokeWidth = 1.2f
            )
            x += step
        }
    }
}

private fun defaultLanguage(): AppLanguage {
    val code = Locale.getDefault().language.lowercase(Locale.US)
    return when {
        code.startsWith("ru") -> AppLanguage.Ru
        code.startsWith("zh") -> AppLanguage.Zh
        else -> AppLanguage.En
    }
}

private fun localizedString(context: Context, lang: AppLanguage, @StringRes id: Int): String {
    val locale = when (lang) {
        AppLanguage.En -> Locale.ENGLISH
        AppLanguage.Ru -> Locale("ru")
        AppLanguage.Zh -> Locale.SIMPLIFIED_CHINESE
    }
    val cfg = Configuration(context.resources.configuration)
    cfg.setLocale(locale)
    return context.createConfigurationContext(cfg).resources.getString(id)
}

private val RU_FALLBACK = mapOf(
    "Mobile ASCII Editor" to "Мобильный ASCII редактор",
    "Editor" to "Редактор",
    "Presets" to "Пресеты",
    "Theme" to "Тема",
    "About" to "О проекте",
    "Projects" to "Проекты",
    "Import" to "Импорт",
    "Import Media" to "Импорт медиа",
    "Export" to "Экспорт",
    "Fullscreen" to "Полный экран",
    "Windowed" to "Оконный",
    "Media selected" to "Медиа выбрано",
    "Import failed" to "Ошибка импорта",
    "No media selected" to "Медиа не выбрано",
    "ASCII copied" to "ASCII скопирован",
    "Nothing to export" to "Нечего экспортировать",
    "Export failed" to "Ошибка экспорта",
    "TXT exported" to "TXT экспортирован",
    "HTML exported" to "HTML экспортирован",
    "SVG exported" to "SVG экспортирован",
    "Image exported" to "Изображение экспортировано",
    "Create a new project or continue your latest work." to "Создайте новый проект или продолжите последний.",
    "New video" to "Новое видео",
    "Edit photo" to "Редактировать фото",
    "Continue project" to "Продолжить проект",
    "No recent projects yet." to "Пока нет недавних проектов.",
    "Open" to "Открыть",
    "Play" to "Пуск",
    "Pause" to "Пауза",
    "Reset" to "Сброс",
    "Copy" to "Копировать",
    "Quick Presets" to "Быстрые пресеты",
    "Preset Gallery" to "Галерея пресетов",
    "Preview example for this preset" to "Пример рендера для этого пресета",
    "Apply Preset" to "Применить пресет",
    "Preset saved" to "Пресет сохранён",
    "Preset loaded" to "Пресет загружен",
    "Projects imported" to "Проекты импортированы",
    "Pick a global style for the whole app." to "Выберите глобальный стиль для всего приложения.",
    "Interactive touch tail" to "Интерактивный хвост касаний",
    "Custom Theme Colors" to "Цвета кастомной темы"
)

private val ZH_FALLBACK = mapOf(
    "Mobile ASCII Editor" to "移动端 ASCII 编辑器",
    "Editor" to "编辑器",
    "Presets" to "预设",
    "Theme" to "主题",
    "About" to "关于",
    "Projects" to "项目",
    "Import" to "导入",
    "Import Media" to "导入媒体",
    "Export" to "导出",
    "Fullscreen" to "全屏",
    "Windowed" to "窗口",
    "Media selected" to "已选择媒体",
    "Import failed" to "导入失败",
    "No media selected" to "未选择媒体",
    "ASCII copied" to "ASCII 已复制",
    "Nothing to export" to "没有可导出的内容",
    "Export failed" to "导出失败",
    "TXT exported" to "TXT 已导出",
    "HTML exported" to "HTML 已导出",
    "SVG exported" to "SVG 已导出",
    "Image exported" to "图片已导出",
    "Create a new project or continue your latest work." to "创建新项目或继续最近项目。",
    "New video" to "新建视频",
    "Edit photo" to "编辑照片",
    "Continue project" to "继续项目",
    "No recent projects yet." to "暂无最近项目。",
    "Open" to "打开",
    "Play" to "播放",
    "Pause" to "暂停",
    "Reset" to "重置",
    "Copy" to "复制",
    "Quick Presets" to "快速预设",
    "Preset Gallery" to "预设画廊",
    "Preview example for this preset" to "该预设的预览示例",
    "Apply Preset" to "应用预设",
    "Preset saved" to "预设已保存",
    "Preset loaded" to "预设已加载",
    "Projects imported" to "项目已导入",
    "Pick a global style for the whole app." to "为整个应用选择全局风格。",
    "Interactive touch tail" to "交互式触摸尾迹",
    "Custom Theme Colors" to "自定义主题颜色"
)

private fun looksMojibake(text: String): Boolean {
    if (text.isBlank()) return false
    return text.contains("Р ") ||
        text.contains("Р’") ||
        text.contains("вЂ") ||
        text.contains("Ћ") ||
        text.contains("Ў")
}

private fun tr(lang: AppLanguage, en: String, ru: String, zh: String): String = when (lang) {
    AppLanguage.En -> en
    AppLanguage.Ru -> RU_FALLBACK[en] ?: ru.takeIf { it.isNotBlank() && !looksMojibake(it) } ?: en
    AppLanguage.Zh -> ZH_FALLBACK[en] ?: zh.takeIf { it.isNotBlank() && !looksMojibake(it) } ?: en
}

private fun ClipboardManager.copyAscii(text: String) = setText(AnnotatedString(text))
private fun toast(context: Context, message: String) = Toast.makeText(context, message, Toast.LENGTH_SHORT).show()

private suspend fun loadBitmapSmart(context: Context, uri: Uri, maxSide: Int): Result<LoadedBitmap> = withContext(Dispatchers.IO) {
    runCatching {
        val mime = context.contentResolver.getType(uri).orEmpty().lowercase(Locale.US)
        val isVideo = mime.startsWith("video/")
        val raw = if (isVideo) decodeVideoFrame(context, uri) else decodeImageBitmap(context, uri, maxSide)
        val scaled = scaleBitmap(raw, maxSide)
        LoadedBitmap(scaled, when {
            isVideo -> "video"
            mime.contains("gif") -> "gif"
            else -> "image"
        })
    }
}

private fun readUriBytes(context: Context, uri: Uri): ByteArray? = runCatching {
    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
}.getOrNull()

private fun probeMediaPlaybackInfo(context: Context, uri: Uri, mediaKind: String): MediaPlaybackInfo {
    return when (mediaKind) {
        "video" -> {
            val mmr = MediaMetadataRetriever()
            try {
                mmr.setDataSource(context, uri)
                val dur = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L
                val fpsRaw = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CAPTURE_FRAMERATE)?.toFloatOrNull()
                val fps = (fpsRaw?.roundToInt() ?: 24).coerceIn(6, 60)
                MediaPlaybackInfo(durationMs = dur, fps = fps)
            } catch (_: Throwable) {
                MediaPlaybackInfo(durationMs = 0L, fps = 24)
            } finally {
                runCatching { mmr.release() }
            }
        }
        "gif" -> {
            val bytes = readUriBytes(context, uri)
            if (bytes == null) return MediaPlaybackInfo(durationMs = 3000L, fps = 24)
            val movie = Movie.decodeByteArray(bytes, 0, bytes.size)
            val dur = movie?.duration()?.toLong()?.takeIf { it > 0L } ?: 3000L
            MediaPlaybackInfo(durationMs = dur, fps = 24)
        }
        else -> MediaPlaybackInfo(durationMs = 0L, fps = 24)
    }
}

private fun decodeMediaFrame(
    context: Context,
    uri: Uri,
    mediaKind: String,
    atMs: Long,
    maxSide: Int,
    gifBytes: ByteArray? = null,
    gifMovie: Movie? = null
): Bitmap? {
    return runCatching {
        when (mediaKind) {
            "video" -> {
                VideoFrameCache.getFrame(context, uri, atMs, maxSide)
            }
            "gif" -> {
                val movie = gifMovie ?: run {
                    val bytes = gifBytes ?: readUriBytes(context, uri) ?: return null
                    Movie.decodeByteArray(bytes, 0, bytes.size)
                } ?: return null
                val duration = movie.duration().takeIf { it > 0 } ?: 3000
                val t = (atMs % duration.toLong()).toInt().coerceAtLeast(0)
                movie.setTime(t)
                val w = movie.width().coerceAtLeast(1)
                val h = movie.height().coerceAtLeast(1)
                val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                val canvas = Canvas(bmp)
                movie.draw(canvas, 0f, 0f)
                scaleBitmap(bmp, maxSide)
            }
            else -> decodeImageBitmap(context, uri, maxSide)
        }
    }.getOrNull()
}

private object VideoFrameCache {
    private var activeUri: String? = null
    private var retriever: MediaMetadataRetriever? = null
    private val frameCache = LruCache<Long, Bitmap>(28)

    @Synchronized
    fun getFrame(context: Context, uri: Uri, atMs: Long, maxSide: Int): Bitmap? {
        val key = uri.toString()
        try {
            if (retriever == null || activeUri != key) {
                retriever?.release()
                retriever = MediaMetadataRetriever().apply { setDataSource(context, uri) }
                activeUri = key
                frameCache.evictAll()
            }
            val bucketMs = (atMs.coerceAtLeast(0L) / 16L) * 16L
            val cacheKey = (bucketMs shl 18) xor (maxSide.toLong() shl 4) xor key.hashCode().toLong()
            frameCache.get(cacheKey)?.let { return it }
            val atUs = atMs.coerceAtLeast(0L) * 1000L
            val frame = retriever?.getFrameAtTime(atUs, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                ?: retriever?.getFrameAtTime(atUs, MediaMetadataRetriever.OPTION_CLOSEST)
                ?: retriever?.getFrameAtTime()
            val scaled = frame?.let { scaleBitmap(it, maxSide) }
            if (scaled != null) {
                frameCache.put(cacheKey, scaled)
            }
            return scaled
        } catch (_: Throwable) {
            clear()
            return null
        }
    }

    @Synchronized
    fun clear() {
        runCatching { retriever?.release() }
        retriever = null
        activeUri = null
        frameCache.evictAll()
    }
}

private fun formatMs(ms: Long): String {
    val total = (ms.coerceAtLeast(0L) / 1000L).toInt()
    val m = total / 60
    val s = total % 60
    return String.format(Locale.US, "%02d:%02d", m, s)
}

private fun decodeVideoFrame(context: Context, uri: Uri): Bitmap {
    val mmr = MediaMetadataRetriever()
    return try {
        mmr.setDataSource(context, uri)
        mmr.getFrameAtTime(0L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC) ?: mmr.getFrameAtTime() ?: error("No video frame available")
    } finally {
        runCatching { mmr.release() }
    }
}

private fun decodeImageBitmap(context: Context, uri: Uri, maxSide: Int): Bitmap {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        val source = ImageDecoder.createSource(context.contentResolver, uri)
        return ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
            val srcW = info.size.width.coerceAtLeast(1)
            val srcH = info.size.height.coerceAtLeast(1)
            val largest = max(srcW, srcH)
            if (largest > maxSide) {
                val ratio = maxSide.toFloat() / largest.toFloat()
                decoder.setTargetSize(max(1, (srcW * ratio).roundToInt()), max(1, (srcH * ratio).roundToInt()))
            }
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            decoder.isMutableRequired = false
        }
    }

    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) } ?: error("Cannot open stream")
    val sample = calculateInSampleSize(bounds.outWidth, bounds.outHeight, maxSide)
    val opts = BitmapFactory.Options().apply {
        inSampleSize = sample
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }
    return context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) ?: error("Decode failed") }
        ?: error("Cannot open stream")
}

private fun calculateInSampleSize(srcW: Int, srcH: Int, maxSide: Int): Int {
    if (srcW <= 0 || srcH <= 0) return 1
    var sample = 1
    var w = srcW
    var h = srcH
    while (max(w, h) > maxSide) {
        sample *= 2
        w /= 2
        h /= 2
    }
    return sample.coerceAtLeast(1)
}

private fun queryDisplayName(context: Context, uri: Uri): String? {
    val projection = arrayOf(MediaStore.MediaColumns.DISPLAY_NAME)
    context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
        val col = cursor.getColumnIndex(MediaStore.MediaColumns.DISPLAY_NAME)
        if (col >= 0 && cursor.moveToFirst()) return cursor.getString(col)
    }
    return null
}

private fun loadProjects(context: Context): List<ProjectEntry> {
    return runCatching {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val raw = (prefs.getString(PREFS_PROJECTS_KEY, "[]") ?: "[]").trimStart('\uFEFF')
        val parsed = ProjectV2.parseList(raw)
        parsed.map {
            ProjectEntry(
                id = it.id,
                title = it.title,
                uri = it.sourceUri,
                kind = it.mediaKind,
                durationMs = it.durationMs,
                updatedAt = it.updatedAt
            )
        }
    }.getOrElse { emptyList() }
}

private fun saveProjects(context: Context, entries: List<ProjectEntry>) {
    runCatching {
        val v2 = entries.take(40).map { e ->
            ProjectV2(
                id = e.id,
                title = e.title,
                sourceUri = e.uri,
                mediaKind = e.kind,
                durationMs = e.durationMs,
                updatedAt = e.updatedAt
            )
        }
        val raw = ProjectV2.serializeList(v2)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREFS_PROJECTS_KEY, raw)
            .apply()
    }
}

private fun scaleBitmap(src: Bitmap, maxSide: Int): Bitmap {
    val longest = max(src.width, src.height)
    if (longest <= maxSide) return src
    val ratio = maxSide.toFloat() / longest.toFloat()
    val w = max(1, (src.width * ratio).roundToInt())
    val h = max(1, (src.height * ratio).roundToInt())
    return Bitmap.createScaledBitmap(src, w, h, true)
}

private suspend fun bitmapToAscii(
    bitmap: Bitmap,
    widthChars: Int,
    contrast: Float,
    brightness: Float,
    gamma: Float,
    saturation: Float,
    exposure: Float,
    sharpen: Float,
    vignette: Float,
    bloom: Float,
    denoise: Float,
    edgeBoost: Float,
    posterize: Int,
    scanlines: Boolean,
    scanStrength: Float,
    scanStep: Int,
    dither: Boolean,
    curvature: Float,
    concavity: Float,
    curveCenterX: Float,
    curveExpand: Float,
    curveType: Int,
    grain: Float,
    chroma: Float,
    ribbing: Float,
    clarity: Float,
    motionBlur: Float,
    colorBoost: Float,
    glitch: Float,
    glitchDensity: Float,
    glitchShift: Float,
    glitchRgb: Boolean,
    glitchBlock: Float,
    glitchJitter: Float,
    glitchNoise: Float,
    invert: Boolean,
    charset: String,
    quality: PreviewQuality = PreviewQuality.Normal
): String =
    withContext(Dispatchers.Default) {
        val settings = RenderSettings(
            widthChars = widthChars,
            contrast = contrast,
            brightness = brightness,
            gamma = gamma,
            saturation = saturation,
            exposure = exposure,
            sharpen = sharpen,
            vignette = vignette,
            bloom = bloom,
            denoise = denoise,
            edgeBoost = edgeBoost,
            posterize = posterize,
            scanlines = scanlines,
            scanStrength = scanStrength,
            scanStep = scanStep,
            dither = dither,
            curvature = curvature,
            concavity = concavity,
            curveCenterX = curveCenterX,
            curveExpand = curveExpand,
            curveType = curveType,
            grain = grain,
            chroma = chroma,
            ribbing = ribbing,
            clarity = clarity,
            motionBlur = motionBlur,
            colorBoost = colorBoost,
            glitch = glitch,
            glitchDensity = glitchDensity,
            glitchShift = glitchShift,
            glitchRgb = glitchRgb,
            glitchBlock = glitchBlock,
            glitchJitter = glitchJitter,
            glitchNoise = glitchNoise,
            invert = invert,
            charsetValue = charset
        )
        AsciiRenderEngine.renderSync(
            bitmap = bitmap,
            settings = settings,
            quality = quality
        ) { ensureActive() }.ascii
    }

private fun bitmapToAsciiSync(
    bitmap: Bitmap,
    widthChars: Int,
    contrast: Float,
    brightness: Float,
    gamma: Float,
    saturation: Float,
    exposure: Float = 0f,
    sharpen: Float = 0f,
    vignette: Float = 0f,
    bloom: Float = 0f,
    denoise: Float = 0f,
    edgeBoost: Float = 0f,
    posterize: Int = 0,
    scanlines: Boolean = false,
    scanStrength: Float = 0f,
    scanStep: Int = 3,
    dither: Boolean = false,
    curvature: Float = 0f,
    concavity: Float = 0f,
    curveCenterX: Float = 0f,
    curveExpand: Float = 0f,
    curveType: Int = 0,
    grain: Float = 0f,
    chroma: Float = 0f,
    ribbing: Float = 0f,
    clarity: Float = 0f,
    motionBlur: Float = 0f,
    colorBoost: Float = 0f,
    glitch: Float = 0f,
    glitchDensity: Float = 0.35f,
    glitchShift: Float = 0.42f,
    glitchRgb: Boolean = true,
    glitchBlock: Float = 0.10f,
    glitchJitter: Float = 0.10f,
    glitchNoise: Float = 0.12f,
    invert: Boolean,
    charset: String,
    cancelCheck: (() -> Unit)? = null
): String {
    val map = if (charset.isNotEmpty()) charset else "@%#*+=-:. "
    val charW = widthChars.coerceIn(48, 320)
    val charH = max(1, ((bitmap.height.toFloat() / bitmap.width.toFloat()) * charW * 0.55f).roundToInt())
    val scaled = Bitmap.createScaledBitmap(bitmap, charW, charH, true)
    val pixels = IntArray(charW * charH)
    scaled.getPixels(pixels, 0, charW, 0, 0, charW, charH)

    val gammaSafe = gamma.coerceAtLeast(0.1f)
    val exposureMul = 2f.pow(exposure.coerceIn(-1f, 1f))
    val bloomSafe = bloom.coerceIn(0f, 1f)
    val denoiseSafe = denoise.coerceIn(0f, 1f)
    val edgeSafe = edgeBoost.coerceIn(0f, 1f)
    val posterLevels = posterize.coerceIn(0, 10)
    val scanSafe = scanStrength.coerceIn(0f, 1f)
    val scanStepSafe = scanStep.coerceIn(1, 8)
    val curvSafe = curvature.coerceIn(-1f, 1f)
    val concSafe = concavity.coerceIn(-1f, 1f)
    val centerShift = curveCenterX.coerceIn(-1f, 1f)
    val expandSafe = curveExpand.coerceIn(-1f, 1f)
    val curveMode = curveType.coerceIn(0, 2)
    val sharpenSafe = sharpen.coerceIn(0f, 1f)
    val vignetteSafe = vignette.coerceIn(0f, 1f)
    val grainSafe = grain.coerceIn(0f, 1f)
    val chromaSafe = chroma.coerceIn(0f, 1f)
    val ribbingSafe = ribbing.coerceIn(0f, 1f)
    val claritySafe = clarity.coerceIn(0f, 1f)
    val motionBlurSafe = motionBlur.coerceIn(0f, 1f)
    val colorBoostSafe = colorBoost.coerceIn(0f, 1f)
    val glitchSafe = glitch.coerceIn(0f, 1f)
    val glitchDensitySafe = glitchDensity.coerceIn(0f, 1f)
    val glitchShiftSafe = glitchShift.coerceIn(0f, 1f)
    val glitchBlockSafe = glitchBlock.coerceIn(0f, 1f)
    val glitchJitterSafe = glitchJitter.coerceIn(0f, 1f)
    val glitchNoiseSafe = glitchNoise.coerceIn(0f, 1f)

    val lumBase = FloatArray(charW * charH)
    for (y in 0 until charH) {
        val row = y * charW
        for (x in 0 until charW) {
            val c = pixels[row + x]
            val r = ((c shr 16) and 0xFF) / 255f
            val g = ((c shr 8) and 0xFF) / 255f
            val b = (c and 0xFF) / 255f
            val gray = (0.299f * r + 0.587f * g + 0.114f * b)
            val satMul = (saturation + colorBoostSafe * 0.85f).coerceIn(0f, 3f)
            val rs = (gray + (r - gray) * satMul).coerceIn(0f, 1f)
            val gs = (gray + (g - gray) * satMul).coerceIn(0f, 1f)
            val bs = (gray + (b - gray) * satMul).coerceIn(0f, 1f)
            val chromaMix = chromaSafe * 0.35f
            val lum = (0.2126f * rs + 0.7152f * gs + 0.0722f * bs)
            val colorEdge = kotlin.math.abs(rs - bs) * 0.55f + kotlin.math.abs(gs - rs) * 0.25f
            lumBase[row + x] = (lum + colorEdge * chromaMix).coerceIn(0f, 1f)
        }
    }

    val lumDenoised = if (denoiseSafe <= 0.001f) {
        lumBase
    } else {
        val out = FloatArray(lumBase.size)
        for (y in 0 until charH) {
            val row = y * charW
            for (x in 0 until charW) {
                val i = row + x
                val c = lumBase[i]
                val left = lumBase[row + (x - 1).coerceAtLeast(0)]
                val right = lumBase[row + (x + 1).coerceAtMost(charW - 1)]
                val up = lumBase[(y - 1).coerceAtLeast(0) * charW + x]
                val down = lumBase[(y + 1).coerceAtMost(charH - 1) * charW + x]
                val blur = (left + right + up + down + c) / 5f
                out[i] = (c * (1f - denoiseSafe) + blur * denoiseSafe).coerceIn(0f, 1f)
            }
        }
        out
    }

    val lumReady = if (sharpenSafe <= 0.001f) {
        lumDenoised
    } else {
        val out = FloatArray(lumBase.size)
        for (y in 0 until charH) {
            val row = y * charW
            for (x in 0 until charW) {
                val i = row + x
                val c = lumDenoised[i]
                val left = lumDenoised[row + (x - 1).coerceAtLeast(0)]
                val right = lumDenoised[row + (x + 1).coerceAtMost(charW - 1)]
                val up = lumDenoised[(y - 1).coerceAtLeast(0) * charW + x]
                val down = lumDenoised[(y + 1).coerceAtMost(charH - 1) * charW + x]
                val blur = (left + right + up + down + c) / 5f
                out[i] = (c + (c - blur) * (sharpenSafe * 1.8f)).coerceIn(0f, 1f)
            }
        }
        out
    }

    val lumMotion = if (motionBlurSafe <= 0.001f) {
        lumReady
    } else {
        val out = FloatArray(lumReady.size)
        val radius = (1 + (motionBlurSafe * 5f).roundToInt()).coerceIn(1, 6)
        for (y in 0 until charH) {
            val row = y * charW
            for (x in 0 until charW) {
                var sum = 0f
                var count = 0
                var k = -radius
                while (k <= radius) {
                    val sx = (x + k).coerceIn(0, charW - 1)
                    sum += lumReady[row + sx]
                    count++
                    k++
                }
                val blur = sum / count.coerceAtLeast(1)
                val base = lumReady[row + x]
                out[row + x] = (base * (1f - motionBlurSafe) + blur * motionBlurSafe).coerceIn(0f, 1f)
            }
        }
        out
    }

    val cx = (charW - 1) * 0.5f
    val cxWarp = cx + centerShift * cx * 0.35f
    val cy = (charH - 1) * 0.5f
    val maxDist = kotlin.math.sqrt((cx * cx + cy * cy).coerceAtLeast(1f))
    val bayer4 = intArrayOf(0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
    val tick = ((System.currentTimeMillis() / 33L) and 0xFFFF).toInt()
    fun hash01(x: Int, y: Int, seed: Int): Float {
        var n = x * 374761393 + y * 668265263 + seed * 1274126177
        n = (n xor (n shr 13)) * 1274126177
        n = n xor (n shr 16)
        return ((n and 0x7fffffff) / 2147483647f).coerceIn(0f, 1f)
    }
    val rowShift = IntArray(charH) { y ->
        if (glitchSafe <= 0.001f) 0 else {
            val active = hash01(y, tick, 1) < (glitchDensitySafe * glitchSafe)
            if (!active) 0 else {
                val dir = if (hash01(y, tick, 2) > 0.5f) 1 else -1
                val amt = ((charW * (0.02f + glitchShiftSafe * 0.25f) * glitchSafe)).roundToInt()
                dir * amt
            }
        }
    }
    val blockStride = (2 + (glitchBlockSafe * 14f).roundToInt()).coerceIn(2, 18)
    val sb = StringBuilder((charW + 1) * charH)
    for (y in 0 until charH) {
        cancelCheck?.invoke()
        val row = y * charW
        for (x in 0 until charW) {
            val nx = ((x - cxWarp) / cx.coerceAtLeast(1f))
            val ny = ((y - cy) / cy.coerceAtLeast(1f))
            val r2 = nx * nx + ny * ny
            val k = curvSafe * 0.45f + concSafe * 0.35f
            val warp = when (curveMode) {
                1 -> 1f + k * r2
                2 -> 1f - k * r2
                else -> 1f + k * r2 * 0.5f
            }
            val sx = (cxWarp + nx * cx * warp + expandSafe * cx * 0.15f).roundToInt().coerceIn(0, charW - 1)
            val sy = (cy + ny * cy * warp).roundToInt().coerceIn(0, charH - 1)
            var sx2 = (sx + rowShift[sy]).coerceIn(0, charW - 1)
            if (glitchSafe > 0.001f && ((x / blockStride + y / blockStride) % 7 == 0) && hash01(x, y, tick) < (glitchSafe * 0.22f)) {
                val j = ((hash01(x + tick, y, 4) - 0.5f) * glitchJitterSafe * charW * 0.12f).roundToInt()
                sx2 = (sx2 + j).coerceIn(0, charW - 1)
            }
            var lum = lumMotion[sy * charW + sx2]

            if (edgeSafe > 0.001f) {
                val xl = (sx2 - 1).coerceAtLeast(0)
                val xr = (sx2 + 1).coerceAtMost(charW - 1)
                val yu = (sy - 1).coerceAtLeast(0)
                val yd = (sy + 1).coerceAtMost(charH - 1)
                val gx = lumMotion[sy * charW + xr] - lumMotion[sy * charW + xl]
                val gy = lumMotion[yd * charW + sx2] - lumMotion[yu * charW + sx2]
                val edge = kotlin.math.sqrt(gx * gx + gy * gy)
                lum = (lum + edge * edgeSafe * 0.6f).coerceIn(0f, 1f)
            }

            lum = (lum * exposureMul).coerceIn(0f, 1f)
            lum = ((lum - 0.5f) * contrast + 0.5f + brightness).coerceIn(0f, 1f)
            if (bloomSafe > 0.001f && lum > 0.72f) {
                lum = (lum + (lum - 0.72f) * bloomSafe * 0.9f).coerceIn(0f, 1f)
            }
            lum = lum.pow(1f / gammaSafe).coerceIn(0f, 1f)
            if (posterLevels > 1) {
                lum = (kotlin.math.round(lum * posterLevels) / posterLevels).coerceIn(0f, 1f)
            }
            if (claritySafe > 0.001f) {
                lum = (((lum - 0.5f) * (1f + claritySafe * 1.1f)) + 0.5f).coerceIn(0f, 1f)
            }
            if (vignetteSafe > 0.001f) {
                val dx = x - cx
                val dy = y - cy
                val d = kotlin.math.sqrt(dx * dx + dy * dy) / maxDist
                val factor = 1f - vignetteSafe * d.pow(1.6f)
                lum = (lum * factor).coerceIn(0f, 1f)
            }
            if (ribbingSafe > 0.001f) {
                val rib = 0.5f + 0.5f * sin((x * 0.19f) + (y * 0.04f))
                lum = (lum * (1f - ribbingSafe * 0.14f) + rib * ribbingSafe * 0.14f).coerceIn(0f, 1f)
            }
            if (scanlines && (y % scanStepSafe == 0)) {
                lum = (lum * (1f - scanSafe * 0.8f)).coerceIn(0f, 1f)
            }
            if (dither) {
                val bv = bayer4[(y % 4) * 4 + (x % 4)] / 16f
                val shift = (bv - 0.5f) * 0.18f
                lum = (lum + shift).coerceIn(0f, 1f)
            }
            if (grainSafe > 0.001f) {
                val n = (hash01(x + tick, y, 9) - 0.5f) * 0.22f * grainSafe
                lum = (lum + n).coerceIn(0f, 1f)
            }
            if (glitchSafe > 0.001f) {
                val gn = (hash01(x, y + tick, 11) - 0.5f) * glitchNoiseSafe * glitchSafe * 0.35f
                lum = (lum + gn).coerceIn(0f, 1f)
                if (glitchRgb && hash01(x, y, 12) < glitchSafe * 0.06f) {
                    lum = (lum + (if ((x + y) % 2 == 0) 0.08f else -0.08f) * glitchSafe).coerceIn(0f, 1f)
                }
            }
            if (invert) lum = 1f - lum
            val idx = (lum * (map.length - 1)).roundToInt().coerceIn(0, map.length - 1)
            sb.append(map[idx])
        }
        sb.append('\n')
    }
    return sb.toString()
}

private fun applyWatermark(ascii: String, widthChars: Int, text: String): String {
    val watermark = text.trim().take(widthChars.coerceAtLeast(1))
    if (watermark.isEmpty() || ascii.isBlank()) return ascii
    val lines = ascii.trimEnd('\n').lines().toMutableList()
    if (lines.isEmpty()) return ascii
    val i = lines.lastIndex
    val line = lines[i]
    val start = (line.length - watermark.length).coerceAtLeast(0)
    val out = StringBuilder(line)
    for (k in watermark.indices) {
        val at = start + k
        if (at < out.length) out.setCharAt(at, watermark[k]) else out.append(watermark[k])
    }
    lines[i] = out.toString()
    return lines.joinToString("\n") + "\n"
}

private fun buildQuickPresetPreviewAscii(item: QuickPresetItem, bitmap: Bitmap): String {
    val charset = CHARSETS[item.charset] ?: CHARSETS.getValue("Classic")
    return when (item.style) {
        "cyber" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1.26f, brightness = -0.01f, gamma = 1.02f,
            saturation = 1.22f, exposure = 0.06f, sharpen = 0.20f, vignette = 0.18f, bloom = 0.20f,
            denoise = 0.05f, edgeBoost = 0.22f, posterize = 2, scanlines = true, scanStrength = 0.30f,
            scanStep = 3, dither = true, curvature = 0.12f, concavity = 0.08f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 0, grain = 0.08f, chroma = 0.22f, ribbing = 0.08f, clarity = 0.20f, motionBlur = 0.04f,
            colorBoost = 0.30f, glitch = 0.18f, glitchDensity = 0.36f, glitchShift = 0.42f, glitchRgb = true,
            glitchBlock = 0.12f, glitchJitter = 0.12f, glitchNoise = 0.20f, invert = false, charset = charset
        )
        "retro" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1.12f, brightness = 0.04f, gamma = 0.94f,
            saturation = 1.08f, exposure = 0.03f, sharpen = 0.14f, vignette = 0.24f, bloom = 0.08f,
            denoise = 0.03f, edgeBoost = 0.10f, posterize = 3, scanlines = true, scanStrength = 0.34f,
            scanStep = 3, dither = true, curvature = 0.24f, concavity = 0.12f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 1, grain = 0.14f, chroma = 0.16f, ribbing = 0.20f, clarity = 0.08f, motionBlur = 0.06f,
            colorBoost = 0.12f, glitch = 0.10f, glitchDensity = 0.28f, glitchShift = 0.30f, glitchRgb = true,
            glitchBlock = 0.10f, glitchJitter = 0.08f, glitchNoise = 0.16f, invert = false, charset = charset
        )
        "cinematic" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1.30f, brightness = -0.03f, gamma = 0.96f,
            saturation = 1.12f, exposure = 0.04f, sharpen = 0.22f, vignette = 0.22f, bloom = 0.16f,
            denoise = 0.05f, edgeBoost = 0.14f, posterize = 1, scanlines = false, scanStrength = 0f,
            scanStep = 3, dither = false, curvature = 0f, concavity = 0f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 0, grain = 0.10f, chroma = 0.06f, ribbing = 0.04f, clarity = 0.16f, motionBlur = 0.02f,
            colorBoost = 0.18f, glitch = 0f, glitchDensity = 0.20f, glitchShift = 0.20f, glitchRgb = true,
            glitchBlock = 0.08f, glitchJitter = 0.05f, glitchNoise = 0.06f, invert = false, charset = charset
        )
        "vhs" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1.06f, brightness = 0.02f, gamma = 0.90f,
            saturation = 1.06f, exposure = 0.02f, sharpen = 0.10f, vignette = 0.18f, bloom = 0.10f,
            denoise = 0.08f, edgeBoost = 0.06f, posterize = 2, scanlines = true, scanStrength = 0.42f,
            scanStep = 2, dither = true, curvature = 0.14f, concavity = 0.10f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 1, grain = 0.24f, chroma = 0.30f, ribbing = 0.24f, clarity = 0.06f, motionBlur = 0.20f,
            colorBoost = 0.12f, glitch = 0.28f, glitchDensity = 0.48f, glitchShift = 0.50f, glitchRgb = true,
            glitchBlock = 0.14f, glitchJitter = 0.18f, glitchNoise = 0.32f, invert = false, charset = charset
        )
        "soft" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1.04f, brightness = 0.01f, gamma = 1f,
            saturation = 1.14f, exposure = 0.02f, sharpen = 0.08f, vignette = 0.10f, bloom = 0.12f,
            denoise = 0.10f, edgeBoost = 0.05f, posterize = 0, scanlines = false, scanStrength = 0f,
            scanStep = 3, dither = false, curvature = 0f, concavity = 0f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 0, grain = 0.08f, chroma = 0.08f, ribbing = 0.02f, clarity = 0.08f, motionBlur = 0.02f,
            colorBoost = 0.14f, glitch = 0f, glitchDensity = 0.20f, glitchShift = 0.20f, glitchRgb = true,
            glitchBlock = 0.08f, glitchJitter = 0.05f, glitchNoise = 0.08f, invert = false, charset = charset
        )
        "clean" -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1f, brightness = 0f, gamma = 1f,
            saturation = 1f, exposure = 0f, sharpen = 0.12f, vignette = 0f, bloom = 0f,
            denoise = 0.10f, edgeBoost = 0.10f, posterize = 0, scanlines = false, scanStrength = 0f,
            scanStep = 3, dither = false, curvature = 0f, concavity = 0f, curveCenterX = 0f, curveExpand = 0f,
            curveType = 0, grain = 0f, chroma = 0f, ribbing = 0f, clarity = 0.12f, motionBlur = 0f,
            colorBoost = 0.05f, glitch = 0f, glitchDensity = 0.20f, glitchShift = 0.20f, glitchRgb = true,
            glitchBlock = 0.08f, glitchJitter = 0.05f, glitchNoise = 0.08f, invert = false, charset = charset
        )
        else -> bitmapToAsciiSync(
            bitmap = bitmap, widthChars = item.width, contrast = 1f, brightness = 0f, gamma = 1f,
            saturation = 1f, invert = false, charset = charset
        )
    }
}

private fun saveAsciiText(context: Context, fileName: String, text: String): Result<String> {
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + File.separator + "ASCIIStudio")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: error("MediaStore insert failed")
            context.contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(text) } ?: error("Cannot open output stream")
            uri.toString()
        } else {
            val dir = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "ASCIIStudio")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            file.writeText(text)
            file.absolutePath
        }
    }
}

private fun savePresetFile(context: Context, fileName: String, payload: String): Result<String> {
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, "application/json")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + File.separator + "ASCIIStudio")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("MediaStore insert failed")
            context.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { writer ->
                writer.write(payload)
            } ?: error("Cannot open output stream")
            uri.toString()
        } else {
            val dir = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "ASCIIStudio")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            file.writeText(payload, Charsets.UTF_8)
            file.absolutePath
        }
    }
}

private fun readUtf8FromUri(context: Context, uri: Uri): String? = runCatching {
    context.contentResolver.openInputStream(uri)?.use { stream ->
        stream.bufferedReader(Charsets.UTF_8).use { it.readText().trimStart('\uFEFF') }
    }
}.getOrNull()

private fun saveAsciiHtml(context: Context, fileName: String, ascii: String): Result<String> {
    val escaped = ascii
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    val html = """
        <!doctype html>
        <html>
        <head><meta charset="utf-8"><title>ASCII Studio Export</title></head>
        <body style="background:#0b1018;color:#e8f2ff;font-family:Consolas,Menlo,monospace;white-space:pre;line-height:1.08;">
        $escaped
        </body>
        </html>
    """.trimIndent()
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, "text/html")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + File.separator + "ASCIIStudio")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("MediaStore insert failed")
            context.contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { writer ->
                writer.write(html)
            } ?: error("Cannot open output stream")
            uri.toString()
        } else {
            val dir = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "ASCIIStudio")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            file.writeText(html)
            file.absolutePath
        }
    }
}

private fun saveAsciiSvg(
    context: Context,
    fileName: String,
    ascii: String,
    settings: RenderSettings
): Result<String> {
    val svg = AsciiRenderEngine.exportSvg(ascii, settings)
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, "image/svg+xml")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + File.separator + "ASCIIStudio")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("MediaStore insert failed")
            context.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { writer ->
                writer.write(svg)
            } ?: error("Cannot open output stream")
            uri.toString()
        } else {
            val dir = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "ASCIIStudio")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            file.writeText(svg, Charsets.UTF_8)
            file.absolutePath
        }
    }
}

private fun saveAsciiRaster(
    context: Context,
    fileName: String,
    ascii: String,
    fontSizeSp: Float,
    fgArgb: Int,
    bgArgb: Int,
    format: String,
    renderBitmap: Bitmap? = null,
    targetWidth: Int? = null,
    targetHeight: Int? = null
): Result<String> {
    return runCatching {
        val raw = renderBitmap ?: AsciiRenderEngine.rasterizeAsciiToBitmap(
            context = context,
            ascii = ascii,
            fontSizeSp = fontSizeSp,
            fgArgb = fgArgb,
            bgArgb = bgArgb
        )
        val bmp = if (targetWidth != null && targetHeight != null) {
            val tw = targetWidth.coerceAtLeast(64)
            val th = targetHeight.coerceAtLeast(64)
            if (raw.width == tw && raw.height == th) raw else Bitmap.createScaledBitmap(raw, tw, th, true)
        } else {
            raw
        }
        val fmt = format.lowercase(Locale.US)
        val mime = when (fmt) {
            "jpg", "jpeg" -> "image/jpeg"
            "webp" -> "image/webp"
            else -> "image/png"
        }
        val compress = when (fmt) {
            "jpg", "jpeg" -> Bitmap.CompressFormat.JPEG
            "webp" -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Bitmap.CompressFormat.WEBP_LOSSY
                else Bitmap.CompressFormat.WEBP
            }
            else -> Bitmap.CompressFormat.PNG
        }
        val quality = if (compress == Bitmap.CompressFormat.PNG) 100 else 95

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + File.separator + "ASCIIStudio")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("MediaStore insert failed")
            context.contentResolver.openOutputStream(uri)?.use { out ->
                if (!bmp.compress(compress, quality, out)) error("Compress failed")
            } ?: error("Cannot open output stream")
            uri.toString()
        } else {
            val dir = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "ASCIIStudio")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            file.outputStream().use { out ->
                if (!bmp.compress(compress, quality, out)) error("Compress failed")
            }
            file.absolutePath
        }
    }
}

private fun rasterizeAsciiToBitmap(
    context: Context,
    ascii: String,
    fontSizeSp: Float,
    fgArgb: Int,
    bgArgb: Int,
    targetWidth: Int? = null,
    targetHeight: Int? = null
): Bitmap {
    val lines = ascii.trimEnd('\n').lines().ifEmpty { listOf("") }
    val density = context.resources.displayMetrics.scaledDensity
    val textSizePx = (fontSizeSp.coerceIn(6f, 36f) * density).coerceAtLeast(8f)
    val pad = 24

    val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = fgArgb
        textSize = textSizePx
        typeface = Typeface.MONOSPACE
        isDither = true
    }
    val fm = paint.fontMetrics
    val lineH = (fm.descent - fm.ascent).coerceAtLeast(1f)
    val maxW = lines.maxOf { ln -> kotlin.math.ceil(paint.measureText(ln).toDouble()).toInt() }.coerceAtLeast(1)
    val outW = (maxW + pad * 2).coerceAtLeast(64)
    val outH = (kotlin.math.ceil(lineH * lines.size).toInt() + pad * 2).coerceAtLeast(64)
    val bmp = Bitmap.createBitmap(outW, outH, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bmp)
    canvas.drawColor(bgArgb)
    var y = pad - fm.ascent
    lines.forEach { line ->
        canvas.drawText(line, pad.toFloat(), y, paint)
        y += lineH
    }
    val tw = targetWidth?.coerceAtLeast(64)
    val th = targetHeight?.coerceAtLeast(64)
    if (tw == null || th == null) return bmp
    if (tw == outW && th == outH) return bmp

    val out = Bitmap.createBitmap(tw, th, Bitmap.Config.ARGB_8888)
    val outCanvas = Canvas(out)
    outCanvas.drawColor(bgArgb)
    val scale = min(tw / outW.toFloat(), th / outH.toFloat())
    val drawW = (outW * scale).roundToInt().coerceAtLeast(1)
    val drawH = (outH * scale).roundToInt().coerceAtLeast(1)
    val left = ((tw - drawW) / 2f)
    val top = ((th - drawH) / 2f)
    outCanvas.drawBitmap(bmp, null, android.graphics.RectF(left, top, left + drawW, top + drawH), null)
    return out
}

private fun generatePresetSampleBitmap(context: Context, w: Int, h: Int): Bitmap {
    val resId = context.resources.getIdentifier("preset_sample", "drawable", context.packageName)
    if (resId != 0) {
        val fromRes = runCatching {
            BitmapFactory.decodeResource(context.resources, resId)
        }.getOrNull()
        if (fromRes != null) {
            return Bitmap.createScaledBitmap(fromRes, w.coerceAtLeast(64), h.coerceAtLeast(64), true)
        }
    }
    val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    val pixels = IntArray(w * h)
    val cx = w * 0.56f
    val cy = h * 0.47f
    val r = (minOf(w, h) * 0.33f)
    for (y in 0 until h) {
        val fy = y.toFloat() / (h - 1).coerceAtLeast(1)
        for (x in 0 until w) {
            val fx = x.toFloat() / (w - 1).coerceAtLeast(1)
            val dx = x - cx
            val dy = y - cy
            val dist = kotlin.math.sqrt(dx * dx + dy * dy) / r
            val vignette = (1f - (dist - 0.1f).coerceIn(0f, 1f)).coerceIn(0f, 1f)
            val red = (20 + 165 * fx + 30 * vignette).roundToInt().coerceIn(0, 255)
            val green = (28 + 120 * (1f - fy) + 25 * vignette).roundToInt().coerceIn(0, 255)
            val blue = (42 + 190 * vignette).roundToInt().coerceIn(0, 255)
            pixels[y * w + x] = (0xFF shl 24) or (red shl 16) or (green shl 8) or blue
        }
    }
    bmp.setPixels(pixels, 0, w, 0, 0, w, h)
    return bmp
}

private fun mixColor(a: Color, b: Color, t: Float): Color {
    val k = t.coerceIn(0f, 1f)
    return Color(
        red = a.red + (b.red - a.red) * k,
        green = a.green + (b.green - a.green) * k,
        blue = a.blue + (b.blue - a.blue) * k,
        alpha = a.alpha + (b.alpha - a.alpha) * k
    )
}



