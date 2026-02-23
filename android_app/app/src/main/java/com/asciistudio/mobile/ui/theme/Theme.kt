package com.asciistudio.mobile.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf

private val LocalAsciiPalette = staticCompositionLocalOf {
    paletteFor(MobileThemeMode.Midnight, CustomThemeConfig())
}

object AsciiTheme {
    val palette: ThemePalette
        @Composable
        @ReadOnlyComposable
        get() = LocalAsciiPalette.current
}

private fun materialScheme(p: ThemePalette, isLight: Boolean): ColorScheme {
    return if (isLight) {
        lightColorScheme(
            primary = p.accent,
            onPrimary = p.bg,
            secondary = p.accent2,
            onSecondary = p.bg,
            background = p.bg,
            onBackground = p.text,
            surface = p.panelStrong,
            onSurface = p.text,
            outline = p.border
        )
    } else {
        darkColorScheme(
            primary = p.accent,
            onPrimary = p.bg,
            secondary = p.accent2,
            onSecondary = p.bg,
            background = p.bg,
            onBackground = p.text,
            surface = p.panelStrong,
            onSurface = p.text,
            outline = p.border
        )
    }
}

@Composable
fun AsciiStudioMobileTheme(
    mode: MobileThemeMode,
    custom: CustomThemeConfig,
    content: @Composable () -> Unit
) {
    val palette = paletteFor(mode, custom)
    val isLight = mode == MobileThemeMode.Light || mode == MobileThemeMode.Sketch

    androidx.compose.runtime.CompositionLocalProvider(LocalAsciiPalette provides palette) {
        MaterialTheme(
            colorScheme = materialScheme(palette, isLight),
            typography = Typography,
            content = content
        )
    }
}
