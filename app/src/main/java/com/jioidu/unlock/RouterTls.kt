package com.jioidu.unlock

import java.net.URI
import java.net.URL
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSession
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** TLS certificate pinning for routers with self-signed certificates. */
internal object RouterTls {
    fun pinKey(baseUrl: String): String {
        val uri = URI(baseUrl.trim())
        val port = uri.port.takeIf { it != -1 } ?: 443
        return "${uri.host}:$port"
    }

    /** Read the certificate only. This connection sends no router credentials. */
    fun fingerprint(baseUrl: String): String {
        val host = privateRouterAddress(baseUrl)
        val connection = URL(baseUrl.trim().trimEnd('/') + "/").openConnection() as HttpsURLConnection
        connection.sslSocketFactory = probeSocketFactory()
        connection.hostnameVerifier = HostnameVerifier { hostname, _ -> hostname == host }
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 15_000
        connection.readTimeout = 15_000
        return try {
            connection.connect()
            val certificate = connection.serverCertificates.firstOrNull() as? X509Certificate
                ?: throw RouterFailure("Router did not provide an X.509 certificate.")
            certificate.fingerprint()
        } catch (failure: RouterFailure) {
            throw failure
        } catch (_: Exception) {
            throw RouterFailure("Could not read the router certificate. No password was sent.")
        } finally {
            connection.disconnect()
        }
    }

    fun pinnedSocketFactory(host: String, pin: String) = pinnedContext(host, pin).socketFactory

    fun pinnedHostnameVerifier(host: String, pin: String) = HostnameVerifier { name, session ->
        name == host && session.hasPinnedCertificate(pin)
    }

    private fun probeSocketFactory() = SSLContext.getInstance("TLS").apply {
        init(null, arrayOf<TrustManager>(object : X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            // This untrusted certificate is used only to display a fingerprint; the
            // user must verify it independently before any credential request.
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                if (chain.isEmpty()) throw CertificateException("Missing server certificate")
            }
        }), null)
    }.socketFactory

    private fun pinnedContext(host: String, pin: String) = SSLContext.getInstance("TLS").apply {
        init(null, arrayOf<TrustManager>(object : X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                if (chain.firstOrNull()?.fingerprint() != pin) {
                    throw CertificateException("Router certificate pin mismatch for $host")
                }
            }
        }), null)
    }

    private fun SSLSession.hasPinnedCertificate(pin: String): Boolean = try {
        (peerCertificates.firstOrNull() as? X509Certificate)?.fingerprint() == pin
    } catch (_: Exception) {
        false
    }

    private fun X509Certificate.fingerprint(): String =
        MessageDigest.getInstance("SHA-256").digest(encoded)
            .joinToString("") { "%02X".format(it) }
}
