package com.remotetouch.app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    companion object {
        private const val REQUEST_MEDIA_PROJECTION = 2001
        private const val PREFS_NAME = "RemoteTouchPrefs"
        private const val KEY_LAST_IP = "last_pc_ip"
    }

    private lateinit var tvAccessStatus: TextView
    private lateinit var tvProjectionStatus: TextView
    private lateinit var tvConnectionStatus: TextView
    private lateinit var btnAccessibility: Button
    private lateinit var btnScreenCapture: Button
    private lateinit var btnConnect: Button
    private lateinit var etPcIp: EditText

    private var mediaProjectionResultCode: Int = Activity.RESULT_CANCELED
    private var mediaProjectionResultData: Intent? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvAccessStatus = findViewById(R.id.tvAccessStatus)
        tvProjectionStatus = findViewById(R.id.tvProjectionStatus)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        btnAccessibility = findViewById(R.id.btnAccessibility)
        btnScreenCapture = findViewById(R.id.btnScreenCapture)
        btnConnect = findViewById(R.id.btnConnect)
        etPcIp = findViewById(R.id.etPcIp)

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        etPcIp.setText(prefs.getString(KEY_LAST_IP, "192.168.1."))

        // Nút 1: Cấp quyền Trợ năng (Accessibility)
        btnAccessibility.setOnClickListener {
            val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            startActivity(intent)
            Toast.makeText(
                this,
                "Hãy tìm 'RemoteTouch Auto Gesture' và BẬT công tắc cấp quyền!",
                Toast.LENGTH_LONG
            ).show()
        }

        // Nút 2: Cấp quyền Chụp màn hình (MediaProjection)
        btnScreenCapture.setOnClickListener {
            val projectionManager =
                getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            @Suppress("DEPRECATION")
            startActivityForResult(
                projectionManager.createScreenCaptureIntent(),
                REQUEST_MEDIA_PROJECTION
            )
        }

        // Nút 3: Kết nối tới PC (Port 8888)
        btnConnect.setOnClickListener {
            if (ScreenCaptureService.isRunning) {
                val stopIntent = Intent(this, ScreenCaptureService::class.java).apply {
                    action = ScreenCaptureService.ACTION_STOP
                }
                startService(stopIntent)
                tvConnectionStatus.text = "Nhật ký: Đã ngắt kết nối với PC."
                btnConnect.text = "3. Kết nối tới PC (Port 8888)"
                return@setOnClickListener
            }

            if (!isAccessibilityEnabled()) {
                Toast.makeText(
                    this,
                    "Vui lòng cấp quyền Trợ năng (Bước 1) trước!",
                    Toast.LENGTH_SHORT
                ).show()
                return@setOnClickListener
            }

            if (mediaProjectionResultCode != Activity.RESULT_OK || mediaProjectionResultData == null) {
                Toast.makeText(
                    this,
                    "Vui lòng bấm '2. Cấp quyền Chụp màn hình' trước!",
                    Toast.LENGTH_SHORT
                ).show()
                return@setOnClickListener
            }

            val ip = etPcIp.text.toString().trim()
            if (ip.isEmpty()) {
                Toast.makeText(this, "Vui lòng nhập địa chỉ IP của PC!", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            prefs.edit().putString(KEY_LAST_IP, ip).apply()

            val serviceIntent = Intent(this, ScreenCaptureService::class.java).apply {
                putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, mediaProjectionResultCode)
                putExtra(ScreenCaptureService.EXTRA_RESULT_INTENT, mediaProjectionResultData)
                putExtra(ScreenCaptureService.EXTRA_PC_IP, ip)
                putExtra(ScreenCaptureService.EXTRA_PC_PORT, 8888)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent)
            } else {
                startService(serviceIntent)
            }

            tvConnectionStatus.text =
                "Nhật ký: Đang chạy ForegroundService và kết nối tới $ip:8888...
Bạn có thể ẩn ứng dụng và mở trò chơi."
            btnConnect.text = "Ngắt kết nối PC"
        }
    }

    override fun onResume() {
        super.onResume()
        updateUiStatus()
    }

    private fun updateUiStatus() {
        if (isAccessibilityEnabled()) {
            tvAccessStatus.text = "Trạng thái Trợ năng: ĐÃ BẬT (Sẵn sàng)"
            tvAccessStatus.setTextColor(Color.parseColor("#34D399"))
        } else {
            tvAccessStatus.text = "Trạng thái Trợ năng: CHƯA BẬT"
            tvAccessStatus.setTextColor(Color.parseColor("#F87171"))
        }

        if (mediaProjectionResultCode == Activity.RESULT_OK && mediaProjectionResultData != null) {
            tvProjectionStatus.text = "Trạng thái Chụp màn hình: ĐÃ CẤP QUYỀN"
            tvProjectionStatus.setTextColor(Color.parseColor("#34D399"))
        } else {
            tvProjectionStatus.text = "Trạng thái Chụp màn hình: Chưa cấp quyền"
            tvProjectionStatus.setTextColor(Color.parseColor("#FBBF24"))
        }

        if (ScreenCaptureService.isRunning) {
            btnConnect.text = "Ngắt kết nối PC"
        } else {
            btnConnect.text = "3. Kết nối tới PC (Port 8888)"
        }
    }

    private fun isAccessibilityEnabled(): Boolean {
        if (TouchAccessibilityService.instance != null) return true
        val expectedComponent = "$packageName/${TouchAccessibilityService::class.java.canonicalName}"
        val enabledServices = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        return enabledServices.contains(expectedComponent)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_MEDIA_PROJECTION) {
            if (resultCode == Activity.RESULT_OK && data != null) {
                mediaProjectionResultCode = resultCode
                mediaProjectionResultData = data
                updateUiStatus()
                tvConnectionStatus.text =
                    "Nhật ký: Đã cấp quyền chụp màn hình thành công. Hãy nhập IP PC và bấm nút 3."
            } else {
                Toast.makeText(this, "Bạn đã từ chối quyền chụp màn hình.", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
