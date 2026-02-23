package com.asciistudio.mobile.feature.editor

import android.graphics.Bitmap
import android.graphics.Color
import com.asciistudio.mobile.core.model.PreviewQuality
import com.asciistudio.mobile.core.model.RenderSettings
import com.asciistudio.mobile.testutil.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class EditorViewModelPipelineTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun latestRequestWinsAfterRapidUpdates() = runTest {
        val vm = EditorViewModel()
        val bmp = Bitmap.createBitmap(24, 24, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.WHITE)
        }
        vm.submitRender(bmp, RenderSettings(widthChars = 80), PreviewQuality.Draft)
        vm.submitRender(bmp, RenderSettings(widthChars = 160), PreviewQuality.High)

        advanceTimeBy(120)
        advanceUntilIdle()
    }
}
