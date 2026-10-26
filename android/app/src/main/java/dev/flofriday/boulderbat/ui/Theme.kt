package dev.flofriday.boulderbat.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val BatYellow = Color(0xFFFFCC00)
val CardDark = Color(0xFF191E20)
val Quiet = Color(0xFF58D6A3)

@Composable
fun BoulderbatTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    MaterialTheme(colorScheme = if (dark) darkColorScheme(
        primary = BatYellow, onPrimary = Color.Black, primaryContainer = Color(0xFF493D10),
        secondary = Color(0xFFE9CF7A), secondaryContainer = Color(0xFF40391E), onSecondaryContainer = Color(0xFFFFE9A2),
        surfaceContainer = Color(0xFF202629),
        background = Color(0xFF101416), surface = Color(0xFF171D20), onSurface = Color(0xFFECEFEF),
    ) else lightColorScheme(
        primary = Color(0xFF805A00), onPrimary = Color.White, primaryContainer = Color(0xFFFFECAA),
        secondary = Color(0xFF705B16), secondaryContainer = Color(0xFFFFEDB4), onSecondaryContainer = Color(0xFF332900),
        surfaceContainer = Color(0xFFF2F2ED),
        background = Color(0xFFFAFAF7), surface = Color.White, onSurface = Color(0xFF172027),
    ), content = content)
}
