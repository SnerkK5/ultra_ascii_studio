package com.asciistudio.mobile.ui.theme

import androidx.compose.ui.graphics.Color

data class ThemePalette(
    val bg: Color,
    val bgSecondary: Color,
    val panel: Color,
    val panelStrong: Color,
    val text: Color,
    val textSubtle: Color,
    val accent: Color,
    val accent2: Color,
    val border: Color
)

data class CustomThemeConfig(
    val bg: Color = Color(0xFF0C1018),
    val panel: Color = Color(0xFF151C29),
    val accent: Color = Color(0xFF5EC8FF),
    val text: Color = Color(0xFFE8F2FF)
)

fun paletteFor(mode: MobileThemeMode, custom: CustomThemeConfig): ThemePalette {
    return when (mode) {
        MobileThemeMode.Dark -> ThemePalette(
            bg = Color(0xFF0A0F17),
            bgSecondary = Color(0xFF0E1624),
            panel = Color(0xFF202A3A),
            panelStrong = Color(0xFF2A3548),
            text = Color(0xFFEAF3FF),
            textSubtle = Color(0xFFC8DCEE),
            accent = Color(0xFF63C9FF),
            accent2 = Color(0xFF76F2D1),
            border = Color(0xFFA3BDE0)
        )

        MobileThemeMode.Midnight -> ThemePalette(
            bg = Color(0xFF050A13),
            bgSecondary = Color(0xFF101B2B),
            panel = Color(0xFF162338),
            panelStrong = Color(0xFF1E2F49),
            text = Color(0xFFEAF6FF),
            textSubtle = Color(0xFFB8D0E9),
            accent = Color(0xFF5EC8FF),
            accent2 = Color(0xFF7AE2FF),
            border = Color(0xFF90B9DB)
        )

        MobileThemeMode.Retro -> ThemePalette(
            bg = Color(0xFF17130E),
            bgSecondary = Color(0xFF272016),
            panel = Color(0xFF332818),
            panelStrong = Color(0xFF47361F),
            text = Color(0xFFFFF2D8),
            textSubtle = Color(0xFFF2DDB9),
            accent = Color(0xFFFFA447),
            accent2 = Color(0xFFFFD677),
            border = Color(0xFFF0BB75)
        )

        MobileThemeMode.Sketch -> ThemePalette(
            bg = Color(0xFFEDEFF4),
            bgSecondary = Color(0xFFF4F6FA),
            panel = Color(0xFFEAF0F8),
            panelStrong = Color(0xFFDEE8F3),
            text = Color(0xFF202734),
            textSubtle = Color(0xFF3F526D),
            accent = Color(0xFF2F88E9),
            accent2 = Color(0xFF66A8F7),
            border = Color(0xFFA6B7CB)
        )

        MobileThemeMode.Cyberpunk2077 -> ThemePalette(
            bg = Color(0xFF090612),
            bgSecondary = Color(0xFF140C22),
            panel = Color(0xFF1B1130),
            panelStrong = Color(0xFF22173D),
            text = Color(0xFFF5EAFF),
            textSubtle = Color(0xFFD8C0EC),
            accent = Color(0xFFFFE100),
            accent2 = Color(0xFF00F6FF),
            border = Color(0xFFFFCA00)
        )

        MobileThemeMode.AphexTwin -> ThemePalette(
            bg = Color(0xFF0C0C11),
            bgSecondary = Color(0xFF171726),
            panel = Color(0xFF2A2C42),
            panelStrong = Color(0xFF333550),
            text = Color(0xFFF0EEFF),
            textSubtle = Color(0xFFCDD0E9),
            accent = Color(0xFFB894FF),
            accent2 = Color(0xFF88E6FF),
            border = Color(0xFF9AA4D8)
        )

        MobileThemeMode.Dedsec -> ThemePalette(
            bg = Color(0xFF090E0B),
            bgSecondary = Color(0xFF101912),
            panel = Color(0xFF152219),
            panelStrong = Color(0xFF1B2B1F),
            text = Color(0xFFE6FFE8),
            textSubtle = Color(0xFFB9E3C3),
            accent = Color(0xFF48FF83),
            accent2 = Color(0xFF00E0B6),
            border = Color(0xFF68E59A)
        )

        MobileThemeMode.Solarized -> ThemePalette(
            bg = Color(0xFF002B36),
            bgSecondary = Color(0xFF073642),
            panel = Color(0xFF163E4A),
            panelStrong = Color(0xFF1F4C59),
            text = Color(0xFFEEE8D5),
            textSubtle = Color(0xFFD5C8AC),
            accent = Color(0xFF2AA198),
            accent2 = Color(0xFFB58900),
            border = Color(0xFF5CA49C)
        )

        MobileThemeMode.Custom -> ThemePalette(
            bg = custom.bg,
            bgSecondary = blend(custom.bg, Color.Black, 0.18f),
            panel = custom.panel,
            panelStrong = blend(custom.panel, Color.White, 0.10f),
            text = custom.text,
            textSubtle = blend(custom.text, Color.Black, 0.18f),
            accent = custom.accent,
            accent2 = blend(custom.accent, Color.White, 0.24f),
            border = blend(custom.accent, Color.White, 0.45f)
        )

        MobileThemeMode.Light -> ThemePalette(
            bg = Color(0xFFF4F8FF),
            bgSecondary = Color(0xFFEFF4FF),
            panel = Color(0xFFEAF1FF),
            panelStrong = Color(0xFFF8FBFF),
            text = Color(0xFF172236),
            textSubtle = Color(0xFF405C7A),
            accent = Color(0xFF2B7EDB),
            accent2 = Color(0xFF5EAFF7),
            border = Color(0xFF8EA9CC)
        )
    }
}

private fun blend(a: Color, b: Color, t: Float): Color {
    val clamped = t.coerceIn(0f, 1f)
    return Color(
        red = a.red + (b.red - a.red) * clamped,
        green = a.green + (b.green - a.green) * clamped,
        blue = a.blue + (b.blue - a.blue) * clamped,
        alpha = a.alpha + (b.alpha - a.alpha) * clamped
    )
}
