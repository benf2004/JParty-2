#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class KokoCloneAdapterHandler(BaseHTTPRequestHandler):
    cloner = None
    reference_audio = ""
    language = "en"
    lock = threading.Lock()

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"ok": True, "engine": "kokoclone"})
            return
        if self.path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "kokoclone", "object": "model"},
                ],
            })
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
            if not text:
                self.send_error(400, "Missing input")
                return

            language = str(payload.get("language", self.language)).strip() or self.language
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output:
                output_path = output.name
            try:
                with self.lock:
                    self.cloner.generate(
                        text=text,
                        lang=language,
                        reference_audio=self.reference_audio,
                        output_path=output_path,
                    )
                with open(output_path, "rb") as audio_file:
                    audio = audio_file.read()
            finally:
                try:
                    os.remove(output_path)
                except OSError:
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as exc:
            self.send_error(500, f"KokoClone TTS failed: {exc}")

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args), flush=True)

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="OpenAI-compatible adapter for KokoClone.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8892, type=int)
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--reference-audio", required=True)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    os.chdir(args.repo_dir)
    sys.path.insert(0, args.repo_dir)
    from core.cloner import KokoClone

    print("Loading KokoClone models. First start can take a while.", flush=True)
    KokoCloneAdapterHandler.cloner = KokoClone()
    KokoCloneAdapterHandler.reference_audio = args.reference_audio
    KokoCloneAdapterHandler.language = args.language

    server = ThreadingHTTPServer((args.host, args.port), KokoCloneAdapterHandler)
    print(f"KokoClone adapter listening at http://{args.host}:{args.port}/v1/audio/speech", flush=True)
    print(f"Reference voice: {args.reference_audio}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping KokoClone adapter.", flush=True)


if __name__ == "__main__":
    main()
