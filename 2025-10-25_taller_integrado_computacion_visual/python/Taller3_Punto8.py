#!/usr/bin/env python3
"""
voice_command_osc.py

Voice command controller (Google recognizer only) sending clean OSC messages for Processing.

Features included:
- Captura audio con SpeechRecognition + PyAudio (Microphone).
- Reconocimiento con Google Speech Recognition (online).
- Envío de mensajes OSC con python-osc.
- Retroalimentación por voz con pyttsx3 (cada utterance ejecutado en un proceso hijo).
- Matching robusto de comandos (variantes en español/inglés, tokens y fuzzy fallback).
- Envía solo el argumento relevante por OSC (evita duplicated args / typetag "ss").
- Opciones CLI: --osc-ip, --osc-port, --phrase-time-limit, --device-index, --language, --no-tts

Usage:
    python voice_command_osc.py --osc-ip 127.0.0.1 --osc-port 9000 --language es-ES

Requirements:
    pip install SpeechRecognition python-osc pyttsx3 pyaudio
    (En Windows: pip install pywin32 si pyttsx3 no funciona)
    (En Linux: sudo apt install espeak ffmpeg libespeak1 si pyttsx3 falla)
"""

from __future__ import annotations
import argparse
import time
import traceback
import re
from difflib import get_close_matches
import multiprocessing
import os
import signal

import speech_recognition as sr
from pythonosc import udp_client

# -----------------------------
# Command mapping (variants)
# -----------------------------
# Each entry: (keywords_list, canonical_cmd, spoken_response, osc_path, osc_args_default)
# osc_args_default: list of strings to send as OSC args (if empty, we send canonical cmd as sole arg)
COMMAND_MAP = [
    (["iniciar juego", "start game", "comenzar juego", "start"], "start_game", "Iniciando juego", "/game/start", ["start_game"]),
    (["detener juego", "stop game", "parar juego", "stop"], "stop_game", "Deteniendo juego", "/game/stop", ["stop_game"]),
    (["pausa", "pause", "pausar"], "pause", "Pausado", "/game/pause", ["pause"]),
    (["puntaje", "score", "marcador"], "score", "Mostrando puntaje", "/game/score", ["score"]),

    (["izquierda", "a la izquierda", "mover a la izquierda", "mueve a la izquierda", "left"], "left", "Moviendo a la izquierda", "/control/move", ["left"]),
    (["derecha", "a la derecha", "mover a la derecha", "mueve a la derecha", "right"], "right", "Moviendo a la derecha", "/control/move", ["right"]),
    (["arriba", "sube", "up"], "up", "Moviendo arriba", "/control/move", ["up"]),
    (["abajo", "baja", "down"], "down", "Moviendo abajo", "/control/move", ["down"]),

    (["hola", "hello"], "hello", "Hola, listo para recibir comandos", "/app/hello", ["hello"]),
    (["captura", "capture", "foto"], "capture", "Capturando imagen", "/app/capture", ["capture"]),
    (["pinch", "pellizco", "pellizcar"], "pinch", "Pinch recibido", "/gesture/pinch", []),
    (["puño", "fist"], "fist", "Puño detectado", "/gesture/fist", []),
    (["salir", "quit", "cerrar"], "quit", "Cerrando controlador de voz. Hasta luego.", "/app/quit", []),
]

# -----------------------------
# Utilities: normalization/matching
# -----------------------------
def normalize_text(t: str) -> str:
    """Lowercase, remove punctuation (except unicode letters) and collapse spaces."""
    s = (t or "").lower().strip()
    s = re.sub(r"[^\w\sáéíóúüñ]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def match_command(text: str):
    """
    Return a dict with keys: cmd, resp, osc_path, osc_args, matched_kw
    or None if no match.
    Matching strategy:
      1) phrase/word boundary regex for each keyword
      2) token-based match
      3) fuzzy match (difflib) fallback
    """
    if not text:
        return None
    norm = normalize_text(text)
    print(f"[MATCH] normalized recognized text: '{norm}'")

    # 1) phrase/word regex match
    for keywords, canonical, resp, osc_path, osc_args in COMMAND_MAP:
        for kw in keywords:
            kw_norm = normalize_text(kw)
            # word-boundary match (unicode-aware)
            if re.search(r"(?u)\b" + re.escape(kw_norm) + r"\b", norm):
                print(f"[MATCH] phrase match -> '{kw}' => {canonical}")
                return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": kw}

    # 2) token based
    words = norm.split()
    for keywords, canonical, resp, osc_path, osc_args in COMMAND_MAP:
        for kw in keywords:
            if normalize_text(kw) in words:
                print(f"[MATCH] token match -> '{kw}' => {canonical}")
                return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": kw}

    # 3) fuzzy fallback
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
        print(f"[MATCH] fuzzy match -> '{orig_kw}' => {canonical}")
        return {"cmd": canonical, "resp": resp, "osc_path": osc_path, "osc_args": osc_args, "matched_kw": orig_kw}

    print("[MATCH] No match found")
    return None

# -----------------------------
# TTSEngine (process-per-utterance)
# -----------------------------
def _tts_process_worker(text: str, rate=None, volume=None):
    """
    Proceso hijo: crea engine pyttsx3, aplica propiedades y habla el texto.
    Ejecuta engine.runAndWait() y sale.
    """
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
    """
    TTS que lanza un proceso por cada utterance. Más robusto ante bloqueos de pyttsx3.
    """
    def __init__(self, enabled: bool = True, rate: int | None = None, volume: float | None = None):
        self.enabled = bool(enabled)
        self.rate = rate
        self.volume = volume
        self._procs = []  # lista de (Process, start_time)
        print(f"[TTS] Process-based TTS initialized (enabled={self.enabled})")

    def _cleanup_procs(self):
        # limpiar procesos terminados de la lista
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
        if not self.enabled:
            print("[TTS] disabled; not queueing:", text)
            return
        if text is None:
            return
        s = str(text)
        # lanzar proceso hijo
        try:
            p = multiprocessing.Process(target=_tts_process_worker, args=(s, self.rate, self.volume), daemon=True)
            p.start()
            self._procs.append((p, time.time()))
            print(f"[TTS] spawned process pid={p.pid} for utterance: {repr(s)} (active_procs={len(self._procs)})")
            # limpiar procesos terminados de vez en cuando
            if len(self._procs) > 8:
                self._cleanup_procs()
        except Exception as e:
            print("[TTS] failed to spawn process:", e)

    def stop(self):
        # intentar terminar procesos hijos en la lista
        for p, _ in self._procs:
            try:
                if p.is_alive():
                    try:
                        p.terminate()
                    except Exception:
                        try:
                            os.kill(p.pid, signal.SIGTERM)
                        except Exception:
                            pass
                p.join(timeout=0.1)
            except Exception:
                pass
        self._procs = []
        print("[TTS] stopped - child processes terminated")

    def is_worker_alive(self):
        self._cleanup_procs()
        return any(p.is_alive() for p, _ in self._procs)

# -----------------------------
# VoiceCommandController
# -----------------------------
class VoiceCommandController:
    def __init__(self, osc_ip: str = "127.0.0.1", osc_port: int = 9000,
                 phrase_time_limit: float = 5.0, device_index: int | None = None,
                 language: str = "es-ES", enable_tts: bool = True):
        self.recognizer = sr.Recognizer()
        self.phrase_time_limit = float(phrase_time_limit)
        self.device_index = int(device_index) if device_index is not None else None
        self.language = language or "es-ES"
        self.stop_listening_fn = None

        # OSC client
        try:
            self.osc_client = udp_client.SimpleUDPClient(osc_ip, int(osc_port))
            print(f"[OSC] client ready -> {osc_ip}:{osc_port}")
        except Exception as e:
            print("[OSC] Warning: could not create OSC client:", e)
            self.osc_client = None

        # TTS engine
        self.tts = TTSEngine(enabled=enable_tts)

    def _perform_action(self, match: dict, raw_text: str):
        if match is None:
            self.tts.say("No entendí el comando. Repite por favor.")
            print("[ACTION] No command matched.")
            return
        cmd = match["cmd"]
        resp = match["resp"]
        osc_path = match["osc_path"]
        osc_args = match["osc_args"]
        matched_kw = match.get("matched_kw")
        print(f"[ACTION] Comando reconocido: {cmd} (raw: {raw_text}) matched_kw={matched_kw}")

        # Prepare args to send: prefer osc_args (explicit), otherwise send canonical cmd
        if osc_args:
            args_to_send = list(osc_args)
        else:
            args_to_send = [cmd]

        # Send OSC
        if self.osc_client:
            try:
                self.osc_client.send_message(osc_path, args_to_send)
                print(f"[OSC] -> {osc_path} {args_to_send}")
            except Exception as e:
                print("[OSC] Error sending OSC:", e)

        # TTS
        try:
            print("[PERFORM] Preparing to TTS:", repr(resp))
            self.tts.say(resp)
        except Exception as e:
            print("[PERFORM] Error calling tts.say:", e)

        # Local action: quit
        if cmd == "quit":
            self.stop()

    def _callback(self, recognizer, audio):
        """Callback for listen_in_background. Uses Google recognizer."""
        try:
            text = recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            print("[Reconocimiento] No comprendido (UnknownValue).")
            return
        except sr.RequestError as e:
            print("[Reconocimiento] RequestError (Google):", e)
            return
        except Exception as e:
            print("[Reconocimiento] Unexpected recognition error:", e)
            traceback.print_exc()
            return

        if not text:
            return
        print(f"[Reconocimiento] \"{text}\"")
        match = match_command(text)
        if match is None:
            print("[MATCH] No command matched for:", text)
            # fallback: give short TTS feedback
            self.tts.say("No entendí el comando")
            return
        # perform action
        self._perform_action(match, text)

    def start(self, adjust_for_ambient_seconds: float = 1.0) -> bool:
        mic_kwargs = {}
        if self.device_index is not None:
            mic_kwargs["device_index"] = self.device_index
        try:
            with sr.Microphone(**mic_kwargs) as source:
                print("[MIC] Ajustando nivel de ruido ambiente...")
                try:
                    self.recognizer.adjust_for_ambient_noise(source, duration=float(adjust_for_ambient_seconds))
                    print(f"[MIC] Energy threshold: {self.recognizer.energy_threshold}")
                except Exception as e:
                    print("[MIC] Warning: adjust_for_ambient_noise failed:", e)
            print("[MIC] Comenzando escucha en background (Google). Habla cuando quieras...")
            # start background listening
            self.stop_listening_fn = self.recognizer.listen_in_background(
                sr.Microphone(**mic_kwargs),
                self._callback,
                phrase_time_limit=self.phrase_time_limit
            )
            return True
        except Exception as e:
            print("[MIC] Could not start listening (Microphone/PyAudio):", e)
            traceback.print_exc()
            return False

    def stop(self):
        if self.stop_listening_fn:
            try:
                self.stop_listening_fn(wait_for_stop=False)
            except Exception:
                pass
            self.stop_listening_fn = None
        try:
            self.tts.stop()
        except Exception:
            pass
        print("[CONTROLLER] Escucha detenida.")

# -----------------------------
# CLI parsing and entrypoint
# -----------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Voice Command Controller (Google Speech Recognition)")
    parser.add_argument("--osc-ip", default="127.0.0.1", help="OSC destination IP")
    parser.add_argument("--osc-port", default=9000, type=int, help="OSC destination port")
    parser.add_argument("--phrase-time-limit", default=5.0, type=float, help="Max seconds per phrase")
    parser.add_argument("--device-index", default=None, help="Microphone device index (optional)")
    parser.add_argument("--language", default="es-ES", help="Google recognition language (e.g. es-ES or en-US)")
    parser.add_argument("--no-tts", action="store_true", help="Disable TTS")
    args, unknown = parser.parse_known_args()
    if unknown:
        print("Ignoring unknown CLI args (likely from VSCode/Jupyter):", unknown)
    return args

def main():
    args = parse_args()
    print("[MAIN] Starting VoiceCommandController (Google) with:", args)
    controller = VoiceCommandController(
        osc_ip=args.osc_ip,
        osc_port=args.osc_port,
        phrase_time_limit=args.phrase_time_limit,
        device_index=args.device_index,
        language=args.language,
        enable_tts=(not args.no_tts),
    )
    ok = controller.start(adjust_for_ambient_seconds=1.0)
    if not ok:
        print("[MAIN] Controller failed to start. Check microphone / PyAudio.")
        return
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("[MAIN] Interrupted by user.")
    finally:
        controller.stop()

if __name__ == "__main__":
    main()