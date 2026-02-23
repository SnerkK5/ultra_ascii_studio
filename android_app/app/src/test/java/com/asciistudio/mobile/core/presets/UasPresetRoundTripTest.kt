package com.asciistudio.mobile.core.presets

import com.asciistudio.mobile.core.model.RenderSettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class UasPresetRoundTripTest {
    @Test
    fun presetJsonRoundTripKeepsCriticalFields() {
        val settings = RenderSettings(
            widthChars = 188,
            charAspectRatio = 0.62f,
            contrast = 1.25f,
            brightness = -0.1f,
            charsetKey = "Dense",
            charsetValue = "@#WMBRXVYIti+=:,. ",
            watermarkEnabled = true,
            watermarkText = "SNERK503",
            renderFps = 30,
            renderCodec = "libx264",
            renderBitrate = "4M",
            exportFormat = "SVG"
        )
        val p = UasPreset(name = "test", description = "rt", settings = settings)
        val json = p.toJsonString()
        assertTrue(json.contains("\"name\": \"test\""))
        val decoded = UasPreset.fromJsonString(json)
        assertEquals(settings.widthChars, decoded.settings.widthChars)
        assertEquals(settings.charAspectRatio, decoded.settings.charAspectRatio)
        assertEquals(settings.charsetKey, decoded.settings.charsetKey)
        assertEquals(settings.exportFormat, decoded.settings.exportFormat)
    }

    @Test
    fun presetParserHandlesBom() {
        val raw = "\uFEFF{\"version\":1,\"name\":\"BOM\",\"description\":\"ok\",\"settings\":{\"widthChars\":100}}"
        val parsed = UasPreset.fromJsonString(raw)
        assertEquals("BOM", parsed.name)
        assertEquals(100, parsed.settings.widthChars)
    }
}
