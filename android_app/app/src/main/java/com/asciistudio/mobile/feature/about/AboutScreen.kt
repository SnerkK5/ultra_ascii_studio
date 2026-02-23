package com.asciistudio.mobile.feature.about

import androidx.compose.runtime.Composable
import com.asciistudio.mobile.AboutTab
import com.asciistudio.mobile.ui.theme.AppLanguage

@Composable
fun AboutScreen(
    lang: AppLanguage,
    onOpenRepo: () -> Unit
) {
    AboutTab(lang = lang, onOpenRepo = onOpenRepo)
}
