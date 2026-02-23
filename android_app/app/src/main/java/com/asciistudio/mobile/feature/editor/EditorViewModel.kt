package com.asciistudio.mobile.feature.editor

import android.graphics.Bitmap
import android.util.LruCache
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.asciistudio.mobile.core.model.PreviewQuality
import com.asciistudio.mobile.core.model.RenderSettings
import com.asciistudio.mobile.core.render.AsciiRenderEngine
import com.asciistudio.mobile.core.render.RenderOutput
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class RenderRequest(
    val bitmap: Bitmap,
    val settings: RenderSettings,
    val quality: PreviewQuality
)

class EditorViewModel : ViewModel() {
    private val requestFlow = MutableStateFlow<RenderRequest?>(null)
    private val _renderOutput = MutableStateFlow<RenderOutput?>(null)
    private val _isRendering = MutableStateFlow(false)
    private val renderCache = LruCache<Int, RenderOutput>(24)

    val renderOutput: StateFlow<RenderOutput?> = _renderOutput.asStateFlow()
    val isRendering: StateFlow<Boolean> = _isRendering.asStateFlow()

    init {
        viewModelScope.launch {
            requestFlow
                .filterNotNull()
                .debounce(66)
                .mapLatest { req ->
                    val cacheKey = buildCacheKey(req)
                    renderCache.get(cacheKey)?.let { return@mapLatest it }
                    _isRendering.update { true }
                    try {
                        withContext(Dispatchers.Default) {
                            AsciiRenderEngine.renderSync(
                                bitmap = req.bitmap,
                                settings = req.settings,
                                quality = req.quality
                            )
                        }.also { rendered ->
                            renderCache.put(cacheKey, rendered)
                        }
                    } finally {
                        _isRendering.update { false }
                    }
                }
                .collect { out ->
                    _renderOutput.update { out }
                }
        }
    }

    fun submitRender(bitmap: Bitmap, settings: RenderSettings, quality: PreviewQuality) {
        requestFlow.update {
            RenderRequest(
                bitmap = bitmap,
                settings = settings,
                quality = quality
            )
        }
    }

    private fun buildCacheKey(req: RenderRequest): Int {
        return listOf(
            req.bitmap.width,
            req.bitmap.height,
            req.bitmap.hashCode(),
            req.quality.id,
            req.settings.hashCode()
        ).joinToString("|").hashCode()
    }
}
