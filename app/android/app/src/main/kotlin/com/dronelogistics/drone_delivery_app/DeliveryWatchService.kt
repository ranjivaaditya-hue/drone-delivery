package com.dronelogistics.drone_delivery_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Foreground service that runs while a delivery is in progress.
 *
 * Every few seconds it asks the PC backend for the current delivery state.
 * On each state change it posts a notification ("Drone has taken off",
 * "Package delivered", ...). It keeps working when the app is in the
 * background or swiped away, and it needs no Firebase. It stops itself once
 * the delivery is COMPLETED or CANCELLED.
 *
 * Duplicate guard: the last notified "deliveryId:state" is saved in
 * SharedPreferences, so a restart never posts the same update twice.
 */
class DeliveryWatchService : Service() {
    private val executor = Executors.newSingleThreadScheduledExecutor()
    private var task: ScheduledFuture<*>? = null
    @Volatile private var serverUrl = ""
    private var failures = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannels(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTracking()
            return START_NOT_STICKY
        }
        val url = intent?.getStringExtra(EXTRA_URL) ?: prefs().getString(KEY_URL, null)
        if (url.isNullOrBlank()) {
            stopSelf()
            return START_NOT_STICKY
        }
        serverUrl = url.trimEnd('/')
        prefs().edit().putString(KEY_URL, serverUrl).apply()
        goForeground(ongoing(getString(R.string.tracking_title), getString(R.string.tracking_waiting)))
        if (task == null) {
            task = executor.scheduleWithFixedDelay({ pollSafely() }, 0, POLL_SECONDS, TimeUnit.SECONDS)
        }
        return START_STICKY
    }

    private fun goForeground(n: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(ONGOING_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(ONGOING_ID, n)
        }
    }

    private fun pollSafely() {
        try {
            poll()
        } catch (t: Throwable) {
            Log.w(TAG, "poll failed", t)
        }
    }

    private fun poll() {
        val body = httpGet("$serverUrl/api/deliveries/current")
        if (body == null) {
            failures++
            if (failures == 3) notify(ONGOING_ID, ongoing(getString(R.string.tracking_title), getString(R.string.tracking_offline)))
            return
        }
        failures = 0
        val d = JSONObject(body).optJSONObject("delivery") ?: return
        val id = d.getString("delivery_id")
        val status = d.getString("status")
        val n = d.getJSONObject("notification")
        val title = n.getString("title")
        val text = n.getString("body")
        val key = "$id:$status"

        val prefs = prefs()
        val lastId = prefs.getString(KEY_LAST_ID, null)
        val lastKey = prefs.getString(KEY_LAST_KEY, null)
        // The first time a delivery is seen, its current state is the baseline (the app is
        // showing it already). Notify only on later changes.
        if (lastId == id && lastKey != key) postUpdate(id, title, text)
        prefs.edit().putString(KEY_LAST_ID, id).putString(KEY_LAST_KEY, key).apply()

        if (status == "COMPLETED" || status == "CANCELLED") {
            stopTracking()
        } else {
            notify(ONGOING_ID, ongoing(title, "$id · Package ${d.optString("package_id")}"))
        }
    }

    private fun postUpdate(deliveryId: String, title: String, text: String) {
        val b = builder(CHANNEL_UPDATES)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setSubText(deliveryId)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent())
        @Suppress("DEPRECATION")
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) b.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL)
        notify(UPDATE_ID_BASE + (deliveryId.hashCode() and 0xFFFF), b.build())
    }

    private fun ongoing(title: String, text: String): Notification {
        val stop = PendingIntent.getService(
            this, 1, Intent(this, DeliveryWatchService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return builder(CHANNEL_TRACKING)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openAppIntent())
            .addAction(Notification.Action.Builder(null, getString(R.string.tracking_stop), stop).build())
            .build()
    }

    private fun builder(channel: String): Notification.Builder {
        @Suppress("DEPRECATION")
        val b = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, channel) else Notification.Builder(this)
        return b.setSmallIcon(R.drawable.ic_stat_drone).setColor(BRAND_COLOR).setShowWhen(true)
    }

    private fun openAppIntent(): PendingIntent = PendingIntent.getActivity(
        this, 0,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun notify(id: Int, n: Notification) {
        try {
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify(id, n)
        } catch (e: SecurityException) {
            Log.w(TAG, "notification permission missing", e) // Android 13+ without POST_NOTIFICATIONS
        }
    }

    private fun stopTracking() {
        task?.cancel(false)
        task = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    /** Android 15+: a dataSync foreground service has a daily time budget. Stop cleanly when it runs out. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        stopTracking()
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun prefs(): SharedPreferences = getSharedPreferences("delivery_watch", Context.MODE_PRIVATE)

    private fun httpGet(url: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 4000
            conn.readTimeout = 4000
            if (conn.responseCode == 200) conn.inputStream.bufferedReader().use { it.readText() } else null
        } catch (e: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val TAG = "DeliveryWatch"
        private const val EXTRA_URL = "server_url"
        private const val ACTION_STOP = "com.dronelogistics.STOP_TRACKING"
        private const val KEY_URL = "server_url"
        private const val KEY_LAST_ID = "last_delivery_id"
        private const val KEY_LAST_KEY = "last_notified"
        private const val CHANNEL_UPDATES = "delivery_updates"
        private const val CHANNEL_TRACKING = "delivery_tracking"
        private const val ONGOING_ID = 1001
        private const val UPDATE_ID_BASE = 2000
        private const val POLL_SECONDS = 3L
        private const val BRAND_COLOR = 0xFF4F46E5.toInt()

        fun start(context: Context, serverUrl: String) {
            val intent = Intent(context, DeliveryWatchService::class.java).putExtra(EXTRA_URL, serverUrl)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent) else context.startService(intent)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, DeliveryWatchService::class.java).setAction(ACTION_STOP))
        }

        fun createChannels(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_UPDATES, context.getString(R.string.channel_updates), NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = context.getString(R.string.channel_updates_desc) },
            )
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_TRACKING, context.getString(R.string.channel_tracking), NotificationManager.IMPORTANCE_LOW)
                    .apply { description = context.getString(R.string.channel_tracking_desc) },
            )
        }
    }
}
