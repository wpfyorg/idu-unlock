package com.jioidu.unlock

import org.json.JSONObject
import java.io.Closeable
import java.net.Inet4Address
import java.net.InetAddress
import java.net.URI
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import javax.net.ssl.HttpsURLConnection

internal class RouterFailure(message: String) : Exception(message)

internal data class RouterDevice(
    val model: String,
    val vendor: String,
    val board: String
) {
    val family: String get() = when (model) {
        "JIDU6101", "JIDU6201", "JIDU6401", "JIDU6601", "JIDU6701" -> "mediatek"
        "JIDU6111", "JIDU6411", "JIDU6611", "JIDU6811", "JIDU6911" -> "qualcomm"
        else -> "unknown"
    }
}

internal data class Compatibility(val firmware: String, val message: String, val confirmed: Boolean)

internal fun routerDeviceFromFlags(
    loginFlags: Map<String, String>,
    postLoginFlags: Map<String, String>?
): RouterDevice {
    val flags = postLoginFlags ?: loginFlags
    return RouterDevice(
        flags["DEVICE_MODEL"] ?: "unknown",
        flags["DEVICE_SYSTEM_NAME"] ?: "?",
        flags["BOARD_NAME"] ?: "?"
    )
}

internal fun checkCompatibility(device: RouterDevice, firmware: String): Compatibility {
    val version = Regex("""_R(\d+(?:\.\d+)+)""").find(firmware)?.groupValues?.get(1)
    val values = version?.split('.')?.mapNotNull { it.toIntOrNull() }
    val limit = if (device.family == "qualcomm") listOf(3, 2, 6) else listOf(3, 2, 0)
    val confirmed = device.family != "unknown" && values != null && compareRelease(values, limit) <= 0
    val label = "R" + limit.joinToString(".")
    val verdict = if (confirmed) {
        "YES — tested firmware range (≤$label, ${device.family})"
    } else {
        "TEST — compatibility unconfirmed for ${firmware.ifBlank { "unknown firmware" }}"
    }
    return Compatibility(firmware, verdict, confirmed)
}

private fun compareRelease(a: List<Int>, b: List<Int>): Int {
    for (i in 0 until maxOf(a.size, b.size)) {
        val diff = (a.getOrElse(i) { 0 }).compareTo(b.getOrElse(i) { 0 })
        if (diff != 0) return diff
    }
    return 0
}

internal fun privateRouterAddress(value: String): String {
    val uri = try { URI(value.trim()) } catch (_: Exception) { throw RouterFailure("Enter a valid router HTTPS URL.") }
    if (uri.scheme != "https" || uri.userInfo != null || uri.host == null || uri.query != null ||
        uri.fragment != null || (uri.path != null && uri.path != "" && uri.path != "/")) {
        throw RouterFailure("Enter an HTTPS URL with a private IPv4 router address.")
    }
    val host = uri.host
    if (!Regex("""\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}""").matches(host)) {
        throw RouterFailure("Use the router's numeric private IPv4 address (such as 192.168.31.1).")
    }
    val octets = host.split('.').map { it.toIntOrNull() ?: -1 }
    if (octets.any { it !in 0..255 }) throw RouterFailure("Invalid router IPv4 address.")
    val address = InetAddress.getByAddress(octets.map { it.toByte() }.toByteArray())
    if (address !is Inet4Address || !address.isSiteLocalAddress) {
        throw RouterFailure("The router must have a private LAN IPv4 address.")
    }
    if (uri.port == 0 || uri.port > 65535 || uri.port < -1) throw RouterFailure("Invalid HTTPS port.")
    return host
}

internal class RouterApi(private val baseUrl: String, private val certificatePin: String) : Closeable {
    val host = privateRouterAddress(baseUrl)
    private var token: String? = null
    private var sessionCookie: String? = null
    private val rng = SecureRandom()
    private val rpcUrl = URL(baseUrl.trim().trimEnd('/') + "/WCGI")

    fun call(method: String, params: JSONObject = JSONObject()): JSONObject {
        val connection = rpcUrl.openConnection() as HttpsURLConnection
        connection.sslSocketFactory = RouterTls.pinnedSocketFactory(host, certificatePin)
        connection.hostnameVerifier = RouterTls.pinnedHostnameVerifier(host, certificatePin)
        connection.instanceFollowRedirects = false
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.connectTimeout = 15_000
        connection.readTimeout = 20_000
        connection.setRequestProperty("Content-Type", "application/json")
        token?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
        sessionCookie?.let { connection.setRequestProperty("Cookie", "sysauth=$it") }
        val payload = JSONObject().apply {
            put("id", rng.nextInt().toUInt().toString(16))
            put("method", method)
            put("params", params)
        }
        return try {
            connection.outputStream.use { it.write(payload.toString().toByteArray(StandardCharsets.UTF_8)) }
            // The firmware sets sysauth with an invalid cookie Path, so preserve it
            // manually rather than relying on CookieManager.
            connection.headerFields.entries
                .firstOrNull { it.key.equals("Set-Cookie", ignoreCase = true) }
                ?.value?.firstNotNullOfOrNull { header ->
                Regex("""sysauth=([^;,\s]+)""").find(header)?.groupValues?.get(1)
            }?.let { sessionCookie = it }
            val code = connection.responseCode
            val text = (if (code in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""
            JSONObject(text)
        } catch (ex: Exception) {
            // Avoid including request contents, admin password or bearer values in errors.
            throw RouterFailure("$method failed: router unreachable or returned an invalid response.")
        } finally {
            connection.disconnect()
        }
    }

    private fun isOk(response: JSONObject): Boolean =
        response.optString("status") == "OK" || response.optString("code").startsWith("OK_") ||
            response.optString("code") == "OK"

    fun connect(password: String): RouterDevice {
        call("preLogin")
        val reply = call("login", JSONObject().put("username", "admin").put("password", password))
        var post: JSONObject? = null
        if (!isOk(reply)) {
            if (reply.optString("code") == "ERR_LOGIN_DUPLICATE_ADMIN") {
                val held = reply.optJSONObject("results") ?: JSONObject()
                val bearer = held.optString("token").substringBefore("-")
                val loggedId = held.optString("loggedId")
                if (bearer.isBlank() || loggedId.isBlank()) {
                    throw RouterFailure("Another admin session is open. Log out of the router web UI.")
                }
                token = bearer
                post = call("postLogin", JSONObject()
                    .put("loggedId", loggedId).put("authHeader", "Bearer $bearer"))
            } else {
                val code = reply.optString("code")
                val message = when (code) {
                    "ERR_LOGIN_CREDENTIALS_FAIL" -> "Router rejected the admin password. Avoid repeated retries."
                    else -> "Router login failed: $code"
                }
                throw RouterFailure(message)
            }
        }
        val results = reply.optJSONObject("results") ?: JSONObject()
        if (token == null) {
            val combined = results.optString("token")
            if (combined.isBlank()) throw RouterFailure("Login returned no session token.")
            token = combined.substringBefore("-")
            if (combined.contains("-")) sessionCookie = combined.substringAfter("-", "")
        }
        if (post == null) post = call("postLogin")
        if (post.optString("code") == "ERR_POSTLOGIN_FACTORY_RESET") {
            throw RouterFailure("Finish the router setup wizard in the browser before using this app.")
        }
        if (!isOk(post)) throw RouterFailure("Router postLogin failed: ${post.optString("code")}")
        val loginFlags = results.optJSONObject("deviceFlags")?.stringMap() ?: emptyMap()
        val postLoginFlags = post.optJSONObject("results")?.optJSONObject("deviceFlags")?.stringMap()
        return routerDeviceFromFlags(loginFlags, postLoginFlags)
    }

    private fun JSONObject.stringMap(): Map<String, String> = buildMap {
        put("DEVICE_MODEL", optString("DEVICE_MODEL", "unknown"))
        put("DEVICE_SYSTEM_NAME", optString("DEVICE_SYSTEM_NAME", "?"))
        put("BOARD_NAME", optString("BOARD_NAME", "?"))
    }

    fun firmware(): String {
        val reply = call("getFirmwareDetails")
        return (reply.optJSONObject("results") ?: JSONObject()).optString("firmwareVersion")
    }

    override fun close() {
        if (token != null) try { call("logout") } catch (_: Exception) { }
        token = null
        sessionCookie = null
    }
}
