package com.asciistudio.mobile.feature.presets

import androidx.compose.runtime.Composable
import com.asciistudio.mobile.AsciiPreset
import com.asciistudio.mobile.PresetsTab
import com.asciistudio.mobile.ui.theme.AppLanguage

@Composable
internal fun PresetsScreen(
    lang: AppLanguage,
    onApply: (AsciiPreset) -> Unit
) {
    PresetsTab(lang = lang, onApply = onApply)
}
