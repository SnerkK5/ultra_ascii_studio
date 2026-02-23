package com.asciistudio.mobile.core.render

import android.graphics.Bitmap
import android.graphics.Color
import com.asciistudio.mobile.core.model.PreviewQuality
import com.asciistudio.mobile.core.model.RenderSettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AsciiRenderEngineDeterminismTest {
    @Test
    fun renderSyncDeterministicForFixedInput() {
        val bmp = Bitmap.createBitmap(32, 32, Bitmap.Config.ARGB_8888)
        for (y in 0 until 32) {
            for (x in 0 until 32) {
                val v = ((x + y) * 4).coerceIn(0, 255)
                bmp.setPixel(x, y, Color.rgb(v, v, v))
            }
        }
        val settings = RenderSettings(widthChars = 80, charAspectRatio = 0.55f, contrast = 1.1f)
        val one = AsciiRenderEngine.renderSync(bmp, settings, PreviewQuality.Normal)
        val two = AsciiRenderEngine.renderSync(bmp, settings, PreviewQuality.Normal)

        assertEquals(one.ascii, two.ascii)
        assertEquals(one.meta.settingsHash, two.meta.settingsHash)
        assertTrue(one.raster.width > 0)
        assertTrue(one.raster.height > 0)
    }
}
