package com.remotetouch.app

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.util.Log
import android.view.accessibility.AccessibilityEvent

class TouchAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "TouchAccessibilitySvc"

        @Volatile
        var instance: TouchAccessibilityService? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "TouchAccessibilityService connected and ready.")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Không cần xử lý sự kiện UI vì dịch vụ chuyên nhận lệnh tọa độ từ PC
    }

    override fun onInterrupt() {
        Log.w(TAG, "TouchAccessibilityService interrupted.")
    }

    override fun onDestroy() {
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    /**
     * Thực hiện thao tác chạm đơn (TAP) tại tọa độ (x, y) trên màn hình thực.
     */
    fun performTap(x: Float, y: Float, durationMs: Long = 50L) {
        val safeX = x.coerceAtLeast(1f)
        val safeY = y.coerceAtLeast(1f)
        val safeDuration = durationMs.coerceIn(10L, 1000L)

        val path = Path().apply {
            moveTo(safeX, safeY)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0L, safeDuration)
        val gesture = GestureDescription.Builder()
            .addStroke(stroke)
            .build()

        dispatchGesture(gesture, null, null)
    }

    /**
     * Thực hiện thao tác vuốt kéo tâm (SWIPE) từ (x1, y1) đến (x2, y2) trong khoảng thời gian durationMs.
     */
    fun performSwipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long = 120L) {
        val safeX1 = x1.coerceAtLeast(1f)
        val safeY1 = y1.coerceAtLeast(1f)
        val safeX2 = x2.coerceAtLeast(1f)
        val safeY2 = y2.coerceAtLeast(1f)
        val safeDuration = durationMs.coerceIn(15L, 2000L)

        val path = Path().apply {
            moveTo(safeX1, safeY1)
            lineTo(safeX2, safeY2)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0L, safeDuration)
        val gesture = GestureDescription.Builder()
            .addStroke(stroke)
            .build()

        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                super.onCompleted(gestureDescription)
            }

            override fun onCancelled(gestureDescription: GestureDescription?) {
                super.onCancelled(gestureDescription)
                Log.w(TAG, "Swipe gesture cancelled")
            }
        }, null)
    }
}
