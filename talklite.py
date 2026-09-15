import socket
import struct
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox

import sounddevice as sd

APP_NAME = "TalkLite"
HOST = "0.0.0.0"
PORT = 39876
RATE = 16000
CHANNELS = 1
BLOCK = 320  # 20 ms at 16 kHz
SAMPLE_WIDTH = 2
MAX_PACKET = BLOCK * SAMPLE_WIDTH * 2


def send_frame(sock, pcm: bytes):
    if len(pcm) > 65535:
        return
    sock.sendall(struct.pack("!H", len(pcm)) + pcm)


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("연결이 종료되었습니다.")
        data.extend(chunk)
    return bytes(data)


def recv_frame(sock):
    header = recv_exact(sock, 2)
    size = struct.unpack("!H", header)[0]
    if size <= 0 or size > MAX_PACKET:
        raise ConnectionError("잘못된 오디오 패킷입니다.")
    return recv_exact(sock, size)


class CallSession:
    def __init__(self, sock, on_state):
        self.sock = sock
        self.sock.settimeout(None)
        self.on_state = on_state
        self.running = True
        self.send_lock = threading.Lock()
        self.play_queue = queue.Queue(maxsize=8)
        self.stream_in = None
        self.stream_out = None

    def start(self):
        self.on_state("통화 연결됨")
        self.stream_in = sd.RawInputStream(
            samplerate=RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=BLOCK,
            callback=self._mic_callback,
        )
        self.stream_out = sd.RawOutputStream(
            samplerate=RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=BLOCK,
            callback=self._speaker_callback,
        )
        self.stream_in.start()
        self.stream_out.start()
        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _mic_callback(self, indata, frames, time_info, status):
        if not self.running:
            return
        try:
            pcm = bytes(indata)
            with self.send_lock:
                send_frame(self.sock, pcm)
        except Exception:
            self.stop("통화 연결이 끊어졌습니다.")

    def _speaker_callback(self, outdata, frames, time_info, status):
        try:
            pcm = self.play_queue.get_nowait()
            if len(pcm) < len(outdata):
                outdata[:len(pcm)] = pcm
                outdata[len(pcm):] = b"\x00" * (len(outdata) - len(pcm))
            else:
                outdata[:] = pcm[:len(outdata)]
        except queue.Empty:
            outdata[:] = b"\x00" * len(outdata)

    def _receive_loop(self):
        try:
            while self.running:
                pcm = recv_frame(self.sock)
                try:
                    self.play_queue.put_nowait(pcm)
                except queue.Full:
                    # Drop the oldest packet to keep latency low.
                    try:
                        self.play_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.play_queue.put_nowait(pcm)
                    except queue.Full:
                        pass
        except Exception:
            if self.running:
                self.stop("통화 연결이 끊어졌습니다.")

    def stop(self, reason="통화 종료"):
        if not self.running:
            return
        self.running = False
        for stream in (self.stream_in, self.stream_out):
            try:
                if stream:
                    stream.stop()
                    stream.close()
            except Exception:
                pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        self.on_state(reason)


class TalkLiteApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("430x360")
        self.root.minsize(430, 360)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.server = None
        self.server_thread = None
        self.session = None
        self.mode = tk.StringVar(value="caller")
        self.status = tk.StringVar(value="대기 중")
        self.ip_var = tk.StringVar()

        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="친구와 1:1 음성 통화만 간단하게", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 18))

        mode_frame = ttk.Frame(frame)
        mode_frame.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(mode_frame, text="내가 전화 걸기 (서버)", variable=self.mode, value="caller", command=self._mode_changed).pack(side="left")
        ttk.Radiobutton(mode_frame, text="친구에게 받기", variable=self.mode, value="callee", command=self._mode_changed).pack(side="left", padx=12)

        self.ip_label = ttk.Label(frame, text="친구에게 내 주소를 알려주세요")
        self.ip_label.pack(anchor="w")
        self.ip_entry = ttk.Entry(frame, textvariable=self.ip_var)
        self.ip_entry.pack(fill="x", pady=(5, 12))

        self.action = ttk.Button(frame, text="통화 대기 시작", command=self._action)
        self.action.pack(fill="x", ipady=8)

        ttk.Button(frame, text="통화 종료", command=self.end_call).pack(fill="x", pady=(8, 0), ipady=5)

        ttk.Separator(frame).pack(fill="x", pady=18)
        ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text="오디오: 16 kHz / 16-bit / mono\n헤드셋 사용을 권장합니다.", foreground="#666").pack(anchor="w", pady=(8, 0))

        self._mode_changed()

    def _mode_changed(self):
        if self.session:
            return
        if self.mode.get() == "caller":
            self.ip_label.config(text="친구에게 내 PC 주소를 알려주세요 (같은 Wi-Fi면 사설 IP)")
            self.ip_entry.config(state="disabled")
            self.action.config(text="통화 대기 시작")
        else:
            self.ip_label.config(text=f"친구의 IP 주소 (포트 {PORT})")
            self.ip_entry.config(state="normal")
            self.action.config(text="친구에게 연결")

    def _action(self):
        if self.session:
            return
        if self.mode.get() == "caller":
            self.start_server()
        else:
            self.connect_to_friend()

    def start_server(self):
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, PORT))
            self.server.listen(1)
            self.status.set(f"통화 대기 중 — 포트 {PORT}")
            self.action.config(state="disabled")
            self.server_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self.server_thread.start()
        except Exception as e:
            self._cleanup_server()
            messagebox.showerror(APP_NAME, f"서버를 열 수 없습니다.\n\n{e}")

    def _accept_loop(self):
        try:
            sock, addr = self.server.accept()
            self._cleanup_server()
            self.root.after(0, lambda: self._start_session(sock, f"친구 연결됨: {addr[0]}"))
        except Exception as e:
            self.root.after(0, lambda: self.status.set(f"연결 대기 종료: {e}"))
            self._cleanup_server()

    def connect_to_friend(self):
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showwarning(APP_NAME, "친구의 IP 주소를 입력하세요.")
            return
        self.status.set("친구에게 연결 중...")
        self.action.config(state="disabled")
        threading.Thread(target=self._connect_thread, args=(ip,), daemon=True).start()

    def _connect_thread(self, ip):
        try:
            sock = socket.create_connection((ip, PORT), timeout=8)
            self.root.after(0, lambda: self._start_session(sock, "친구에게 연결됨"))
        except Exception as e:
            self.root.after(0, lambda: self._connect_failed(e))

    def _connect_failed(self, e):
        self.status.set("연결 실패")
        self.action.config(state="normal")
        messagebox.showerror(APP_NAME, f"연결할 수 없습니다.\n\n{e}\n\n친구가 통화 대기를 시작했는지, IP와 방화벽/포트 설정을 확인하세요.")

    def _start_session(self, sock, text):
        try:
            self.session = CallSession(sock, self.status.set)
            self.session.start()
            self.status.set(text)
            self.action.config(state="disabled")
        except Exception as e:
            try:
                sock.close()
            except Exception:
                pass
            self.session = None
            self.action.config(state="normal")
            messagebox.showerror(APP_NAME, f"오디오 장치를 시작할 수 없습니다.\n\n{e}")

    def end_call(self):
        if self.session:
            self.session.stop("통화 종료")
            self.session = None
        self._cleanup_server()
        self.action.config(state="normal")
        self._mode_changed()

    def _cleanup_server(self):
        if self.server:
            try:
                self.server.close()
            except Exception:
                pass
            self.server = None

    def close(self):
        self.end_call()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    TalkLiteApp(root)
    root.mainloop()
