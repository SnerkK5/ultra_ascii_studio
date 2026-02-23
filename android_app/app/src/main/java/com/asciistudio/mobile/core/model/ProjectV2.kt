package com.asciistudio.mobile.core.model

import org.json.JSONArray
import org.json.JSONObject

data class ProjectV2(
    val schemaVersion: Int = 2,
    val id: String,
    val title: String,
    val sourceUri: String,
    val mediaKind: String,
    val durationMs: Long,
    val updatedAt: Long,
    val settings: RenderSettings = RenderSettings()
) {
    fun toJson(): JSONObject = JSONObject()
        .put("schemaVersion", schemaVersion)
        .put("id", id)
        .put("title", title)
        .put("sourceUri", sourceUri)
        .put("mediaKind", mediaKind)
        .put("durationMs", durationMs)
        .put("updatedAt", updatedAt)
        .put("settings", RenderSettingsJson.run { settings.toJson() })

    companion object {
        fun fromJson(json: JSONObject): ProjectV2 {
            val id = json.optString("id")
            val title = json.optString("title")
            val sourceUri = json.optString("sourceUri")
            val mediaKind = json.optString("mediaKind", json.optString("kind", "image"))
            val durationMs = json.optLong("durationMs", 0L)
            val updatedAt = json.optLong("updatedAt", 0L)
            val settingsJson = json.optJSONObject("settings") ?: JSONObject()
            return ProjectV2(
                schemaVersion = json.optInt("schemaVersion", 2),
                id = id,
                title = title,
                sourceUri = sourceUri,
                mediaKind = mediaKind,
                durationMs = durationMs,
                updatedAt = updatedAt,
                settings = RenderSettingsJson.fromJson(settingsJson)
            )
        }

        fun parseList(rawUtf8: String): List<ProjectV2> {
            val clean = rawUtf8.trim().trimStart('\uFEFF')
            if (clean.isBlank()) return emptyList()

            val out = mutableListOf<ProjectV2>()
            val root = clean.first()
            if (root == '[') {
                // Legacy v1 array format.
                val arr = JSONArray(clean)
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    val id = o.optString("id")
                    val title = o.optString("title")
                    val uri = o.optString("uri")
                    if (id.isBlank() || uri.isBlank()) continue
                    out += ProjectV2(
                        id = id,
                        title = if (title.isNotBlank()) title else "Project",
                        sourceUri = uri,
                        mediaKind = o.optString("kind", "image"),
                        durationMs = o.optLong("durationMs", 0L),
                        updatedAt = o.optLong("updatedAt", 0L)
                    )
                }
                return out.sortedByDescending { it.updatedAt }
            }

            // v2 object format: { "schemaVersion":2, "projects":[...] }
            val obj = JSONObject(clean)
            val arr = obj.optJSONArray("projects") ?: JSONArray()
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                runCatching { out += fromJson(o) }
            }
            return out.sortedByDescending { it.updatedAt }
        }

        fun serializeList(projects: List<ProjectV2>): String {
            val arr = JSONArray()
            projects.forEach { arr.put(it.toJson()) }
            return JSONObject()
                .put("schemaVersion", 2)
                .put("projects", arr)
                .toString()
        }
    }
}

private object RenderSettingsJson {
    fun RenderSettings.toJson(): JSONObject = JSONObject()
        .put("widthChars", widthChars)
        .put("charAspectRatio", charAspectRatio.toDouble())
        .put("fontSizeSp", fontSizeSp.toDouble())
        .put("contrast", contrast.toDouble())
        .put("brightness", brightness.toDouble())
        .put("gamma", gamma.toDouble())
        .put("saturation", saturation.toDouble())
        .put("exposure", exposure.toDouble())
        .put("sharpen", sharpen.toDouble())
        .put("vignette", vignette.toDouble())
        .put("bloom", bloom.toDouble())
        .put("denoise", denoise.toDouble())
        .put("edgeBoost", edgeBoost.toDouble())
        .put("posterize", posterize)
        .put("scanlines", scanlines)
        .put("scanStrength", scanStrength.toDouble())
        .put("scanStep", scanStep)
        .put("dither", dither)
        .put("curvature", curvature.toDouble())
        .put("concavity", concavity.toDouble())
        .put("curveCenterX", curveCenterX.toDouble())
        .put("curveExpand", curveExpand.toDouble())
        .put("curveType", curveType)
        .put("grain", grain.toDouble())
        .put("chroma", chroma.toDouble())
        .put("ribbing", ribbing.toDouble())
        .put("clarity", clarity.toDouble())
        .put("motionBlur", motionBlur.toDouble())
        .put("colorBoost", colorBoost.toDouble())
        .put("glitch", glitch.toDouble())
        .put("glitchDensity", glitchDensity.toDouble())
        .put("glitchShift", glitchShift.toDouble())
        .put("glitchRgb", glitchRgb)
        .put("glitchBlock", glitchBlock.toDouble())
        .put("glitchJitter", glitchJitter.toDouble())
        .put("glitchNoise", glitchNoise.toDouble())
        .put("invert", invert)
        .put("preserveSourceColors", preserveSourceColors)
        .put("charsetKey", charsetKey)
        .put("charsetValue", charsetValue)
        .put("watermarkEnabled", watermarkEnabled)
        .put("watermarkText", watermarkText)
        .put("renderFps", renderFps)
        .put("renderCodec", renderCodec)
        .put("renderBitrate", renderBitrate)
        .put("exportFormat", exportFormat)

    fun fromJson(json: JSONObject): RenderSettings = RenderSettings(
        widthChars = json.optInt("widthChars", 120),
        charAspectRatio = json.optDouble("charAspectRatio", 0.55).toFloat(),
        fontSizeSp = json.optDouble("fontSizeSp", 8.5).toFloat(),
        contrast = json.optDouble("contrast", 1.0).toFloat(),
        brightness = json.optDouble("brightness", 0.0).toFloat(),
        gamma = json.optDouble("gamma", 1.0).toFloat(),
        saturation = json.optDouble("saturation", 1.0).toFloat(),
        exposure = json.optDouble("exposure", 0.0).toFloat(),
        sharpen = json.optDouble("sharpen", 0.0).toFloat(),
        vignette = json.optDouble("vignette", 0.0).toFloat(),
        bloom = json.optDouble("bloom", 0.0).toFloat(),
        denoise = json.optDouble("denoise", 0.0).toFloat(),
        edgeBoost = json.optDouble("edgeBoost", 0.0).toFloat(),
        posterize = json.optInt("posterize", 0),
        scanlines = json.optBoolean("scanlines", false),
        scanStrength = json.optDouble("scanStrength", 0.22).toFloat(),
        scanStep = json.optInt("scanStep", 3),
        dither = json.optBoolean("dither", false),
        curvature = json.optDouble("curvature", 0.0).toFloat(),
        concavity = json.optDouble("concavity", 0.0).toFloat(),
        curveCenterX = json.optDouble("curveCenterX", 0.0).toFloat(),
        curveExpand = json.optDouble("curveExpand", 0.0).toFloat(),
        curveType = json.optInt("curveType", 0),
        grain = json.optDouble("grain", 0.0).toFloat(),
        chroma = json.optDouble("chroma", 0.0).toFloat(),
        ribbing = json.optDouble("ribbing", 0.0).toFloat(),
        clarity = json.optDouble("clarity", 0.0).toFloat(),
        motionBlur = json.optDouble("motionBlur", 0.0).toFloat(),
        colorBoost = json.optDouble("colorBoost", 0.0).toFloat(),
        glitch = json.optDouble("glitch", 0.0).toFloat(),
        glitchDensity = json.optDouble("glitchDensity", 0.35).toFloat(),
        glitchShift = json.optDouble("glitchShift", 0.42).toFloat(),
        glitchRgb = json.optBoolean("glitchRgb", true),
        glitchBlock = json.optDouble("glitchBlock", 0.10).toFloat(),
        glitchJitter = json.optDouble("glitchJitter", 0.10).toFloat(),
        glitchNoise = json.optDouble("glitchNoise", 0.12).toFloat(),
        invert = json.optBoolean("invert", false),
        preserveSourceColors = json.optBoolean("preserveSourceColors", false),
        charsetKey = json.optString("charsetKey", "Classic"),
        charsetValue = json.optString("charsetValue", "@%#*+=-:. "),
        watermarkEnabled = json.optBoolean("watermarkEnabled", false),
        watermarkText = json.optString("watermarkText", "SNERK503"),
        renderFps = json.optInt("renderFps", 24),
        renderCodec = json.optString("renderCodec", "libx264"),
        renderBitrate = json.optString("renderBitrate", "2M"),
        exportFormat = json.optString("exportFormat", "PNG")
    )
}
