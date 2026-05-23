#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._send_json({"ok": True})
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
            voice = str(payload.get("voice", "")).strip()
            if not text:
                self.send_error(400, "Missing input")
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                aiff_path = os.path.join(tmpdir, "speech.aiff")
                wav_path = os.path.join(tmpdir, "speech.wav")
                say_command = ["say", "-o", aiff_path]
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
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), TTSHandler)
    print(f"Local macOS TTS server listening at http://{args.host}:{args.port}/v1/audio/speech")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local macOS TTS server.")


if __name__ == "__main__":
    main()
