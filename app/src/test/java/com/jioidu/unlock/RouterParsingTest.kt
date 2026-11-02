package com.jioidu.unlock

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class RouterParsingTest {
    private val mtk = RouterDevice("JIDU6101", "test", "board")
    private val qcom = RouterDevice("JIDU6611", "test", "board")

    @Test fun compatibilityHonorsFamilyCutoffs() {
        assertTrue(checkCompatibility(mtk, "ARCNJIO_JIDU6101_R3.2.0").confirmed)
        assertFalse(checkCompatibility(mtk, "ARCNJIO_JIDU6101_R3.2.1").confirmed)
        assertFalse(checkCompatibility(mtk, "ARCNJIO_JIDU6101_R3.2.0.1").confirmed)
        assertTrue(checkCompatibility(qcom, "SRCMJIO_JIDU6611_R3.2.6").confirmed)
        assertFalse(checkCompatibility(qcom, "SRCMJIO_JIDU6611_R3.2.7").confirmed)
        assertFalse(checkCompatibility(mtk, "unknown").confirmed)
        assertFalse(checkCompatibility(RouterDevice("UNRECOGNIZED", "test", "board"),
            "UNKNOWN_R3.2.0").confirmed)
    }

    @Test fun onlyPrivateHttpsAddresses() {
        assertEquals("192.168.31.1", privateRouterAddress("https://192.168.31.1"))
        assertEquals("10.0.0.1", privateRouterAddress("https://10.0.0.1:443"))
        for (url in listOf("https://8.8.8.8", "http://192.168.31.1",
            "https://router.example", "https://192.168.31.1@bad.example", "https://192.168.31.999")) {
            try {
                privateRouterAddress(url)
                fail("Expected invalid LAN router URL: $url")
            } catch (_: RouterFailure) {}
        }
    }

    @Test fun certificatePinsAreScopedToRouterPort() {
        assertEquals("192.168.31.1:443", RouterTls.pinKey("https://192.168.31.1"))
        assertEquals("192.168.31.1:8443", RouterTls.pinKey("https://192.168.31.1:8443"))
    }

    @Test fun duplicateAdminLoginUsesDeviceFlagsFromPostLogin() {
        val device = routerDeviceFromFlags(
            emptyMap(),
            mapOf("DEVICE_MODEL" to "JIDU6611", "DEVICE_SYSTEM_NAME" to "Jio", "BOARD_NAME" to "board")
        )
        assertEquals("JIDU6611", device.model)
        assertEquals("qualcomm", device.family)
        assertEquals("Jio", device.vendor)
        assertEquals("board", device.board)
    }

    @Test fun flashPartitionsAreParsedWithSizes() {
        val parsed = partitions("""
            dev:    size   erasesize  name
            mtd0: 01000000 00020000 "spi"
            mtd7: 00200000 00020000 "MFG"
        """.trimIndent())
        assertEquals(2, parsed.size)
        assertEquals("mtd7_MFG.bin", parsed[1].filename)
        assertEquals(2L * 1024 * 1024, parsed[1].size)
    }

    @Test fun factoryKeyValueIsRecovered() {
        val blob = ("junk\u0000WiFi-SSID=AirFiber-TEST\n" +
            "WiFi-Password=test123456\n" +
            "device_model=JIDU6701\n").toByteArray(Charsets.ISO_8859_1)
        val data = extractFactory(blob)
        assertEquals("JIDU6701", data["device_model"])
        assertEquals("test123456", data["WiFi-Password"])
    }

    @Test fun asciiAndWideFactoryTablesRecoverCredentials() {
        for (wide in listOf(false, true)) {
            val fields = listOf("010", "RSABCDEF0123456", "I.DVS00A0000", "GxTEbl6DK6XiNsYr",
                "AirFiber-Test01", "2ue2n5p2P8npCpeC", "*q7:zn]E]X?]D4Y0", "0", "JIDU6401")
            val bytes = sampleTable(fields, wide)
            val data = extractFactory(bytes)
            assertEquals("JIDU6401", data["device_model"])
            assertEquals("AirFiber-Test01", data["WiFi-SSID"])
            assertEquals("2ue2n5p2P8npCpeC", data["WiFi-Password"])
            assertEquals("RSABCDEF0123456", data["sn"])
        }
    }

    private fun sampleTable(fields: List<String>, wide: Boolean): ByteArray {
        val scale = if (wide) 2 else 1
        val base = if (wide) 2 else 0
        val data = ByteArray(base + 0x40 * scale + fields.size * 32 * scale)
        if (wide) { data[0] = -1; data[1] = -2 }
        val magic = "mfg.data".toByteArray(if (wide) Charsets.UTF_16LE else Charsets.US_ASCII)
        magic.copyInto(data, base)
        val offset = base + 8 * scale
        ByteBuffer.wrap(data, offset, 4).order(ByteOrder.LITTLE_ENDIAN).putInt(fields.size)
        fields.forEachIndexed { index, text ->
            val encoded = text.toByteArray(if (wide) Charsets.UTF_16LE else Charsets.US_ASCII)
            encoded.copyInto(data, base + 0x40 * scale + index * 32 * scale)
        }
        return data
    }
}
