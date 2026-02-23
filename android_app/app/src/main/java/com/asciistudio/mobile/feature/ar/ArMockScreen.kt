package com.asciistudio.mobile.feature.ar

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.asciistudio.mobile.ui.theme.AsciiTheme

@Composable
fun ArMockScreen() {
    val p = AsciiTheme.palette
    var overlayOn by rememberSaveable { mutableStateOf(true) }
    var gridOn by rememberSaveable { mutableStateOf(true) }

    Column(
        modifier = Modifier.fillMaxSize().padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("AR Mock", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Card(
            colors = CardDefaults.cardColors(containerColor = p.panelStrong.copy(alpha = 0.58f)),
            modifier = Modifier.fillMaxWidth().height(340.dp)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(p.bg.copy(alpha = 0.84f), RoundedCornerShape(16.dp))
                    .border(1.dp, p.border.copy(alpha = 0.7f), RoundedCornerShape(16.dp))
            ) {
                if (gridOn) {
                    Text(
                        "Camera Placeholder Grid",
                        modifier = Modifier.align(Alignment.Center),
                        color = p.textSubtle
                    )
                }
                if (overlayOn) {
                    Text(
                        "@@@\n@ @\n@@@",
                        modifier = Modifier.align(Alignment.TopStart).padding(16.dp),
                        fontFamily = FontFamily.Monospace,
                        color = Color(0xFF9CFFB1)
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = overlayOn, onClick = { overlayOn = !overlayOn }, label = { Text("ASCII Overlay") })
            FilterChip(selected = gridOn, onClick = { gridOn = !gridOn }, label = { Text("Camera Grid") })
        }
    }
}
