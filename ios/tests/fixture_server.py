"""Local simulator fixture: real buzzer template/scripts, native AAC upload verification."""
import json
from pathlib import Path

import tornado.ioloop
import tornado.web
import tornado.websocket

BUZZER = Path(__file__).resolve().parents[2] / "jparty" / "buzzer"
sockets = set()


class Index(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html", messages=[], theme={}, theme_json="{}")


class Socket(tornado.websocket.WebSocketHandler):
    def open(self):
        sockets.add(self)
        self.send("TOKEN", "native-test-player")
        self.send("PROMPT_RECORD_ANSWER", json.dumps({"prompt": "Native microphone test", "recording_timeout_ms": 700}))

    def send(self, message, text):
        self.write_message({"message": message, "text": text})

    def on_message(self, message):
        # Reloads may send CHECK_IF_EXISTS; the initial state above already restores the player.
        pass

    def on_close(self):
        sockets.discard(self)


class Audio(tornado.web.RequestHandler):
    def post(self):
        upload = self.request.files["audio"][0]
        assert self.get_body_argument("token") == "native-test-player"
        assert self.get_body_argument("purpose") == "answer"
        assert self.get_body_argument("sequence_id").isdigit()
        assert upload.filename.endswith(".m4a")
        assert upload.content_type == "audio/mp4"
        assert len(upload.body) > 100
        assert upload.body[4:8] == b"ftyp", "Expected an MPEG-4 audio container"
        print(f"Verified native M4A upload: {len(upload.body)} bytes", flush=True)
        for socket in tuple(sockets):
            socket.send("JUDGEMENT_RESULT", json.dumps({"verdict": "correct", "transcript": "Native microphone upload received"}))
        self.write({"ok": True})


if __name__ == "__main__":
    app = tornado.web.Application(
        [(r"/", Index), (r"/buzzersocket", Socket), (r"/api/player-audio", Audio)],
        template_path=str(BUZZER / "templates"), static_path=str(BUZZER / "static"),
    )
    app.listen(18080, address="127.0.0.1")
    print("iOS HTTP fixture listening on 127.0.0.1:18080", flush=True)
    tornado.ioloop.IOLoop.current().start()
