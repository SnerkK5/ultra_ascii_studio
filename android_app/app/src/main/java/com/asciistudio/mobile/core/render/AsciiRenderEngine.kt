package com.asciistudio.mobile.core.render

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import com.asciistudio.mobile.core.model.PreviewQuality
import com.asciistudio.mobile.core.model.RenderSettings
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

data class RenderMeta(
    val widthChars: Int,
    val heightChars: Int,
    val quality: PreviewQuality,
    val charAspectRatio: Float,
    val settingsHash: Int
)

data class RenderOutput(
    val ascii: String,
    val raster: Bitmap,
    val meta: RenderMeta
)

object AsciiRenderEngine {
    fun renderSync(
        bitmap: Bitmap,
        settings: RenderSettings,
        quality: PreviewQuality = PreviewQuality.Normal,
        cancelCheck: (() -> Unit)? = null
    ): RenderOutput {
        val effectiveWidth = (settings.widthChars.toFloat() * quality.widthScale).roundToInt().coerceIn(48, 420)
        val map = if (settings.charsetValue.isNotBlank()) settings.charsetValue else "@%#*+=-:. "
        val charW = effectiveWidth
        val aspect = settings.charAspectRatio.coerceIn(0.3f, 1.2f)
        val charH = max(1, ((bitmap.height.toFloat() / bitmap.width.toFloat()) * charW * aspect).roundToInt())
        val scaled = Bitmap.createScaledBitmap(bitmap, charW, charH, true)
        val pixels = IntArray(charW * charH)
        scaled.getPixels(pixels, 0, charW, 0, 0, charW, charH)

        val gammaSafe = settings.gamma.coerceAtLeast(0.1f)
        val exposureMul = 2f.pow(settings.exposure.coerceIn(-1f, 1f))
        val bloomSafe = settings.bloom.coerceIn(0f, 1f)
        val denoiseSafe = settings.denoise.coerceIn(0f, 1f)
        val edgeSafe = settings.edgeBoost.coerceIn(0f, 1f)
        val posterLevels = settings.posterize.coerceIn(0, 10)
        val scanSafe = settings.scanStrength.coerceIn(0f, 1f)
        val scanStepSafe = settings.scanStep.coerceIn(1, 8)
        val curvSafe = settings.curvature.coerceIn(-1f, 1f)
        val concSafe = settings.concavity.coerceIn(-1f, 1f)
        val centerShift = settings.curveCenterX.coerceIn(-1f, 1f)
        val expandSafe = settings.curveExpand.coerceIn(-1f, 1f)
        val curveMode = settings.curveType.coerceIn(0, 2)
        val sharpenSafe = settings.sharpen.coerceIn(0f, 1f)
        val vignetteSafe = settings.vignette.coerceIn(0f, 1f)
        val grainSafe = settings.grain.coerceIn(0f, 1f)
        val chromaSafe = settings.chroma.coerceIn(0f, 1f)
        val ribbingSafe = settings.ribbing.coerceIn(0f, 1f)
        val claritySafe = settings.clarity.coerceIn(0f, 1f)
        val motionBlurSafe = settings.motionBlur.coerceIn(0f, 1f)
        val colorBoostSafe = settings.colorBoost.coerceIn(0f, 1f)
        val glitchSafe = settings.glitch.coerceIn(0f, 1f)
        val glitchDensitySafe = settings.glitchDensity.coerceIn(0f, 1f)
        val glitchShiftSafe = settings.glitchShift.coerceIn(0f, 1f)
        val glitchBlockSafe = settings.glitchBlock.coerceIn(0f, 1f)
        val glitchJitterSafe = settings.glitchJitter.coerceIn(0f, 1f)
        val glitchNoiseSafe = settings.glitchNoise.coerceIn(0f, 1f)

        val lumBase = FloatArray(charW * charH)
        for (y in 0 until charH) {
            val row = y * charW
            for (x in 0 until charW) {
                val c = pixels[row + x]
                val r = ((c shr 16) and 0xFF) / 255f
                val g = ((c shr 8) and 0xFF) / 255f
                val b = (c and 0xFF) / 255f
                val gray = 0.299f * r + 0.587f * g + 0.114f * b
                val satMul = (settings.saturation + colorBoostSafe * 0.85f).coerceIn(0f, 3f)
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
        val maxDist = sqrt((cx * cx + cy * cy).coerceAtLeast(1f))
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
                    val amt = (charW * (0.02f + glitchShiftSafe * 0.25f) * glitchSafe).roundToInt()
                    dir * amt
                }
            }
        }
        val blockStride = (2 + (glitchBlockSafe * 14f).roundToInt()).coerceIn(2, 18)
        val sb = StringBuilder((charW + 1) * charH)
        val lumFinal = FloatArray(charW * charH)
        val argbFinal = IntArray(charW * charH)

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

                var lumAscii = lumMotion[sy * charW + sx2]
                if (edgeSafe > 0.001f) {
                    val xl = (sx2 - 1).coerceAtLeast(0)
                    val xr = (sx2 + 1).coerceAtMost(charW - 1)
                    val yu = (sy - 1).coerceAtLeast(0)
                    val yd = (sy + 1).coerceAtMost(charH - 1)
                    val gx = lumMotion[sy * charW + xr] - lumMotion[sy * charW + xl]
                    val gy = lumMotion[yd * charW + sx2] - lumMotion[yu * charW + sx2]
                    val edge = sqrt(gx * gx + gy * gy)
                    lumAscii = (lumAscii + edge * edgeSafe * 0.6f).coerceIn(0f, 1f)
                }

                // Stage 1: source -> ASCII symbol mapping.
                lumAscii = (lumAscii * exposureMul).coerceIn(0f, 1f)
                lumAscii = ((lumAscii - 0.5f) * settings.contrast + 0.5f + settings.brightness).coerceIn(0f, 1f)
                lumAscii = lumAscii.pow(1f / gammaSafe).coerceIn(0f, 1f)
                if (posterLevels > 1) {
                    lumAscii = (kotlin.math.round(lumAscii * posterLevels) / posterLevels).coerceIn(0f, 1f)
                }
                if (settings.invert) lumAscii = 1f - lumAscii
                val idx = (lumAscii * (map.length - 1)).roundToInt().coerceIn(0, map.length - 1)
                sb.append(map[idx])

                // Stage 2: apply visual FX after ASCII conversion for raster preview/export.
                var lum = idx.toFloat() / (map.length - 1).coerceAtLeast(1)
                if (claritySafe > 0.001f) {
                    lum = (((lum - 0.5f) * (1f + claritySafe * 1.1f)) + 0.5f).coerceIn(0f, 1f)
                }
                if (bloomSafe > 0.001f && lum > 0.72f) {
                    lum = (lum + (lum - 0.72f) * bloomSafe * 0.9f).coerceIn(0f, 1f)
                }
                if (vignetteSafe > 0.001f) {
                    val dx = x - cx
                    val dy = y - cy
                    val d = sqrt(dx * dx + dy * dy) / maxDist
                    val factor = 1f - vignetteSafe * d.pow(1.6f)
                    lum = (lum * factor).coerceIn(0f, 1f)
                }
                if (ribbingSafe > 0.001f) {
                    val rib = 0.5f + 0.5f * sin((x * 0.19f) + (y * 0.04f))
                    lum = (lum * (1f - ribbingSafe * 0.14f) + rib * ribbingSafe * 0.14f).coerceIn(0f, 1f)
                }
                if (settings.scanlines && (y % scanStepSafe == 0)) {
                    lum = (lum * (1f - scanSafe * 0.8f)).coerceIn(0f, 1f)
                }
                if (settings.dither) {
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
                    if (settings.glitchRgb && hash01(x, y, 12) < glitchSafe * 0.06f) {
                        lum = (lum + (if ((x + y) % 2 == 0) 0.08f else -0.08f) * glitchSafe).coerceIn(0f, 1f)
                    }
                }
                lumFinal[row + x] = lum
                val srcColor = pixels[sy * charW + sx2]
                val argb = if (settings.preserveSourceColors) {
                    var rr = Color.red(srcColor) / 255f
                    var gg = Color.green(srcColor) / 255f
                    var bb = Color.blue(srcColor) / 255f
                    val g0 = 0.299f * rr + 0.587f * gg + 0.114f * bb
                    val satMul = (settings.saturation + colorBoostSafe * 0.85f).coerceIn(0f, 3f)
                    rr = (g0 + (rr - g0) * satMul).coerceIn(0f, 1f)
                    gg = (g0 + (gg - g0) * satMul).coerceIn(0f, 1f)
                    bb = (g0 + (bb - g0) * satMul).coerceIn(0f, 1f)

                    // Keep hue from source, but drive intensity from post-FX luma.
                    val shade = (0.22f + lum * 0.98f).coerceIn(0f, 1.25f)
                    rr = (rr * shade).coerceIn(0f, 1f)
                    gg = (gg * shade).coerceIn(0f, 1f)
                    bb = (bb * shade).coerceIn(0f, 1f)
                    if (settings.invert) {
                        rr = 1f - rr
                        gg = 1f - gg
                        bb = 1f - bb
                    }
                    Color.argb(
                        255,
                        (rr * 255f).roundToInt().coerceIn(0, 255),
                        (gg * 255f).roundToInt().coerceIn(0, 255),
                        (bb * 255f).roundToInt().coerceIn(0, 255)
                    )
                } else {
                    val v = (lum * 255f).roundToInt().coerceIn(0, 255)
                    Color.argb(255, v, v, v)
                }
                argbFinal[row + x] = argb
            }
            sb.append('\n')
        }

        val ascii = if (settings.watermarkEnabled) {
            applyWatermark(sb.toString(), charW, settings.watermarkText)
        } else {
            sb.toString()
        }

        val settingsHash = buildSettingsHash(settings, map, quality, aspect)
        return RenderOutput(
            ascii = ascii,
            raster = argbToBitmap(argbFinal, charW, charH),
            meta = RenderMeta(
                widthChars = charW,
                heightChars = charH,
                quality = quality,
                charAspectRatio = aspect,
                settingsHash = settingsHash
            )
        )
    }

    fun rasterizeAsciiToBitmap(
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

    fun exportSvg(ascii: String, settings: RenderSettings): String {
        val lines = ascii.trimEnd('\n').lines()
        val width = max(1, settings.widthChars)
        val lineCount = max(1, lines.size)
        val font = settings.fontSizeSp.coerceIn(6f, 32f)
        val lineHeight = font * 1.15f
        val svgWidth = (width * font * 0.64f + 24f)
        val svgHeight = (lineCount * lineHeight + 24f)
        val esc = { s: String ->
            s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        }
        val sb = StringBuilder()
        sb.append("""<svg xmlns="http://www.w3.org/2000/svg" width="$svgWidth" height="$svgHeight" viewBox="0 0 $svgWidth $svgHeight">""")
        sb.append("""<rect width="100%" height="100%" fill="#0b1018"/>""")
        sb.append("""<g font-family="monospace" font-size="$font" fill="#e8f2ff" xml:space="preserve">""")
        var y = 16f + font
        for (line in lines) {
            sb.append("""<text x="12" y="$y">${esc(line)}</text>""")
            y += lineHeight
        }
        sb.append("</g></svg>")
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

    private fun argbToBitmap(argb: IntArray, width: Int, height: Int): Bitmap {
        val out = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        out.setPixels(argb, 0, width, 0, 0, width, height)
        return out
    }

    private fun buildSettingsHash(
        settings: RenderSettings,
        charset: String,
        quality: PreviewQuality,
        charAspectRatio: Float
    ): Int {
        return listOf(
            settings.widthChars,
            "%.3f".format(java.util.Locale.US, charAspectRatio),
            "%.3f".format(java.util.Locale.US, settings.contrast),
            "%.3f".format(java.util.Locale.US, settings.brightness),
            "%.3f".format(java.util.Locale.US, settings.gamma),
            "%.3f".format(java.util.Locale.US, settings.saturation),
            "%.3f".format(java.util.Locale.US, settings.exposure),
            "%.3f".format(java.util.Locale.US, settings.sharpen),
            "%.3f".format(java.util.Locale.US, settings.vignette),
            "%.3f".format(java.util.Locale.US, settings.bloom),
            "%.3f".format(java.util.Locale.US, settings.denoise),
            "%.3f".format(java.util.Locale.US, settings.edgeBoost),
            settings.posterize,
            settings.scanlines,
            "%.3f".format(java.util.Locale.US, settings.scanStrength),
            settings.scanStep,
            settings.dither,
            "%.3f".format(java.util.Locale.US, settings.curvature),
            "%.3f".format(java.util.Locale.US, settings.concavity),
            "%.3f".format(java.util.Locale.US, settings.curveCenterX),
            "%.3f".format(java.util.Locale.US, settings.curveExpand),
            settings.curveType,
            "%.3f".format(java.util.Locale.US, settings.grain),
            "%.3f".format(java.util.Locale.US, settings.chroma),
            "%.3f".format(java.util.Locale.US, settings.ribbing),
            "%.3f".format(java.util.Locale.US, settings.clarity),
            "%.3f".format(java.util.Locale.US, settings.motionBlur),
            "%.3f".format(java.util.Locale.US, settings.colorBoost),
            "%.3f".format(java.util.Locale.US, settings.glitch),
            "%.3f".format(java.util.Locale.US, settings.glitchDensity),
            "%.3f".format(java.util.Locale.US, settings.glitchShift),
            settings.glitchRgb,
            "%.3f".format(java.util.Locale.US, settings.glitchBlock),
            "%.3f".format(java.util.Locale.US, settings.glitchJitter),
            "%.3f".format(java.util.Locale.US, settings.glitchNoise),
            settings.invert,
            settings.preserveSourceColors,
            charset,
            quality.id
        ).joinToString("|").hashCode()
    }
}
