#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_WORDS_PER_MINUTE = 185


def say_voices():
    result = subprocess.run(["say", "-v", "?"], check=True, capture_output=True, text=True)
    voices = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(?P<name>.+?)\s{2,}(?P<language>[a-z]{2}[_-][A-Z]{2})\s+#\s*(?P<sample>.*)$", line)
        if match:
            voices.append({
                "id": match.group("name").strip(),
                "object": "voice",
                "name": match.group("name").strip(),
                "language": match.group("language"),
                "sample": match.group("sample").strip(),
            })
        elif line.strip():
            voices.append({
                "id": line.strip(),
                "object": "voice",
                "name": line.strip(),
            })
    return voices


def say_rate(speed):
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.6, min(speed, 1.6))
    return str(int(DEFAULT_WORDS_PER_MINUTE * speed))


class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._send_json({"ok": True, "engine": "macos-say"})
            return
        if self.path == "/v1/audio/voices":
            self._send_json({"object": "list", "data": say_voices()})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(payload.get("input", "")).strip()
            voice = str(payload.get("voice", "") or os.environ.get("JPARTY_MACOS_TTS_VOICE", "")).strip()
            speed = payload.get("speed")
            if not text:
                self.send_error(400, "Missing input")
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                aiff_path = os.path.join(tmpdir, "speech.aiff")
                wav_path = os.path.join(tmpdir, "speech.wav")
                say_command = ["say", "-o", aiff_path, "-r", say_rate(speed)]
                if voice:
                    say_command.extend(["-v", voice])
                say_command.append(text)
                subprocess.run(say_command, check=True)
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", aiff_path, wav_path],
                    check=True,
                )
                with open(wav_path, "rb") as audio_file:
                    audio = audio_file.read()

            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as exc:
            self.send_error(500, f"TTS failed: {exc}")

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Local OpenAI-compatible macOS TTS bridge for JParty.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8880, type=int)
    parser.add_argument("--list-voices", action="store_true", help="List macOS voices visible to the built-in speech system and exit.")
    args = parser.parse_args()

    if args.list_voices:
        for voice in say_voices():
            language = voice.get("language", "")
            sample = voice.get("sample", "")
            print(f"{voice['name']}\t{language}\t{sample}")
        return

    server = ThreadingHTTPServer((args.host, args.port), TTSHandler)
    print(f"Local macOS TTS server listening at http://{args.host}:{args.port}/v1/audio/speech")
    print("Use System Settings > Accessibility > Personal Voice to allow apps, then set Local TTS voice to the exact voice name from `say -v ?`.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local macOS TTS server.")


if __name__ == "__main__":
    main()
