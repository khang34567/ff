package com.remotetouch.app

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.InputStreamReader
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

class ScreenCaptureService : Service() {

    companion object {
        private const val TAG = "ScreenCaptureService"
        private const val CHANNEL_ID = "RemoteTouchChannel"
        private const val NOTIFICATION_ID = 1001

        const val EXTRA_RESULT_CODE = "EXTRA_RESULT_CODE"
        const val EXTRA_RESULT_INTENT = "EXTRA_RESULT_INTENT"
        const val EXTRA_PC_IP = "EXTRA_PC_IP"
        const val EXTRA_PC_PORT = "EXTRA_PC_PORT"
        const val ACTION_STOP = "ACTION_STOP"

        @Volatile
        var isRunning: Boolean = false
            private set
    }

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var captureThread: HandlerThread? = null
    private var captureHandler: Handler? = null

    private val running = AtomicBoolean(false)
    private var socket: Socket? = null

    private var realScreenWidth = 720
    private var realScreenHeight = 1600
    private var captureWidth = 360
    private var captureHeight = 800
    private var screenDensity = 300

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelfCleanly()
            return START_NOT_STICKY
        }

        createNotificationChannel()
        val notification = buildNotification("Đang kết nối và truyền màn hình tới PC...")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
            ?: Activity.RESULT_CANCELED
        val resultData: Intent? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent?.getParcelableExtra(EXTRA_RESULT_INTENT, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent?.getParcelableExtra(EXTRA_RESULT_INTENT)
        }
        val pcIp = intent?.getStringExtra(EXTRA_PC_IP)?.trim() ?: ""
        val pcPort = intent?.getIntExtra(EXTRA_PC_PORT, 8888) ?: 8888

        if (resultData == null || pcIp.isEmpty()) {
            Log.e(TAG, "Missing MediaProjection permission data or PC IP.")
            stopSelfCleanly()
            return START_NOT_STICKY
        }

        initScreenMetrics()
        startCaptureAndSocket(resultCode, resultData, pcIp, pcPort)

        return START_STICKY
    }

    private fun initScreenMetrics() {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)

        realScreenWidth = metrics.widthPixels
        realScreenHeight = metrics.heightPixels
        screenDensity = metrics.densityDpi

        // Giảm 1/2 độ phân giải khi stream để đạt tốc độ khung hình mượt nhất trên Galaxy A02s
        captureWidth = (realScreenWidth / 2).coerceAtLeast(240)
        captureHeight = (realScreenHeight / 2).coerceAtLeast(400)
        // Đảm bảo kích thước chẵn
        if (captureWidth % 2 != 0) captureWidth++
        if (captureHeight % 2 != 0) captureHeight++
    }

    private fun startCaptureAndSocket(
        resultCode: Int,
        resultData: Intent,
        pcIp: String,
        pcPort: Int
    ) {
        if (running.getAndSet(true)) return
        isRunning = true

        captureThread = HandlerThread("CaptureThread").apply { start() }
        captureHandler = Handler(captureThread!!.looper)

        val projectionManager =
            getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = projectionManager.getMediaProjection(resultCode, resultData)

        mediaProjection?.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                stopSelfCleanly()
            }
        }, captureHandler)

        imageReader = ImageReader.newInstance(
            captureWidth,
            captureHeight,
            PixelFormat.RGBA_8888,
            2
        )

        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "RemoteTouchDisplay",
            captureWidth,
            captureHeight,
            screenDensity,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface,
            null,
            captureHandler
        )

        Thread({
            runSocketLoop(pcIp, pcPort)
        }, "TcpStreamThread").start()
    }

    private fun runSocketLoop(pcIp: String, pcPort: Int) {
        try {
            val client = Socket()
            client.tcpNoDelay = true
            client.connect(InetSocketAddress(pcIp, pcPort), 5000)
            socket = client

            // Luồng nhận lệnh điều khiển cảm ứng từ PC ("SWIPE,x1,y1,x2,y2,duration" hoặc "TAP,x,y")
            val readerThread = Thread({
                listenForCommands(client)
            }, "CommandReceiverThread")
            readerThread.isDaemon = true
            readerThread.start()

            val out = DataOutputStream(client.getOutputStream())
            val jpegStream = ByteArrayOutputStream(65536)

            while (running.get() && !client.isClosed) {
                val image = imageReader?.acquireLatestImage()
                if (image == null) {
                    Thread.sleep(15)
                    continue
                }

                var bitmap: Bitmap? = null
                var croppedBitmap: Bitmap? = null
                try {
                    val plane = image.planes[0]
                    val buffer = plane.buffer
                    val pixelStride = plane.pixelStride
                    val rowStride = plane.rowStride
                    val rowPadding = rowStride - pixelStride * captureWidth

                    val bufferWidth = captureWidth + rowPadding / pixelStride
                    bitmap = Bitmap.createBitmap(
                        bufferWidth,
                        captureHeight,
                        Bitmap.Config.ARGB_8888
                    )
                    bitmap.copyPixelsFromBuffer(buffer)

                    croppedBitmap = if (rowPadding > 0) {
                        Bitmap.createBitmap(bitmap, 0, 0, captureWidth, captureHeight)
                    } else {
                        bitmap
                    }

                    jpegStream.reset()
                    // Nén ảnh JPEG chất lượng 60% theo đúng yêu cầu
                    croppedBitmap.compress(Bitmap.CompressFormat.JPEG, 60, jpegStream)
                    val jpegBytes = jpegStream.toByteArray()

                    // Gửi 4 byte độ dài khung hình + dữ liệu ảnh JPEG qua TCP Socket
                    out.writeInt(jpegBytes.size)
                    out.write(jpegBytes)
                    out.flush()
                } finally {
                    if (croppedBitmap != null && croppedBitmap !== bitmap) {
                        croppedBitmap.recycle()
                    }
                    bitmap?.recycle()
                    image.close()
                }

                // Duy trì khoảng ~25-30 FPS ổn định
                Thread.sleep(25)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Socket loop error: ${e.message}", e)
        } finally {
            stopSelfCleanly()
        }
    }

    private fun listenForCommands(client: Socket) {
        val scaleX = realScreenWidth.toFloat() / captureWidth.toFloat()
        val scaleY = realScreenHeight.toFloat() / captureHeight.toFloat()

        try {
            val reader = BufferedReader(InputStreamReader(client.getInputStream(), Charsets.UTF_8))
            while (running.get() && !client.isClosed) {
                val line = reader.readLine() ?: break
                val parts = line.trim().split(",")
                if (parts.isEmpty()) continue

                val cmd = parts[0].uppercase()
                val touchService = TouchAccessibilityService.instance
                if (touchService == null) {
                    Log.w(TAG, "TouchAccessibilityService chưa được bật!")
                    continue
                }

                when (cmd) {
                    "SWIPE" -> {
                        if (parts.size >= 6) {
                            // Tọa độ gửi từ khung hình PC được quy đổi chính xác sang độ phân giải màn hình thật
                            val x1 = parts[1].toFloatOrNull()?.times(scaleX) ?: continue
                            val y1 = parts[2].toFloatOrNull()?.times(scaleY) ?: continue
                            val x2 = parts[3].toFloatOrNull()?.times(scaleX) ?: continue
                            val y2 = parts[4].toFloatOrNull()?.times(scaleY) ?: continue
                            val duration = parts[5].toLongOrNull() ?: 120L
                            touchService.performSwipe(x1, y1, x2, y2, duration)
                        }
                    }
                    "TAP" -> {
                        if (parts.size >= 3) {
                            val x = parts[1].toFloatOrNull()?.times(scaleX) ?: continue
                            val y = parts[2].toFloatOrNull()?.times(scaleY) ?: continue
                            val duration = if (parts.size >= 4) parts[3].toLongOrNull() ?: 50L else 50L
                            touchService.performTap(x, y, duration)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Command listener stopped: ${e.message}")
        }
    }

    private fun stopSelfCleanly() {
        if (!running.getAndSet(false) && !isRunning) return
        isRunning = false

        try {
            socket?.close()
        } catch (_: Exception) {}
        socket = null

        captureHandler?.post {
            try {
                virtualDisplay?.release()
            } catch (_: Exception) {}
            virtualDisplay = null

            try {
                imageReader?.close()
            } catch (_: Exception) {}
            imageReader = null

            try {
                mediaProjection?.stop()
            } catch (_: Exception) {}
            mediaProjection = null

            captureThread?.quitSafely()
            captureThread = null
        }

        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        stopSelfCleanly()
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "RemoteTouch Foreground Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Duy trì kết nối truyền màn hình và điều khiển cảm ứng"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(contentText: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java)
        val pendingFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, openIntent, pendingFlags)

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("RemoteTouch đang hoạt động")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }
}
