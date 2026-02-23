package com.asciistudio.mobile.feature.theme

import androidx.compose.runtime.Composable
import com.asciistudio.mobile.ThemeTab
import com.asciistudio.mobile.ui.theme.AppLanguage
import com.asciistudio.mobile.ui.theme.MobileThemeMode

@Composable
fun ThemeScreen(
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
    ThemeTab(
        lang = lang,
        themeMode = themeMode,
        onThemeMode = onThemeMode,
        tailEnabled = tailEnabled,
        onTailEnabled = onTailEnabled,
        bgR = bgR,
        bgG = bgG,
        bgB = bgB,
        panelR = panelR,
        panelG = panelG,
        panelB = panelB,
        accR = accR,
        accG = accG,
        accB = accB,
        textR = textR,
        textG = textG,
        textB = textB,
        onBgR = onBgR,
        onBgG = onBgG,
        onBgB = onBgB,
        onPanelR = onPanelR,
        onPanelG = onPanelG,
        onPanelB = onPanelB,
        onAccR = onAccR,
        onAccG = onAccG,
        onAccB = onAccB,
        onTextR = onTextR,
        onTextG = onTextG,
        onTextB = onTextB
    )
}
