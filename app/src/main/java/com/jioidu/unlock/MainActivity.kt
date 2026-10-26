package com.jioidu.unlock

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.method.ScrollingMovementMethod
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var routerUrl: EditText
    private lateinit var adminPassword: EditText
    private lateinit var status: TextView
    private lateinit var logView: TextView
    private lateinit var progress: ProgressBar
    private lateinit var actionButtons: List<Button>
    private var busy = false
    private var pendingBackupConfirmation = false
    private var backupTree: Uri? = null
    @Volatile private var pendingCertificateLatch: CountDownLatch? = null
    private var certificateDialog: AlertDialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        routerUrl = findViewById(R.id.router_url)
        adminPassword = findViewById(R.id.admin_password)
        status = findViewById(R.id.status_text)
        logView = findViewById(R.id.log_text)
        progress = findViewById(R.id.progress)
        logView.movementMethod = ScrollingMovementMethod()
        actionButtons = listOf(
            findViewById(R.id.detect_button),
            findViewById(R.id.check_button),
            findViewById(R.id.unlock_button),
            findViewById(R.id.backup_button),
        )

        findViewById<Button>(R.id.detect_button).setOnClickListener { startAction(RouterAction.DETECT) }
        findViewById<Button>(R.id.check_button).setOnClickListener { startAction(RouterAction.CHECK) }
        findViewById<Button>(R.id.unlock_button).setOnClickListener { startAction(RouterAction.UNLOCK) }
        findViewById<Button>(R.id.backup_button).setOnClickListener { confirmBackup() }
    }

    private fun confirmBackup() {
        AlertDialog.Builder(this)
            .setTitle("Choose private backup folder")
            .setMessage(
                "Only continue on a router you own or are authorized to access. " +
                    "Backup reads factory credentials and flash partitions. Root SSH must " +
                    "already be enabled; this app does not unlock the router. Store the files " +
                    "somewhere private."
            )
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Choose folder") { _, _ -> openBackupFolderPicker() }
            .show()
    }

    private fun openBackupFolderPicker() {
        pendingBackupConfirmation = true
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            )
        }
        @Suppress("DEPRECATION")
        startActivityForResult(intent, REQUEST_BACKUP_FOLDER)
    }

    @Deprecated("Uses ACTION_OPEN_DOCUMENT_TREE for API 26 compatibility")
    @SuppressLint("WrongConstant") // The picker supplies grant bits at runtime; mask to the two supported flags.
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_BACKUP_FOLDER) return
        val uri = if (resultCode == RESULT_OK) data?.data else null
        if (uri == null) {
            pendingBackupConfirmation = false
            status.text = "Backup cancelled: no folder selected"
            return
        }
        val grantFlags = (data?.flags ?: 0) and
            (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        if (grantFlags != 0) {
            try {
                contentResolver.takePersistableUriPermission(uri, grantFlags)
            } catch (_: SecurityException) {
                // A one-session grant can still be used for this backup operation.
            }
        }
        backupTree = uri
        if (pendingBackupConfirmation) {
            pendingBackupConfirmation = false
            startAction(RouterAction.BACKUP)
        }
    }

    private fun startAction(action: RouterAction) {
        if (busy) return
        val url = routerUrl.text.toString().trim()
        val password = adminPassword.text.toString()
        if (url.isBlank() && action != RouterAction.UNLOCK) {
            showInputError("Enter the router URL.")
            return
        }
        if (password.isBlank() && action != RouterAction.UNLOCK) {
            showInputError("Enter the router admin password.")
            return
        }
        if (action == RouterAction.BACKUP && backupTree == null) {
            showInputError("Choose a backup folder first.")
            return
        }

        val guidanceOnly = action == RouterAction.UNLOCK
        setBusy(true, if (guidanceOnly) "Preparing unlock guidance…" else "Running ${action.name.lowercase()}…")
        appendLog(if (guidanceOnly) "\nUnlock guidance requested (no router changes)" else
            "\n${action.name.lowercase().replaceFirstChar { it.uppercase() }} started")
        val destination = if (action == RouterAction.BACKUP) backupTree else null
        worker.execute {
            try {
                val engine = RouterEngine(applicationContext)
                val result = engine.run(action, url, password, destination,
                    confirmCertificate = ::confirmCertificate,
                    confirmSshHostKey = ::confirmSshHostKey) { line ->
                    mainHandler.post { appendLog(sanitize(line, password)) }
                }
                mainHandler.post {
                    appendLog(sanitize(result.summary, password))
                    if (result.details.isNotBlank()) appendLog(sanitize(result.details, password))
                    adminPassword.text?.clear()
                    setBusy(false, if (guidanceOnly) "Unlock guidance ready" else
                        result.summary.ifBlank { "${action.name.lowercase()} complete" })
                    if (guidanceOnly && !isFinishing && !isDestroyed) {
                        val instructions = listOf(result.summary, result.details)
                            .filter { it.isNotBlank() }
                            .joinToString("\n\n")
                        AlertDialog.Builder(this@MainActivity)
                            .setTitle("Unlock guidance")
                            .setMessage(sanitize(instructions.ifBlank { "No guidance is available." }, password))
                            .setPositiveButton("Done", null)
                            .show()
                    }
                }
            } catch (problem: Exception) {
                val safeMessage = sanitize(problem.message ?: problem.javaClass.simpleName, password)
                mainHandler.post {
                    appendLog("Error: $safeMessage")
                    adminPassword.text?.clear()
                    setBusy(false, "${action.name.lowercase().replaceFirstChar { it.uppercase() }} failed")
                }
            }
        }
    }

    /** Pause the worker until the user verifies the first certificate out of band. */
    private fun confirmCertificate(host: String, fingerprint: String): Boolean {
        return confirmIdentity(
            "Verify router certificate",
            "Router: $host\n\nSHA-256:\n$fingerprint\n\n" +
                "Compare this fingerprint with a trusted source independent of this network. " +
                "The app sends no password until you confirm. A mismatch can expose your router credentials."
        )
    }

    private fun confirmSshHostKey(message: String): Boolean =
        confirmIdentity(
            "Verify SSH host key",
            "$message\n\nCompare the fingerprint with a trusted source independent of this network. " +
                "Backup stops if the SSH host key changes."
        )

    private fun confirmIdentity(title: String, message: String): Boolean {
        val answer = AtomicBoolean(false)
        val latch = CountDownLatch(1)
        pendingCertificateLatch = latch
        mainHandler.post {
            if (isFinishing || isDestroyed) {
                latch.countDown()
                return@post
            }
            certificateDialog = AlertDialog.Builder(this)
                .setTitle(title)
                .setMessage(message)
                .setNegativeButton("Cancel") { _, _ -> latch.countDown() }
                .setPositiveButton("I verified it") { _, _ -> answer.set(true); latch.countDown() }
                .setOnCancelListener { latch.countDown() }
                .setOnDismissListener {
                    latch.countDown()
                    certificateDialog = null
                }
                .show()
        }
        val verified = try {
            val completed = latch.await(5, TimeUnit.MINUTES)
            if (!completed) mainHandler.post { certificateDialog?.dismiss() }
            completed && answer.get()
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            mainHandler.post { certificateDialog?.dismiss() }
            false
        }
        if (pendingCertificateLatch === latch) pendingCertificateLatch = null
        return verified
    }

    private fun setBusy(value: Boolean, message: String) {
        busy = value
        status.text = message
        progress.visibility = if (value) ProgressBar.VISIBLE else ProgressBar.GONE
        actionButtons.forEach { it.isEnabled = !value }
    }

    private fun appendLog(raw: String) {
        val current = logView.text.toString().let { if (it == "No activity yet.") "" else it }
        val combined = (current + raw.trimEnd() + "\n").lines().takeLast(MAX_LOG_LINES).joinToString("\n")
        logView.text = combined
        logView.post {
            val layout = logView.layout ?: return@post
            val scroll = layout.getLineTop(logView.lineCount) - logView.height
            if (scroll > 0) logView.scrollTo(0, scroll) else logView.scrollTo(0, 0)
        }
    }

    private fun sanitize(value: String, password: String): String {
        var safe = if (password.isNotEmpty()) value.replace(password, "[redacted]") else value
        safe = CREDENTIAL_ASSIGNMENT.replace(safe) { match -> "${match.groupValues[1]}[redacted]" }
        return safe
    }

    private fun showInputError(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("OK", null).show()
    }

    override fun onDestroy() {
        certificateDialog?.dismiss()
        certificateDialog = null
        pendingCertificateLatch?.countDown()
        pendingCertificateLatch = null
        super.onDestroy()
        // Do not interrupt an in-flight router operation during Activity teardown.
        worker.shutdown()
    }

    companion object {
        private const val REQUEST_BACKUP_FOLDER = 4107
        private const val MAX_LOG_LINES = 120
        private val CREDENTIAL_ASSIGNMENT = Regex(
            "(?im)(\\b(?:WiFi(?:5)?-Password|uboot_user_password|web_user_password|acs_pre_password)\\s*=\\s*).+"
        )
    }
}
