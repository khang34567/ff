#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC_Controller.py - Hệ thống nhận luồng màn hình Android & Tự động vuốt tâm (Auto-Swipe)
Giao thức: TCP Socket (Port 8888) - Không dùng ADB
Đóng gói EXE: pyinstaller --onefile --noconsole --name PC_Controller PC_Controller.py
"""

import socket
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk


def get_local_lan_ip() -> str:
    """Lấy địa chỉ IP LAN hiện tại của máy tính Windows."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def detect_red_center_hsv(frame_bgr: np.ndarray, roi_size: int = 30, offset_x: int = 0, offset_y: int = 0):
    """
    Quét vùng trung tâm khung hình (mặc định 30x30 pixel ngay giữa tâm màn hình)
    trong hệ màu HSV để nhận diện màu đỏ (khi tâm ngắm chuyển sang đỏ).
    Trả về: (red_ratio_percent, (x1_box, y1_box, x2_box, y2_box), mask)
    """
    h, w = frame_bgr.shape[:2]
    cx = int(np.clip(w // 2 + offset_x, roi_size // 2, max(roi_size // 2, w - roi_size // 2)))
    cy = int(np.clip(h // 2 + offset_y, roi_size // 2, max(roi_size // 2, h - roi_size // 2)))

    half = roi_size // 2
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(w, x1 + roi_size)
    y2 = min(h, y1 + roi_size)

    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0, (x1, y1, x2, y2), None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Dải màu đỏ trong không gian HSV của OpenCV (H: 0..10 và 160..180)
    lower_red1 = np.array([0, 110, 110], dtype=np.uint8)
    upper_red1 = np.array([10, 255, 255], dtype=np.uint8)
    lower_red2 = np.array([160, 110, 110], dtype=np.uint8)
    upper_red2 = np.array([180, 255, 255], dtype=np.uint8)

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = cv2.bitwise_or(mask1, mask2)

    red_pixels = int(np.count_nonzero(mask))
    total_pixels = roi.shape[0] * roi.shape[1]
    red_ratio = (red_pixels / total_pixels) * 100.0 if total_pixels > 0 else 0.0

    return red_ratio, (x1, y1, x2, y2), mask


def format_swipe_command(x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> str:
    """Định dạng lệnh gửi qua Socket về điện thoại."""
    return f"SWIPE,{int(x1)},{int(y1)},{int(x2)},{int(y2)},{int(duration_ms)}\n"


class PCControllerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PC Controller - Điều Khiển Cảm Ứng & Quét Tâm Đỏ (Port 8888)")
        self.root.geometry("1040x760")
        self.root.configure(bg="#0F172A")

        self.server_port = 8888
        self.local_ip = get_local_lan_ip()
        self.server_socket = None
        self.client_socket = None
        self.client_lock = threading.Lock()
        self.running = True

        # Trạng thái tự động vuốt
        self.auto_swipe_enabled = tk.BooleanVar(value=False)
        self.swipe_distance = tk.IntVar(value=180)       # Độ dài lực vuốt (px trên khung hình)
        self.swipe_start_x_pct = tk.IntVar(value=75)     # Tọa độ X điểm bắt đầu vuốt (% chiều ngang)
        self.swipe_start_y_pct = tk.IntVar(value=72)     # Tọa độ Y điểm bắt đầu vuốt (% chiều dọc)
        self.swipe_duration_ms = tk.IntVar(value=95)     # Thời gian vuốt (ms)
        self.red_threshold_pct = tk.DoubleVar(value=8.0) # Ngưỡng phần trăm pixel đỏ trong vùng 30x30
        self.cooldown_ms = tk.IntVar(value=350)          # Thời gian nghỉ giữa 2 lần tự động vuốt (ms)

        self.last_swipe_time = 0.0
        self.swipe_count = 0
        self.fps = 0.0
        self.latest_frame_shape = (800, 360)  # (h, w)

        # Thao tác kéo chuột trực tiếp trên màn hình preview
        self.drag_start = None

        self._build_ui()
        self._start_tcp_server()

        self.root.bind("<F6>", lambda e: self.toggle_auto_swipe())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # Thanh thông tin IP phía trên
        top_bar = tk.Frame(self.root, bg="#1E293B", padx=14, pady=10)
        top_bar.pack(fill=tk.X)

        ip_label = tk.Label(
            top_bar,
            text=f"IP LAN CỦA MÁY TÍNH:  {self.local_ip}   |   PORT: {self.server_port}",
            font=("Segoe UI", 13, "bold"),
            fg="#38BDF8",
            bg="#1E293B"
        )
        ip_label.pack(side=tk.LEFT)

        copy_btn = tk.Button(
            top_bar,
            text="Sao chép IP",
            font=("Segoe UI", 10, "bold"),
            bg="#2563EB",
            fg="white",
            activebackground="#1D4ED8",
            activeforeground="white",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            command=self.copy_ip
        )
        copy_btn.pack(side=tk.LEFT, padx=12)

        self.conn_status_lbl = tk.Label(
            top_bar,
            text="● Đang chờ điện thoại kết nối (Port 8888)...",
            font=("Segoe UI", 11, "bold"),
            fg="#FBBF24",
            bg="#1E293B"
        )
        self.conn_status_lbl.pack(side=tk.RIGHT)

        # Khung chính chia 2 cột: Trái (Màn hình trực tiếp) - Phải (Bảng điều khiển)
        main_frame = tk.Frame(self.root, bg="#0F172A", padx=12, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Cột trái: Hiển thị khung hình điện thoại
        left_panel = tk.Frame(main_frame, bg="#020617", bd=1, relief=tk.SOLID)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.video_canvas = tk.Label(
            left_panel,
            text="Chưa có tín hiệu hình ảnh từ điện thoại.\n\n"
                 f"1. Mở ứng dụng RemoteTouch_Android trên điện thoại\n"
                 f"2. Bấm cấp quyền Trợ năng & Chụp màn hình\n"
                 f"3. Nhập IP: {self.local_ip} và bấm Kết nối",
            font=("Segoe UI", 12),
            fg="#94A3B8",
            bg="#020617",
            justify=tk.CENTER
        )
        self.video_canvas.pack(fill=tk.BOTH, expand=True)

        # Cho phép click / kéo chuột trực tiếp trên màn hình PC để gửi TAP / SWIPE
        self.video_canvas.bind("<ButtonPress-1>", self.on_canvas_mouse_down)
        self.video_canvas.bind("<ButtonRelease-1>", self.on_canvas_mouse_up)

        # Cột phải: Bảng điều khiển & Thanh trượt (Sliders)
        right_panel = tk.Frame(main_frame, bg="#1E293B", width=380, padx=16, pady=14)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        right_panel.pack_propagate(False)

        tk.Label(
            right_panel,
            text="BẢNG ĐIỀU KHIỂN TỰ ĐỘNG VUỐT",
            font=("Segoe UI", 12, "bold"),
            fg="#F8FAFC",
            bg="#1E293B"
        ).pack(anchor="w", pady=(0, 10))

        # Nút Bật/Tắt chế độ tự động vuốt
        self.btn_toggle_auto = tk.Button(
            right_panel,
            text="CHẾ ĐỘ TỰ ĐỘNG VUỐT: ĐANG TẮT (Bấm hoặc F6)",
            font=("Segoe UI", 11, "bold"),
            bg="#475569",
            fg="white",
            activebackground="#334155",
            activeforeground="white",
            relief=tk.FLAT,
            pady=10,
            command=self.toggle_auto_swipe
        )
        self.btn_toggle_auto.pack(fill=tk.X, pady=(0, 14))

        # Hộp thông số nhận diện thời gian thực
        metrics_frame = tk.Frame(right_panel, bg="#0F172A", padx=10, pady=8)
        metrics_frame.pack(fill=tk.X, pady=(0, 14))

        self.lbl_red_pct = tk.Label(
            metrics_frame,
            text="Màu đỏ vùng tâm (30x30): 0.0%",
            font=("Segoe UI", 10, "bold"),
            fg="#F87171",
            bg="#0F172A"
        )
        self.lbl_red_pct.pack(anchor="w")

        self.lbl_stats = tk.Label(
            metrics_frame,
            text="FPS: 0.0  |  Số lần vuốt tự động: 0",
            font=("Segoe UI", 10),
            fg="#94A3B8",
            bg="#0F172A"
        )
        self.lbl_stats.pack(anchor="w", pady=(4, 0))

        # Các thanh trượt (Sliders) tùy chỉnh
        self._create_slider(
            right_panel,
            "1. Độ dài lực vuốt (Swipe Distance - px):",
            self.swipe_distance,
            from_=30,
            to=500
        )

        self._create_slider(
            right_panel,
            "2. Tọa độ X vùng vuốt (% chiều ngang):",
            self.swipe_start_x_pct,
            from_=10,
            to=95
        )

        self._create_slider(
            right_panel,
            "3. Tọa độ Y vùng vuốt (% chiều dọc):",
            self.swipe_start_y_pct,
            from_=20,
            to=95
        )

        self._create_slider(
            right_panel,
            "4. Thời gian vuốt (Duration - ms):",
            self.swipe_duration_ms,
            from_=25,
            to=400
        )

        self._create_slider(
            right_panel,
            "5. Ngưỡng nhạy màu đỏ (% pixel vùng 30x30):",
            self.red_threshold_pct,
            from_=1,
            to=40
        )

        self._create_slider(
            right_panel,
            "6. Thời gian nghỉ giữa 2 lần vuốt (Cooldown ms):",
            self.cooldown_ms,
            from_=100,
            to=1000
        )

        # Nút vuốt thử nghiệm thủ công
        test_btn = tk.Button(
            right_panel,
            text="Gửi lệnh SWIPE thử nghiệm ngay",
            font=("Segoe UI", 10, "bold"),
            bg="#059669",
            fg="white",
            relief=tk.FLAT,
            pady=7,
            command=self.trigger_test_swipe
        )
        test_btn.pack(fill=tk.X, pady=(8, 6))

        self.lbl_last_cmd = tk.Label(
            right_panel,
            text="Lệnh gần nhất: (Chưa gửi)",
            font=("Consolas", 9),
            fg="#38BDF8",
            bg="#1E293B",
            wraplength=340,
            justify=tk.LEFT
        )
        self.lbl_last_cmd.pack(anchor="w", pady=(4, 0))

    def _create_slider(self, parent, label_text, variable, from_, to):
        frame = tk.Frame(parent, bg="#1E293B")
        frame.pack(fill=tk.X, pady=4)

        header = tk.Frame(frame, bg="#1E293B")
        header.pack(fill=tk.X)

        lbl = tk.Label(
            header,
            text=label_text,
            font=("Segoe UI", 9, "bold"),
            fg="#E2E8F0",
            bg="#1E293B"
        )
        lbl.pack(side=tk.LEFT)

        val_lbl = tk.Label(
            header,
            textvariable=variable,
            font=("Segoe UI", 9, "bold"),
            fg="#38BDF8",
            bg="#1E293B"
        )
        val_lbl.pack(side=tk.RIGHT)

        scale = tk.Scale(
            frame,
            variable=variable,
            from_=from_,
            to=to,
            orient=tk.HORIZONTAL,
            bg="#1E293B",
            fg="#CBD5E1",
            highlightthickness=0,
            troughcolor="#0F172A",
            activebackground="#38BDF8",
            showvalue=False
        )
        scale.pack(fill=tk.X)

    def copy_ip(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.local_ip)
        messagebox.showinfo("Đã sao chép", f"Đã sao chép địa chỉ IP: {self.local_ip}")

    def toggle_auto_swipe(self):
        new_state = not self.auto_swipe_enabled.get()
        self.auto_swipe_enabled.set(new_state)
        if new_state:
            self.btn_toggle_auto.configure(
                text="CHẾ ĐỘ TỰ ĐỘNG VUỐT: ĐANG BẬT (F6 để tắt)",
                bg="#E11D48",
                activebackground="#BE123C"
            )
        else:
            self.btn_toggle_auto.configure(
                text="CHẾ ĐỘ TỰ ĐỘNG VUỐT: ĐANG TẮT (Bấm hoặc F6)",
                bg="#475569",
                activebackground="#334155"
            )

    def _start_tcp_server(self):
        def server_loop():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("0.0.0.0", self.server_port))
                srv.listen(1)
                self.server_socket = srv

                while self.running:
                    try:
                        client, addr = srv.accept()
                        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except Exception:
                        if not self.running:
                            break
                        continue

                    with self.client_lock:
                        if self.client_socket:
                            try:
                                self.client_socket.close()
                            except Exception:
                                pass
                        self.client_socket = client

                    self.root.after(
                        0,
                        lambda a=addr: self.conn_status_lbl.configure(
                            text=f"● Đã kết nối với điện thoại: {a[0]}:{a[1]}",
                            fg="#34D399"
                        )
                    )
                    self._handle_client_stream(client)

            except Exception as e:
                if self.running:
                    self.root.after(
                        0,
                        lambda err=str(e): self.conn_status_lbl.configure(
                            text=f"● Lỗi mở cổng 8888: {err}",
                            fg="#F87171"
                        )
                    )

        t = threading.Thread(target=server_loop, daemon=True)
        t.start()

    def _recv_exact(self, sock: socket.socket, num_bytes: int) -> bytes:
        buf = bytearray()
        while len(buf) < num_bytes:
            chunk = sock.recv(num_bytes - len(buf))
            if not chunk:
                return b""
            buf.extend(chunk)
        return bytes(buf)

    def _handle_client_stream(self, client: socket.socket):
        frame_counter = 0
        fps_timer = time.time()

        try:
            while self.running:
                header = self._recv_exact(client, 4)
                if not header:
                    break
                frame_len = struct.unpack(">I", header)[0]
                if frame_len <= 0 or frame_len > 10_000_000:
                    break

                jpeg_bytes = self._recv_exact(client, frame_len)
                if not jpeg_bytes:
                    break

                np_arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                frame_counter += 1
                now = time.time()
                if now - fps_timer >= 1.0:
                    self.fps = frame_counter / (now - fps_timer)
                    frame_counter = 0
                    fps_timer = now

                self._process_and_render_frame(frame)

        except Exception:
            pass
        finally:
            with self.client_lock:
                if self.client_socket is client:
                    self.client_socket = None
            try:
                client.close()
            except Exception:
                pass
            if self.running:
                self.root.after(
                    0,
                    lambda: self.conn_status_lbl.configure(
                        text="● Điện thoại đã ngắt kết nối. Đang chờ kết nối lại...",
                        fg="#FBBF24"
                    )
                )

    def _process_and_render_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        self.latest_frame_shape = (h, w)

        # 1. Quét vùng trung tâm 30x30 pixel trong hệ màu HSV để phát hiện màu đỏ
        red_ratio, (bx1, by1, bx2, by2), _ = detect_red_center_hsv(frame, roi_size=30)
        threshold = float(self.red_threshold_pct.get())
        is_red_detected = red_ratio >= threshold

        # 2. Tính toán tọa độ vuốt kéo tâm thẳng lên trên
        swipe_x = int((self.swipe_start_x_pct.get() / 100.0) * w)
        swipe_y1 = int((self.swipe_start_y_pct.get() / 100.0) * h)
        swipe_dist = int(self.swipe_distance.get())
        swipe_y2 = max(10, swipe_y1 - swipe_dist)
        duration = int(self.swipe_duration_ms.get())

        # 3. Nếu chế độ Auto-Swipe đang bật và phát hiện tâm đỏ vượt ngưỡng -> Gửi lệnh SWIPE
        now = time.time()
        cooldown_sec = self.cooldown_ms.get() / 1000.0
        if self.auto_swipe_enabled.get() and is_red_detected and (now - self.last_swipe_time >= cooldown_sec):
            self.last_swipe_time = now
            self.swipe_count += 1
            self.send_swipe(swipe_x, swipe_y1, swipe_x, swipe_y2, duration)

        # 4. Vẽ trực quan vùng quét 30x30 ở tâm và mũi tên hướng vuốt lên khung hình hiển thị
        display_frame = frame.copy()
        box_color = (0, 0, 255) if is_red_detected else (0, 255, 0)
        cv2.rectangle(display_frame, (bx1, by1), (bx2, by2), box_color, 2)

        # Vẽ đường biểu diễn lực vuốt và vị trí vuốt trên màn hình PC
        cv2.circle(display_frame, (swipe_x, swipe_y1), 6, (255, 200, 0), -1)
        cv2.arrowedLine(
            display_frame,
            (swipe_x, swipe_y1),
            (swipe_x, swipe_y2),
            (0, 215, 255),
            2,
            tipLength=0.15
        )

        # Chuyển đổi sang ảnh Tkinter để hiển thị mượt trên cửa sổ
        rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        canvas_w = max(280, self.video_canvas.winfo_width() - 10)
        canvas_h = max(480, self.video_canvas.winfo_height() - 10)
        scale = min(canvas_w / w, canvas_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        pil_img = Image.fromarray(rgb_frame).resize((new_w, new_h), Image.Resampling.BILINEAR)
        self.root.after(0, self._update_gui_frame, pil_img, red_ratio, is_red_detected)

    def _update_gui_frame(self, pil_img: Image.Image, red_ratio: float, is_red_detected: bool):
        if not self.running:
            return
        tk_img = ImageTk.PhotoImage(pil_img)
        self.video_canvas.configure(image=tk_img, text="")
        self.video_canvas.image = tk_img

        self.lbl_red_pct.configure(
            text=f"Màu đỏ vùng tâm (30x30): {red_ratio:.1f}% {'[PHÁT HIỆN ĐỎ!]' if is_red_detected else ''}",
            fg="#EF4444" if is_red_detected else "#34D399"
        )
        self.lbl_stats.configure(
            text=f"FPS: {self.fps:.1f}  |  Số lần vuốt tự động: {self.swipe_count}"
        )

    def send_raw_command(self, cmd_str: str):
        with self.client_lock:
            sock = self.client_socket
        if sock is None:
            return
        try:
            sock.sendall(cmd_str.encode("utf-8"))
            self.root.after(0, lambda c=cmd_str.strip(): self.lbl_last_cmd.configure(text=f"Lệnh gần nhất: {c}"))
        except Exception:
            pass

    def send_swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int):
        cmd = format_swipe_command(x1, y1, x2, y2, duration_ms)
        self.send_raw_command(cmd)

    def trigger_test_swipe(self):
        h, w = self.latest_frame_shape
        swipe_x = int((self.swipe_start_x_pct.get() / 100.0) * w)
        swipe_y1 = int((self.swipe_start_y_pct.get() / 100.0) * h)
        swipe_y2 = max(10, swipe_y1 - int(self.swipe_distance.get()))
        duration = int(self.swipe_duration_ms.get())
        self.send_swipe(swipe_x, swipe_y1, swipe_x, swipe_y2, duration)

    def _canvas_to_frame_coords(self, event_x: int, event_y: int):
        img = getattr(self.video_canvas, "image", None)
        if img is None:
            return None
        disp_w = img.width()
        disp_h = img.height()
        lbl_w = self.video_canvas.winfo_width()
        lbl_h = self.video_canvas.winfo_height()
        offset_x = (lbl_w - disp_w) // 2
        offset_y = (lbl_h - disp_h) // 2

        rel_x = event_x - offset_x
        rel_y = event_y - offset_y
        if rel_x < 0 or rel_y < 0 or rel_x >= disp_w or rel_y >= disp_h:
            return None

        frame_h, frame_w = self.latest_frame_shape
        fx = int((rel_x / disp_w) * frame_w)
        fy = int((rel_y / disp_h) * frame_h)
        return fx, fy

    def on_canvas_mouse_down(self, event):
        coords = self._canvas_to_frame_coords(event.x, event.y)
        if coords:
            self.drag_start = coords

    def on_canvas_mouse_up(self, event):
        if not self.drag_start:
            return
        end_coords = self._canvas_to_frame_coords(event.x, event.y)
        start_x, start_y = self.drag_start
        self.drag_start = None
        if not end_coords:
            return
        end_x, end_y = end_coords
        dist = np.hypot(end_x - start_x, end_y - start_y)
        if dist < 10:
            self.send_raw_command(f"TAP,{start_x},{start_y},50\n")
        else:
            self.send_swipe(start_x, start_y, end_x, end_y, int(self.swipe_duration_ms.get()))

    def on_close(self):
        self.running = False
        try:
            if self.client_socket:
                self.client_socket.close()
        except Exception:
            pass
        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PCControllerApp(root)
    root.mainloop()
