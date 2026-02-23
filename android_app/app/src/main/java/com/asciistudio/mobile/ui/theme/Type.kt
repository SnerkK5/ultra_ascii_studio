package com.asciistudio.mobile.ui.theme

enum class MobileThemeMode(
    val id: String,
    val titleEn: String,
    val titleRu: String,
    val titleZh: String
) {
    Dark("dark", "Dark", "Темная", "深色"),
    Midnight("midnight", "Midnight", "Полночь", "午夜"),
    Retro("retro", "Retro", "Ретро", "复古"),
    Sketch("sketch", "Sketch", "Скетч", "素描"),
    Cyberpunk2077("cyberpunk 2077", "Cyberpunk 2077", "Киберпанк 2077", "赛博朋克2077"),
    AphexTwin("aphex twin", "Aphex Twin", "Aphex Twin", "Aphex Twin"),
    Dedsec("dedsec", "DEDSEC", "DEDSEC", "DEDSEC"),
    Solarized("solarized", "Solarized", "Solarized", "Solarized"),
    Custom("custom", "Custom", "Кастом", "自定义"),
    Light("light", "Light", "Светлая", "浅色");

    fun label(lang: AppLanguage): String = when (lang) {
        AppLanguage.En -> titleEn
        AppLanguage.Ru -> titleRu
        AppLanguage.Zh -> titleZh
    }

    fun next(): MobileThemeMode {
        val all = entries
        return all[(ordinal + 1) % all.size]
    }
}

enum class AppLanguage { En, Ru, Zh }
