package com.asciistudio.mobile.feature.home

import androidx.compose.runtime.Composable
import com.asciistudio.mobile.HomeTab
import com.asciistudio.mobile.ProjectEntry
import com.asciistudio.mobile.ui.theme.AppLanguage

@Composable
internal fun HomeScreen(
    lang: AppLanguage,
    projects: List<ProjectEntry>,
    onPickVideo: () -> Unit,
    onPickPhoto: () -> Unit,
    onOpenProject: (ProjectEntry) -> Unit,
    onOpenSettings: () -> Unit,
    onStartTutorial: () -> Unit,
    onOpenPresets: () -> Unit
) {
    HomeTab(
        lang = lang,
        projects = projects,
        onPickVideo = onPickVideo,
        onPickPhoto = onPickPhoto,
        onOpenProject = onOpenProject,
        onOpenSettings = onOpenSettings,
        onStartTutorial = onStartTutorial,
        onOpenPresets = onOpenPresets
    )
}
