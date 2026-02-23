package com.asciistudio.mobile.core.presets

import com.asciistudio.mobile.core.model.RenderSettings
import org.json.JSONObject

data class UasPreset(
    val version: Int = 1,
    val name: String,
    val description: String = "",
    val settings: RenderSettings
) {
    fun toJsonString(): String {
        val o = JSONObject()
            .put("version", version)
            .put("name", name)
            .put("description", description)
            .put("settings", settingsToJson(settings))
        return o.toString(2)
    }

    companion object {
        fun fromJsonString(rawUtf8: String): UasPreset {
            val clean = rawUtf8.trim().trimStart('\uFEFF')
            val obj = JSONObject(clean)
            return UasPreset(
                version = obj.optInt("version", 1),
                name = obj.optString("name", "Preset"),
                description = obj.optString("description", ""),
                settings = settingsFromJson(obj.optJSONObject("settings") ?: JSONObject())
            )
        }

        private fun settingsToJson(s: RenderSettings): JSONObject = JSONObject()
            .put("widthChars", s.widthChars)
            .put("charAspectRatio", s.charAspectRatio.toDouble())
            .put("fontSizeSp", s.fontSizeSp.toDouble())
            .put("contrast", s.contrast.toDouble())
            .put("brightness", s.brightness.toDouble())
            .put("gamma", s.gamma.toDouble())
            .put("saturation", s.saturation.toDouble())
            .put("exposure", s.exposure.toDouble())
            .put("sharpen", s.sharpen.toDouble())
            .put("vignette", s.vignette.toDouble())
            .put("bloom", s.bloom.toDouble())
            .put("denoise", s.denoise.toDouble())
            .put("edgeBoost", s.edgeBoost.toDouble())
            .put("posterize", s.posterize)
            .put("scanlines", s.scanlines)
            .put("scanStrength", s.scanStrength.toDouble())
            .put("scanStep", s.scanStep)
            .put("dither", s.dither)
            .put("curvature", s.curvature.toDouble())
            .put("concavity", s.concavity.toDouble())
            .put("curveCenterX", s.curveCenterX.toDouble())
            .put("curveExpand", s.curveExpand.toDouble())
            .put("curveType", s.curveType)
            .put("grain", s.grain.toDouble())
            .put("chroma", s.chroma.toDouble())
            .put("ribbing", s.ribbing.toDouble())
            .put("clarity", s.clarity.toDouble())
            .put("motionBlur", s.motionBlur.toDouble())
            .put("colorBoost", s.colorBoost.toDouble())
            .put("glitch", s.glitch.toDouble())
            .put("glitchDensity", s.glitchDensity.toDouble())
            .put("glitchShift", s.glitchShift.toDouble())
            .put("glitchRgb", s.glitchRgb)
            .put("glitchBlock", s.glitchBlock.toDouble())
            .put("glitchJitter", s.glitchJitter.toDouble())
            .put("glitchNoise", s.glitchNoise.toDouble())
            .put("invert", s.invert)
            .put("preserveSourceColors", s.preserveSourceColors)
            .put("charsetKey", s.charsetKey)
            .put("charsetValue", s.charsetValue)
            .put("watermarkEnabled", s.watermarkEnabled)
            .put("watermarkText", s.watermarkText)
            .put("renderFps", s.renderFps)
            .put("renderCodec", s.renderCodec)
            .put("renderBitrate", s.renderBitrate)
            .put("exportFormat", s.exportFormat)

        private fun settingsFromJson(j: JSONObject): RenderSettings = RenderSettings(
            widthChars = j.optInt("widthChars", 120),
            charAspectRatio = j.optDouble("charAspectRatio", 0.55).toFloat(),
            fontSizeSp = j.optDouble("fontSizeSp", 8.5).toFloat(),
            contrast = j.optDouble("contrast", 1.0).toFloat(),
            brightness = j.optDouble("brightness", 0.0).toFloat(),
            gamma = j.optDouble("gamma", 1.0).toFloat(),
            saturation = j.optDouble("saturation", 1.0).toFloat(),
            exposure = j.optDouble("exposure", 0.0).toFloat(),
            sharpen = j.optDouble("sharpen", 0.0).toFloat(),
            vignette = j.optDouble("vignette", 0.0).toFloat(),
            bloom = j.optDouble("bloom", 0.0).toFloat(),
            denoise = j.optDouble("denoise", 0.0).toFloat(),
            edgeBoost = j.optDouble("edgeBoost", 0.0).toFloat(),
            posterize = j.optInt("posterize", 0),
            scanlines = j.optBoolean("scanlines", false),
            scanStrength = j.optDouble("scanStrength", 0.22).toFloat(),
            scanStep = j.optInt("scanStep", 3),
            dither = j.optBoolean("dither", false),
            curvature = j.optDouble("curvature", 0.0).toFloat(),
            concavity = j.optDouble("concavity", 0.0).toFloat(),
            curveCenterX = j.optDouble("curveCenterX", 0.0).toFloat(),
            curveExpand = j.optDouble("curveExpand", 0.0).toFloat(),
            curveType = j.optInt("curveType", 0),
            grain = j.optDouble("grain", 0.0).toFloat(),
            chroma = j.optDouble("chroma", 0.0).toFloat(),
            ribbing = j.optDouble("ribbing", 0.0).toFloat(),
            clarity = j.optDouble("clarity", 0.0).toFloat(),
            motionBlur = j.optDouble("motionBlur", 0.0).toFloat(),
            colorBoost = j.optDouble("colorBoost", 0.0).toFloat(),
            glitch = j.optDouble("glitch", 0.0).toFloat(),
            glitchDensity = j.optDouble("glitchDensity", 0.35).toFloat(),
            glitchShift = j.optDouble("glitchShift", 0.42).toFloat(),
            glitchRgb = j.optBoolean("glitchRgb", true),
            glitchBlock = j.optDouble("glitchBlock", 0.1).toFloat(),
            glitchJitter = j.optDouble("glitchJitter", 0.1).toFloat(),
            glitchNoise = j.optDouble("glitchNoise", 0.12).toFloat(),
            invert = j.optBoolean("invert", false),
            preserveSourceColors = j.optBoolean("preserveSourceColors", false),
            charsetKey = j.optString("charsetKey", "Classic"),
            charsetValue = j.optString("charsetValue", "@%#*+=-:. "),
            watermarkEnabled = j.optBoolean("watermarkEnabled", false),
            watermarkText = j.optString("watermarkText", "SNERK503"),
            renderFps = j.optInt("renderFps", 24),
            renderCodec = j.optString("renderCodec", "libx264"),
            renderBitrate = j.optString("renderBitrate", "2M"),
            exportFormat = j.optString("exportFormat", "PNG")
        )
    }
}
