#!/usr/bin/env python3
"""
multimodal_game.py

Multimodal demo (voz + gestos) con fallback automático:
- Usa MediaPipe Hands si está instalado y funciona.
- Si MediaPipe falla, usa detector por color (OpenCV-only).
- Reconocimiento de voz (SpeechRecognition) + TTS (pyttsx3) en subprocess por utterance.
- UI con OpenCV, muestra cámara, objetivo, score, feedback.
"""

from __future__ import annotations
import argparse
import time
import math
import threading
import queue
import multiprocessing
import os
import signal
import traceback
import re
from difflib import get_close_matches

# imports that must be present
try:
    import cv2
except Exception:
    print("Error: OpenCV (cv2) no encontrado. Instala opencv-python en el venv.")
    raise
try:
    import numpy as np
except Exception:
    print("Error: numpy no encontrado. Instala numpy en el venv.")
    raise
try:
    import speech_recognition as sr
except Exception:
    print("Error: SpeechRecognition no encontrado. Instala SpeechRecognition en el venv.")
    raise

# NOTE: do NOT import mediapipe at module import time; we'll try to import and initialize it in main()
# because partial/broken installs can raise FileNotFoundError at import time.

# -----------------------------
# Command mapping (variants)
# -----------------------------
COMMAND_MAP = [
    (["iniciar juego", "start game", "comenzar juego", "start"], "start_game", "Iniciando juego", "/game/start", ["start_game"]),
    (["detener juego", "stop game", "parar juego", "stop"], "stop_game", "Deteniendo juego", "/game/stop", ["stop_game"]),
    (["pausa", "pause", "pausar"], "pause", "Pausado", "/game/pause", ["pause"]),
    (["puntaje", "score", "marcador"], "score", "Mostrando puntaje", "/game/score", ["score"]),
    (["izquierda", "a la izquierda", "mover a la izquierda", "mueve a la izquierda", "left", "yendo a la izquierda"], "left", "Moviendo a la izquierda", "/control/move", ["left"]),
    (["derecha", "a la derecha", "mover a la derecha", "mueve a la derecha", "right"], "right", "Moviendo a la derecha", "/control/move", ["right"]),
    (["arriba", "sube", "up"], "up", "Moviendo arriba", "/control/move", ["up"]),
    (["abajo", "baja", "down"], "down", "Moviendo abajo", "/control/move", ["down"]),
    (["hola", "hello"], "hello", "Hola, listo para recibir comandos", "/app/hello", ["hello"]),
    (["captura", "capture", "foto"], "capture", "Capturando imagen", "/app/capture", ["capture"]),
    (["pinch", "pellizco", "pellizcar", "pinche"], "pinch", "Pinch recibido", "/gesture/pinch", []),
    (["puño", "fist"], "fist", "Puño detectado", "/gesture/fist", []),
    (["salir", "quit", "cerrar"], "quit", "Cerrando. Hasta luego.", "/app/quit", []),
]

def normalize_text(t: str) -> str:
    s = (t or "").lower().strip()
    s = re.sub(r"[^\w\sáéíóúüñ]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def match_command(text: str):
    if not text:
        return None
    norm = normalize_text(text)
    # phrase match
    for keywords, canonical, resp, osc_path, osc_args in COMMAND_MAP:
        for kw in keywords:
            kw_norm = normalize_text(kw)
            if re.search(r"(?u)\b" + re.escape(kw_norm) + r"\b", norm):
                return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": kw}
    # token match
    words = norm.split()
    for keywords, canonical, resp, osc_path, osc_args in COMMAND_MAP:
        for kw in keywords:
            if normalize_text(kw) in words:
                return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": kw}
    # fuzzy fallback
    all_keywords = []
    kw_map = {}
    for keywords, canonical, resp, osc_path, osc_args in COMMAND_MAP:
        for kw in keywords:
            nk = normalize_text(kw)
            all_keywords.append(nk)
            kw_map[nk] = (canonical, resp, osc_path, osc_args, kw)
    matches = get_close_matches(norm, all_keywords, n=1, cutoff=0.7)
    if matches:
        mk = matches[0]
        canonical, resp, osc_path, osc_args, orig_kw = kw_map[mk]
        return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": orig_kw}
    return None

# -----------------------------
# TTS: process-per-utterance (robusto)
# -----------------------------
def _tts_process_worker(text: str, rate=None, volume=None):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        if rate is not None:
            try:
                engine.setProperty("rate", rate)
            except Exception:
                pass
        if volume is not None:
            try:
                engine.setProperty("volume", volume)
            except Exception:
                pass
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[TTS proc {os.getpid()}] error:", e)
        except Exception:
            pass
    return

class TTSEngine:
    def __init__(self, enabled: bool = True, rate: int | None = None, volume: float | None = None):
        self.enabled = bool(enabled)
        self.rate = rate
        self.volume = volume
        self._procs = []
        print(f"[TTS] Process-based TTS initialized (enabled={self.enabled})")

    def _cleanup_procs(self):
        alive = []
        for p, t0 in self._procs:
            if p.is_alive():
                alive.append((p, t0))
            else:
                try:
                    p.join(timeout=0.01)
                except Exception:
                    pass
        self._procs = alive

    def say(self, text: str):
        if not self.enabled or text is None:
            return
        s = str(text)
        try:
            p = multiprocessing.Process(target=_tts_process_worker, args=(s, self.rate, self.volume), daemon=True)
            p.start()
            self._procs.append((p, time.time()))
            if len(self._procs) > 12:
                self._cleanup_procs()
            print(f"[TTS] spawned process pid={p.pid} for: {repr(s)} (active={len(self._procs)})")
        except Exception as e:
            print("[TTS] failed to spawn process:", e)

    def stop(self):
        for p, _ in self._procs:
            try:
                if p.is_alive():
                    try:
                        p.terminate()
                    except Exception:
                        pass
                p.join(timeout=0.1)
            except Exception:
                pass
        self._procs = []
        print("[TTS] stopped - child processes terminated")

# -----------------------------
# Voice recognizer thread
# -----------------------------
class VoiceListener:
    def __init__(self, event_q: queue.Queue, language="es-ES", device_index=None, enable_tts=True):
        self.event_q = event_q
        self.language = language
        self.device_index = device_index
        self.recognizer = sr.Recognizer()
        self.stop_listening_fn = None
        self.tts = TTSEngine(enabled=enable_tts)

    def start(self):
        mic_kwargs = {}
        if self.device_index is not None:
            mic_kwargs["device_index"] = int(self.device_index)
        try:
            with sr.Microphone(**mic_kwargs) as source:
                print("[Voice] Ajustando ruido ambiente...")
                try:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                except Exception:
                    pass
            print("[Voice] Empezando escucha en background...")
            self.stop_listening_fn = self.recognizer.listen_in_background(
                sr.Microphone(**mic_kwargs),
                self._callback,
                phrase_time_limit=5.0
            )
            return True
        except Exception as e:
            print("[Voice] No se pudo iniciar micrófono:", e)
            return False

    def _callback(self, recognizer, audio):
        try:
            text = recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            return
        except sr.RequestError as e:
            print("[Voice] RequestError (Google):", e)
            return
        except Exception as e:
            print("[Voice] Recognition unexpected error:", e)
            return
        if not text:
            return
        print("[Reconocimiento]", text)
        match = match_command(text)
        if match:
            self.event_q.put({"type": "voice", "cmd": match["cmd"], "resp": match["resp"], "raw": text, "matched_kw": match.get("matched_kw")})
            self.tts.say(match["resp"])
        else:
            self.event_q.put({"type": "voice", "cmd": None, "raw": text})
            self.tts.say("No entendí el comando")

    def stop(self):
        try:
            if self.stop_listening_fn:
                self.stop_listening_fn(wait_for_stop=False)
        except Exception:
            pass
        self.tts.stop()

# -----------------------------
# Color-based gesture detector (fallback)
# -----------------------------
class ColorGestureDetector(threading.Thread):
    def __init__(self, event_q: queue.Queue, camera_index=0, mirror=True,
                 hsv_lower=(40, 70, 70), hsv_upper=(90, 255, 255), min_area=200, frame_queue: queue.Queue | None = None):
        """Color-based detector. If frame_queue is provided, it will read frames from it instead
        of opening its own VideoCapture. This avoids multiple processes opening the same camera.
        """
        super().__init__(daemon=True)
        self.event_q = event_q
        self.camera_index = camera_index
        self.mirror = mirror
        self.running = False
        self.hsv_lower = np.array(hsv_lower, dtype=np.uint8)
        self.hsv_upper = np.array(hsv_upper, dtype=np.uint8)
        self.min_area = min_area
        self.cap = None
        self.last_centroid = None
        self.frame_queue = frame_queue
        self._frames_processed = 0

    def run(self):
        cap = None
        if self.frame_queue is None:
            cap = cv2.VideoCapture(self.camera_index)
            self.cap = cap
        self.running = True
        print("[ColorGesture] detector started (frame_queue mode)" if self.frame_queue else "[ColorGesture] detector started (own camera)")
        try:
            while self.running:
                frame = None
                if self.frame_queue is not None:
                    try:
                        frame = self.frame_queue.get(timeout=0.5)
                    except Exception:
                        frame = None
                else:
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.02)
                        continue
                if frame is None:
                    continue
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=1)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                centroid = None
                if contours:
                    c = max(contours, key=cv2.contourArea)
                    area = cv2.contourArea(c)
                    if area >= self.min_area:
                        M = cv2.moments(c)
                        if M["m00"] != 0:
                            cx = int(M["m10"]/M["m00"])
                            cy = int(M["m01"]/M["m00"])
                            centroid = (cx, cy)
                            nx = cx / float(w)
                            ny = cy / float(h)
                            # pos event (include frame only if this detector owns the camera)
                            pos_evt = {"type": "gesture", "event": "pos", "x": nx, "y": ny}
                            if self.frame_queue is None:
                                try:
                                    pos_evt["frame"] = frame.copy()
                                except Exception:
                                    pass
                            try:
                                self.event_q.put(pos_evt, block=False)
                            except Exception:
                                self.event_q.put(pos_evt)
                            self.last_centroid = (nx, ny)
                            self._frames_processed += 1
                            if self._frames_processed % 30 == 0:
                                print(f"[ColorGesture] tracking at ({nx:.2f}, {ny:.2f}) area={area:.0f}")
                if centroid is None:
                    try:
                        if self.frame_queue is None:
                            evt = {"type": "gesture", "event": "frame_only", "frame": frame.copy()}
                        else:
                            evt = {"type": "gesture", "event": "frame_only"}
                        self.event_q.put(evt, block=False)
                    except Exception:
                        try:
                            if self.frame_queue is None:
                                evt = {"type": "gesture", "event": "frame_only", "frame": frame.copy()}
                            else:
                                evt = {"type": "gesture", "event": "frame_only"}
                            self.event_q.put(evt)
                        except Exception:
                            pass
                time.sleep(0.02)
        except Exception as e:
            print("[ColorGesture] error:", e)
            traceback.print_exc()
        finally:
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            self.running = False
            print("[ColorGesture] detector stopped")

    def stop(self):
        self.running = False

# -----------------------------
# MediaPipe-based gesture detector (only defined if MP import successful)
# We'll attempt to define it later inside main() if mediapipe is available.
# -----------------------------

# -----------------------------
# Camera preview feeder (shared)
# -----------------------------
class CameraPreview(threading.Thread):
    def __init__(self, event_q: queue.Queue, camera_index=0, mirror=True, frame_queue: queue.Queue | None = None):
        super().__init__(daemon=True)
        self.event_q = event_q
        self.camera_index = camera_index
        self.mirror = mirror
        self.running = False
        self.cap = None
        self.frame_queue = frame_queue

    def run(self):
        cap = None
        camera_ok = False
        attempted = []
        # Try default open first
        try:
            cap = cv2.VideoCapture(self.camera_index)
            if cap is not None and cap.isOpened():
                camera_ok = True
                attempted.append((self.camera_index, 'default'))
        except Exception:
            pass
        # Try common Windows backends if default failed
        if not camera_ok:
            backends = []
            if hasattr(cv2, 'CAP_DSHOW'):
                backends.append(('CAP_DSHOW', cv2.CAP_DSHOW))
            if hasattr(cv2, 'CAP_MSMF'):
                backends.append(('CAP_MSMF', cv2.CAP_MSMF))
            if hasattr(cv2, 'CAP_VFW'):
                backends.append(('CAP_VFW', cv2.CAP_VFW))
            for name, b in backends:
                try:
                    cap_try = cv2.VideoCapture(self.camera_index, b)
                    if cap_try is not None and cap_try.isOpened():
                        cap = cap_try
                        camera_ok = True
                        attempted.append((self.camera_index, name))
                        break
                    else:
                        try:
                            cap_try.release()
                        except Exception:
                            pass
                except Exception:
                    pass
        if camera_ok:
            self.cap = cap
            print(f"[CameraPreview] opened camera index={self.camera_index} via {attempted[-1][1]}")
        else:
            print(f"[CameraPreview] WARNING: could not open camera index={self.camera_index}. Tried: {attempted}")
        self.running = True
        try:
            while self.running:
                frame = None
                if camera_ok and cap is not None:
                    try:
                        ret, frame = cap.read()
                    except Exception:
                        ret = False
                        frame = None
                    if not ret or frame is None:
                        # camera opened but read failed; allow retry but produce diagnostic frame
                        frame = None
                if frame is None:
                    # produce a diagnostic frame so UI isn't just a black screen
                    diag = np.zeros((480, 640, 3), dtype=np.uint8)
                    msg = "Camera not available"
                    cv2.putText(diag, msg, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                    cv2.putText(diag, f"index={self.camera_index}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                    cv2.putText(diag, "Check camera permissions / device index", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
                    frame_send = diag
                else:
                    if self.mirror:
                        frame = cv2.flip(frame, 1)
                    frame_send = frame
                try:
                    self.event_q.put({"type": "camera_frame", "frame": frame_send}, block=False)
                except Exception:
                    self.event_q.put({"type": "camera_frame", "frame": frame_send})
                # also put into frame_queue for detectors (non-blocking)
                if self.frame_queue is not None:
                    try:
                        if self.frame_queue.full():
                            try:
                                _ = self.frame_queue.get_nowait()
                            except Exception:
                                pass
                        self.frame_queue.put(frame_send, block=False)
                    except Exception:
                        try:
                            self.frame_queue.put(frame_send)
                        except Exception:
                            pass
                time.sleep(0.03)
        finally:
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            self.running = False

    def stop(self):
        self.running = False

# -----------------------------
# Main game class (UI + logic)
# -----------------------------
class MultimodalGame:
    def __init__(self, event_q: queue.Queue, width=960, height=640, detector_type="unknown"):
        self.event_q = event_q
        self.width = width
        self.height = height
        self.target_x = 0.5
        self.target_y = 0.5
        self.target_radius = 40
        self.score = 0
        self.game_running = False
        self.last_voice_raw = ""
        self.last_voice_cmd = ""
        self.last_gesture_pos = (0.5, 0.5)
        self.cam_frame = None
        self.lock = threading.Lock()
        self.capture_cooldown = 0.5
        self._last_capture_time = 0.0
        # composed-action state: a voice-triggered capture can request a pinch within a short window
        self.expecting_pinch_until = 0.0
        # small state to provide UI feedback from gesture detections
        self.last_gesture_state = "idle"
        self.detector_type = detector_type

    def spawn_new_target(self):
        with self.lock:
            self.target_x = float(np.random.uniform(0.12, 0.88))
            self.target_y = float(np.random.uniform(0.12, 0.88))

    def handle_voice(self, ev):
        cmd = ev.get("cmd")
        raw = ev.get("raw", "")
        self.last_voice_raw = raw
        if cmd:
            self.last_voice_cmd = cmd
        else:
            self.last_voice_cmd = ""
        if cmd == "start_game":
            self.game_running = True
            self.score = 0
            self.spawn_new_target()
        elif cmd == "stop_game":
            self.game_running = False
        elif cmd == "left":
            with self.lock:
                self.target_x = max(0.02, self.target_x - 0.06)
        elif cmd == "right":
            with self.lock:
                self.target_x = min(0.98, self.target_x + 0.06)
        elif cmd == "up":
            with self.lock:
                self.target_y = max(0.02, self.target_y - 0.06)
        elif cmd == "down":
            with self.lock:
                self.target_y = min(0.98, self.target_y + 0.06)
        elif cmd == "capture":
            # start immediate capture and also enable a short window where a pinch can be used as a composed action
            now = time.time()
            self.expecting_pinch_until = now + 2.0
            self.last_gesture_state = "awaiting_pinch"
            self._do_capture(save_img=True)
        elif cmd == "score":
            print("[Game] current score:", self.score)
        elif cmd == "quit":
            pass

    def handle_gesture(self, ev):
        event = ev.get("event")
        if event == "pos":
            x = ev.get("x"); y = ev.get("y")
            self.last_gesture_pos = (x, y)
            frame = ev.get("frame")
            if frame is not None:
                self.cam_frame = frame
            self.last_gesture_state = "tracking"
        elif event == "pinch":
            x = ev.get("x"); y = ev.get("y")
            if not self.game_running:
                return
            tx, ty = self.target_x, self.target_y
            d = math.hypot(x - tx, y - ty)
            norm_radius = self.target_radius / max(self.width, self.height)
            now = time.time()
            # if pinch happens within the voice-triggered window, award extra points as a composed action
            if d <= norm_radius * 1.2 and (now - self._last_capture_time) > self.capture_cooldown:
                if now <= self.expecting_pinch_until:
                    self.score += 2
                    self.last_gesture_state = "composed_capture"
                    self.expecting_pinch_until = 0.0
                    print("[Game] Composed capture! +2 score=", self.score)
                else:
                    self.score += 1
                    self.last_gesture_state = "captured"
                    print("[Game] Captured! score=", self.score)
                self._last_capture_time = now
                self.spawn_new_target()
        elif event == "frame_only":
            frame = ev.get("frame")
            if frame is not None:
                self.cam_frame = frame

    def _do_capture(self, save_img=False):
        if self.cam_frame is not None:
            bg = self.cam_frame.copy()
        else:
            bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._render_overlay_into_frame(bg)
        if save_img:
            ts = int(time.time())
            fname = f"capture_{ts}.png"
            cv2.imwrite(fname, bg)
            print("[Game] Saved capture:", fname)

    def _render_overlay_into_frame(self, frame):
        tx = int(self.target_x * self.width)
        ty = int(self.target_y * self.height)
        color = (0, 140, 255)
        lx, ly = self.last_gesture_pos
        d = math.hypot(lx - self.target_x, ly - self.target_y)
        norm_radius = self.target_radius / max(self.width, self.height)
        if d <= norm_radius * 1.2:
            color = (0, 220, 0)
        cv2.circle(frame, (tx, ty), self.target_radius, color, -1)
        cv2.putText(frame, f"Score: {self.score}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)
        cv2.putText(frame, f"Game: {'RUN' if self.game_running else 'STOP'}  Voice:{self.last_voice_cmd}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
        cv2.putText(frame, f"Detector: {self.detector_type}", (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,255,150), 1)
        cv2.putText(frame, f"Last voice: {self.last_voice_raw}", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180,180,180), 1)
        # draw last gesture position as small marker
        try:
            gx = int(lx * self.width)
            gy = int(ly * self.height)
            cv2.circle(frame, (gx, gy), 8, (50, 200, 255), -1)
        except Exception:
            pass
        # feedback on composed actions or gesture state
        gs = self.last_gesture_state or ""
        if time.time() <= self.expecting_pinch_until:
            gs = "EXPECTING PINCH"
        cv2.putText(frame, f"Gesture: {gs}", (10, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180,220,180), 1)
        cv2.putText(frame, "Left-click to simulate pinch. Press 'c' to capture. 'q' to quit", (10, self.height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,200), 1)

    def process_events(self):
        while True:
            try:
                ev = self.event_q.get_nowait()
            except queue.Empty:
                break
            try:
                if ev["type"] == "voice":
                    self.handle_voice(ev)
                elif ev["type"] == "gesture":
                    self.handle_gesture(ev)
                elif ev["type"] == "ui_click":
                    px = ev.get("x_px"); py = ev.get("y_px")
                    if px is None or py is None:
                        continue
                    nx = px / float(self.width)
                    ny = py / float(self.height)
                    self.handle_gesture({"type":"gesture", "event":"pinch", "x":nx, "y":ny})
                elif ev["type"] == "camera_frame":
                    self.cam_frame = ev.get("frame")
            except Exception as e:
                print("[Game] error handling event:", e)

    def run_ui_loop(self):
        blank = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        window_name = "Multimodal Game (voz + gestos)"
        cv2.namedWindow(window_name)
        def _mouse_cb(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                try:
                    self.event_q.put({"type":"ui_click", "x_px": x, "y_px": y})
                except Exception:
                    pass
        cv2.setMouseCallback(window_name, _mouse_cb)
        while True:
            self.process_events()
            if self.cam_frame is not None:
                frame = cv2.resize(self.cam_frame, (self.width, self.height))
            else:
                frame = blank.copy()
            self._render_overlay_into_frame(frame)
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                self._do_capture(save_img=True)
            if self.last_voice_cmd == "quit":
                break
        cv2.destroyAllWindows()

# -----------------------------
# Entrypoint and adaptive initialization
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Multimodal (voice + gestures) demo")
    p.add_argument("--device-index", type=int, default=0, help="Camera/mic device index (camera used by gesture detector and preview)")
    p.add_argument("--language", type=str, default="es-ES", help="SpeechRecognition language")
    p.add_argument("--no-tts", action="store_true", help="Disable TTS")
    p.add_argument("--force-color", action="store_true", help="Force color-based gesture detector (skip MediaPipe attempt)")
    return p.parse_args()

def main():
    args = parse_args()
    ev_q = queue.Queue()

    # voice listener (use same device index for microphone if desired)
    voice = VoiceListener(ev_q, language=args.language, device_index=None, enable_tts=(not args.no_tts))

    # camera preview (always useful for UI)
    # create a small frame queue so detectors can reuse the same frames
    frame_q = queue.Queue(maxsize=4)
    cam_preview = CameraPreview(ev_q, camera_index=args.device_index, mirror=True, frame_queue=frame_q)

    # attempt to import and initialize MediaPipe Hands if user did not force color
    use_mediapipe = False
    mp = None
    if not args.force_color:
        try:
            import mediapipe as mp_test
            import os
            # Fix for MediaPipe path issues on Windows with special characters
            mp_path = os.path.dirname(mp_test.__file__)
            print(f"[MAIN] MediaPipe path: {mp_path}")
            # try quick instantiation to ensure the required binary files are present
            try:
                # Set MEDIAPIPE_DISABLE_GPU=1 to avoid GPU issues
                os.environ['MEDIAPIPE_DISABLE_GPU'] = '1'
                htest = mp_test.solutions.hands.Hands(static_image_mode=False, max_num_hands=1, 
                                                       min_detection_confidence=0.5, min_tracking_confidence=0.5)
                htest.close()
                use_mediapipe = True
                mp = mp_test  # provide reference for later
                print("[MAIN] ✓ MediaPipe Hands available and initialized; using MediaPipe detector.")
            except Exception as e:
                error_msg = str(e)
                print(f"[MAIN] ✗ MediaPipe import OK but Hands init failed (will fallback to color): {e}")
                if "path does not exist" in error_msg.lower() or "universität" in error_msg.lower():
                    print("[MAIN] → This is likely due to special characters (ä, ü) in the folder path.")
                    print("[MAIN] → Solution: Move project to a path without special characters (e.g., C:\\Temp\\Taller3)")
                print("[MAIN] → Falling back to color detector.")
                use_mediapipe = False
        except Exception as e:
            print(f"[MAIN] ✗ MediaPipe not importable (will fallback to color): {e}")
            use_mediapipe = False
    else:
        print("[MAIN] --force-color specified: using color-based detector.")

    # instantiate gesture detector according to availability
    if use_mediapipe:
        # define MediaPipe-based detector class here capturing mp
        class MediaPipeGestureDetector(threading.Thread):
            def __init__(self, event_q: queue.Queue, camera_index=0, mirror=True, pinch_thresh=0.06, frame_queue: queue.Queue | None = None):
                super().__init__(daemon=True)
                self.event_q = event_q
                self.camera_index = camera_index
                self.mirror = mirror
                self.running = False
                self.pinch_thresh = pinch_thresh
                self.mp_hands = mp.solutions.hands
                self.mp_drawing = mp.solutions.drawing_utils
                self.last_pinch = False
                self.pinch_debounce = 0.08
                self._last_pinch_time = 0.0
                self.cap = None
                self.frame_queue = frame_queue

            def run(self):
                hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=2,
                                            min_detection_confidence=0.5, min_tracking_confidence=0.5)
                self.running = True
                print("[MediaPipeGesture] detector started with Hands(max_num_hands=2, min_det=0.5, min_track=0.5)")
                try:
                    while self.running:
                        frame = None
                        if self.frame_queue is not None:
                            try:
                                frame = self.frame_queue.get(timeout=0.5)
                            except Exception:
                                frame = None
                        else:
                            cap = cv2.VideoCapture(self.camera_index)
                            self.cap = cap
                            ret, frame = cap.read()
                            if not ret:
                                time.sleep(0.05)
                                continue
                        if frame is None:
                            continue
                        if self.mirror:
                            frame = cv2.flip(frame, 1)
                        h, w = frame.shape[:2]
                        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = hands.process(img_rgb)
                        # detectors post gesture events; UI receives camera_frame from CameraPreview
                        if results.multi_hand_landmarks:
                            hand = results.multi_hand_landmarks[0]
                            # Get handedness label
                            handedness = None
                            try:
                                if results.multi_handedness:
                                    handedness = results.multi_handedness[0].classification[0].label
                            except Exception:
                                handedness = None
                            
                            # Key landmarks
                            ix = hand.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP].x
                            iy = hand.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP].y
                            tx = hand.landmark[self.mp_hands.HandLandmark.THUMB_TIP].x
                            ty = hand.landmark[self.mp_hands.HandLandmark.THUMB_TIP].y
                            
                            # post normalized pos event (only include frame if detector owns camera)
                            pos_evt = {"type": "gesture", "event": "pos", "x": ix, "y": iy}
                            if handedness is not None:
                                pos_evt["handedness"] = handedness
                            if self.frame_queue is None:
                                try:
                                    pos_evt["frame"] = frame.copy()
                                except Exception:
                                    pass
                            try:
                                self.event_q.put(pos_evt, block=False)
                            except Exception:
                                self.event_q.put(pos_evt)
                            
                            # Pinch detection with pixel distance (like reference code)
                            ix_px = int(ix * w)
                            iy_px = int(iy * h)
                            tx_px = int(tx * w)
                            ty_px = int(ty * h)
                            pinch_d_px = int(math.hypot(ix_px - tx_px, iy_px - ty_px))
                            
                            # Use pixel threshold (reference uses < 40 pixels)
                            now = time.time()
                            is_pinch = pinch_d_px < 50  # slightly more lenient than reference
                            
                            if is_pinch and (not self.last_pinch) and (now - self._last_pinch_time > self.pinch_debounce):
                                self.last_pinch = True
                                self._last_pinch_time = now
                                pinch_evt = {"type": "gesture", "event": "pinch", "x": ix, "y": iy}
                                if handedness is not None:
                                    pinch_evt["handedness"] = handedness
                                print(f"[MediaPipeGesture] PINCH detected! hand={handedness} dist={pinch_d_px}px")
                                try:
                                    self.event_q.put(pinch_evt)
                                except Exception:
                                    pass
                            elif (not is_pinch) and self.last_pinch and (now - self._last_pinch_time > self.pinch_debounce):
                                self.last_pinch = False
                                self._last_pinch_time = now
                                release_evt = {"type": "gesture", "event": "release", "x": ix, "y": iy}
                                if handedness is not None:
                                    release_evt["handedness"] = handedness
                                try:
                                    self.event_q.put(release_evt)
                                except Exception:
                                    pass
                        time.sleep(0.01)
                except Exception as e:
                    print("[MediaPipeGesture] error:", e)
                    traceback.print_exc()
                finally:
                    try:
                        hands.close()
                    except Exception:
                        pass
                    try:
                        if self.cap is not None:
                            self.cap.release()
                    except Exception:
                        pass
                    self.running = False
                    print("[MediaPipeGesture] detector stopped")

            def stop(self):
                self.running = False

        # instantiate MediaPipe-based detector
        # CameraPreview already mirrors frames. Detectors should not re-flip when using shared frame_q.
        gesture = MediaPipeGestureDetector(ev_q, camera_index=args.device_index, mirror=False, pinch_thresh=0.06, frame_queue=frame_q)
        detector_type = "MediaPipe"
    else:
        # fallback to color detector
        # Use skin-tone HSV range for better hand detection
        gesture = ColorGestureDetector(ev_q, camera_index=args.device_index, mirror=False,
                                       hsv_lower=(0,20,70), hsv_upper=(20,150,255), min_area=500, frame_queue=frame_q)
        detector_type = "Color (Skin tone - show your hand)"
        print("[MAIN] Using color detector with skin-tone HSV range. Show your hand to the camera.")

    game = MultimodalGame(ev_q, width=960, height=640, detector_type=detector_type)

    # start components
    started = voice.start()
    if not started:
        print("Voice failed to start. Continuing with gestures only.")
    cam_preview.start()
    gesture.start()

    print("Multimodal app running. Say commands (iniciar juego, izquierda, derecha, captura, salir) or use gestures.")
    try:
        game.run_ui_loop()
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        print("Stopping threads...")
        try:
            voice.stop()
        except Exception:
            pass
        try:
            gesture.stop()
        except Exception:
            pass
        try:
            cam_preview.stop()
        except Exception:
            pass
        try:
            game._do_capture(save_img=False)
        except Exception:
            pass
        print("Exited cleanly.")

if __name__ == "__main__":
    main()