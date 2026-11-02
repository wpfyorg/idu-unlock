package com.jioidu.unlock

import android.content.ContentResolver
import android.net.Uri
import android.provider.DocumentsContract
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.Charset
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

internal data class FlashPart(val device: String, val size: Long, val name: String) {
    val filename get() = "${device}_${name.replace(Regex("[^A-Za-z0-9_.-]"), "_")}.bin"
}

internal fun partitions(raw: String): List<FlashPart> = raw.lineSequence().mapNotNull { line ->
    val m = Regex("""^(mtd\d+):\s+([a-fA-F0-9]+)\s+[a-fA-F0-9]+\s+"([^"]+)""")
        .find(line.trim()) ?: return@mapNotNull null
    val size = m.groupValues[2].toLongOrNull(16) ?: return@mapNotNull null
    FlashPart(m.groupValues[1], size, m.groupValues[3])
}.toList()

internal fun extractFactory(bytes: ByteArray): Map<String, String> {
    val data = linkedMapOf<String, String>()
    val latin = Charset.forName("ISO-8859-1")
    val binaryText = String(bytes, latin)
    val pairs = Regex("""([A-Za-z0-9_.-]{2,40})=([^\x00\r\n]{0,200})""")
    pairs.findAll(binaryText).forEach { match ->
        data.putIfAbsent(match.groupValues[1], match.groupValues[2])
    }
    if (data.containsKey("WiFi-SSID") || data.containsKey("device_model")) return data

    val wide = bytes.size > 20 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xFE.toByte()
    val magic = if (wide) "mfg.data".toByteArray(Charsets.UTF_16LE)
        else "mfg.data".toByteArray(Charsets.US_ASCII)
    val base = if (wide) 2 else 0
    val scale = if (wide) 2 else 1
    if (bytes.size >= base + magic.size &&
        bytes.copyOfRange(base, base + magic.size).contentEquals(magic)) {
        val countOffset = base + 8 * scale
        if (bytes.size > countOffset + 4) {
            val count = ByteBuffer.wrap(bytes, countOffset, 4).order(ByteOrder.LITTLE_ENDIAN).int
            val table = base + 0x40 * scale
            val slots = (0 until count.coerceIn(0, 128)).map { index ->
                val start = table + index * 32 * scale
                val end = start + 32 * scale
                if (end > bytes.size) "" else {
                    val slot = bytes.copyOfRange(start, end)
                    if (wide) String(slot, Charsets.UTF_16LE).substringBefore('\u0000')
                        .replace("\uFFFF", "").trim()
                    else String(slot, latin).substringBefore('\u0000').trim { it <= ' ' || it == '\u00FF' }
                }
            }
            var ssidIndex = -1
            slots.forEachIndexed { index, value ->
                if (value.isEmpty()) return@forEachIndexed
                when {
                    Regex("""JIDU\d{4}""").matches(value) -> data["device_model"] = value
                    Regex("RS[A-Z0-9]{10,}").matches(value) -> data.putIfAbsent("sn", value)
                    (value.startsWith("AirFiber") || value.startsWith("Jio")) &&
                        !data.containsKey("WiFi-SSID") -> {
                            data["WiFi-SSID"] = value
                            ssidIndex = index
                        }
                    else -> data["mfg_slot_$index"] = value
                }
            }
            if (ssidIndex >= 0 && ssidIndex + 1 < slots.size) {
                val key = slots[ssidIndex + 1]
                if (key.length in 8..63) {
                    data["WiFi-Password"] = key
                    data.remove("mfg_slot_${ssidIndex + 1}")
                }
            }
        }
    } else {
        val telpa = Regex("""R[ST][A-Z0-9]{13}""").find(binaryText)
        if (telpa != null) {
            data["sn"] = telpa.value
            fun fixed(start: Int, size: Int) = binaryText.substring(start.coerceAtMost(binaryText.length),
                (start + size).coerceAtMost(binaryText.length)).trim()
            val ssid = fixed(telpa.range.last + 1, 15)
            val key = fixed(telpa.range.last + 16, 16)
            if (ssid.isNotBlank()) data["WiFi-SSID"] = ssid
            if (key.length in 8..63) data["WiFi-Password"] = key
        }
    }
    if (!data.containsKey("device_model")) {
        Regex("""JIDU\d{4}""").find(binaryText)?.let { data["device_model"] = it.value }
        if (!data.containsKey("device_model") && wide) {
            Regex("""JIDU\d{4}""").find(String(bytes, Charsets.UTF_16LE))?.let {
                data["device_model"] = it.value
            }
        }
    }
    return data
}

/** Writes to a user-picked SAF folder. No storage permission or public temp files. */
internal class RouterBackup(
    private val resolver: ContentResolver,
    private val tree: Uri,
    private val log: (String) -> Unit
) {
    private val directoryMime = DocumentsContract.Document.MIME_TYPE_DIR

    private fun folder(parent: Uri, label: String): Uri =
        DocumentsContract.createDocument(resolver, parent, directoryMime, label)
            ?: throw RouterFailure("Cannot create backup folder; choose a writable location.")

    private fun write(parent: Uri, label: String, value: String) {
        val uri = DocumentsContract.createDocument(resolver, parent, "text/plain", label)
            ?: throw RouterFailure("Cannot write $label.")
        try {
            resolver.openOutputStream(uri, "w")?.use { it.write(value.toByteArray(Charsets.UTF_8)) }
                ?: throw IOException("No output stream")
        } catch (_: Exception) {
            DocumentsContract.deleteDocument(resolver, uri)
            throw RouterFailure("Could not write $label. Check free storage.")
        }
    }

    fun execute(ssh: RouterSsh, model: String): String {
        val raw = ssh.command("cat /proc/mtd")
        val parts = partitions(raw)
        val mfg = parts.firstOrNull { it.name.equals("MFG", ignoreCase = true) }
            ?: throw RouterFailure("Router has no identifiable MFG flash partition.")
        val mfgData = ssh.rawFile("/dev/${mfg.device}", maxOf(8L * 1024 * 1024, mfg.size + 4096))
        val fields = extractFactory(mfgData).toMutableMap()
        fields.putIfAbsent("device_model", model)
        val timestamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
        val name = "${model.replace(Regex("[^A-Za-z0-9-]"), "_")}_$timestamp"
        val treeRoot = DocumentsContract.buildDocumentUriUsingTree(
            tree, DocumentsContract.getTreeDocumentId(tree)
        )
        val root = folder(treeRoot, name)
        val images = folder(root, "backup")

        val names = listOf("WiFi-SSID", "WiFi-Password", "WiFi5-Password", "WiFi5-SSID",
            "uboot_user_name", "uboot_user_password", "web_user_name", "web_user_password",
            "acs_pre_password", "sn", "mac", "OUI", "hardware_version", "secure_boot",
            "factory_mode")
        val credentials = buildString {
            appendLine("# ${fields["device_model"] ?: model} factory data")
            names.forEach { appendLine("${it.padEnd(20)} = ${fields[it].orEmpty()}") }
            fields.toSortedMap().filterKeys { it.startsWith("mfg_slot_") }.forEach { (k, v) ->
                appendLine("${k.padEnd(20)} = $v")
            }
        }
        write(root, "credentials.txt", credentials)
        write(root, "uboot_credentials.env",
            "UBOOT_USERNAME=${fields["uboot_user_name"].orEmpty()}\n" +
                "UBOOT_PASSWORD=${fields["uboot_user_password"].orEmpty()}\n")
        write(root, "partitions.txt", raw)
        write(root, "uboot_env.txt", "### fw_printenv\n" +
            safeCommand(ssh, "fw_printenv 2>&1") + "\n### alternate environment\n" +
            safeCommand(ssh, "fw_printenv -c /etc/jio.config 2>&1"))
        write(root, "factory_env.txt", safeCommand(ssh, "strings /dev/${mfg.device} 2>/dev/null"))
        log("Saving ${parts.size} partitions to selected folder.")
        for (part in parts) {
            if (part.device == "mtd0") {
                log("Skipping mtd0 full-chip image (same default as CLI).")
                continue
            }
            val target = DocumentsContract.createDocument(
                resolver, images, "application/octet-stream", part.filename
            ) ?: throw RouterFailure("Could not create ${part.filename}.")
            try {
                resolver.openOutputStream(target, "w")?.use { stream ->
                    if (part.device == mfg.device) {
                        stream.write(mfgData)
                    } else {
                        ssh.download(part.device, stream, part.size) { received ->
                            log("${part.name}: ${received / (1024 * 1024)} / ${part.size / (1024 * 1024)} MiB")
                        }
                    }
                } ?: throw IOException("No output stream")
            } catch (ex: Exception) {
                try { DocumentsContract.deleteDocument(resolver, target) } catch (_: Exception) {}
                if (ex is RouterFailure) throw ex
                throw RouterFailure("Backup of ${part.name} failed. Verify storage and router connectivity.")
            }
            log("Saved ${part.name}.")
        }
        return name
    }

    private fun safeCommand(ssh: RouterSsh, text: String): String =
        try { ssh.command(text) } catch (_: Exception) { "(unavailable)\n" }
}
