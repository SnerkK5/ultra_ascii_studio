package com.asciistudio.mobile.core.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ProjectV2ParserTest {
    @Test
    fun parsesUtf8WithBom() {
        val raw = "\uFEFF{\"schemaVersion\":2,\"projects\":[{\"id\":\"a\",\"title\":\"T\",\"sourceUri\":\"file://a.png\",\"mediaKind\":\"image\",\"durationMs\":0,\"updatedAt\":1}]}"
        val parsed = ProjectV2.parseList(raw)
        assertEquals(1, parsed.size)
        assertEquals("a", parsed.first().id)
    }

    @Test
    fun parsesLegacyArrayFormat() {
        val raw = "[{\"id\":\"x\",\"title\":\"Legacy\",\"uri\":\"file://legacy.jpg\",\"kind\":\"image\",\"durationMs\":0,\"updatedAt\":7}]"
        val parsed = ProjectV2.parseList(raw)
        assertEquals(1, parsed.size)
        assertEquals("Legacy", parsed.first().title)
        assertEquals("file://legacy.jpg", parsed.first().sourceUri)
    }

    @Test
    fun serializeThenParseRoundTrip() {
        val input = listOf(
            ProjectV2(
                id = "id-1",
                title = "Demo",
                sourceUri = "file://demo.png",
                mediaKind = "image",
                durationMs = 0,
                updatedAt = 11
            )
        )
        val encoded = ProjectV2.serializeList(input)
        val parsed = ProjectV2.parseList(encoded)
        assertTrue(parsed.isNotEmpty())
        assertEquals("id-1", parsed.first().id)
    }
}
