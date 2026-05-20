import logging
import ssl
import subprocess
import tempfile
import tornado.escape
import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado.options import define, options

import os
from threading import Thread
import socket

from jparty.environ import root
from jparty.game import Player
from jparty.constants import MAXPLAYERS, PORT, HTTPS_PORT
import json
from jparty.utils import resource_path
from jparty.paths import user_data_dir


define("port", default=PORT, help="run on the given port", type=int)
define("https_port", default=HTTPS_PORT, help="run HTTPS buzzer on the given port", type=int)


def bundled_path(*parts):
    candidates = [
        os.path.join(root, *parts),
        os.path.join(root, "jparty", *parts),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


class Application(tornado.web.Application):
    def __init__(self, controller):
        buzzer_path = bundled_path("buzzer")
        designer_path = bundled_path("designer_site", "game")
        handlers = [
            (r"/", WelcomeHandler),
            (r"/play", BuzzerHandler),
            (r"/designer", DesignerHandler),
            (r"/designer/(.*)", tornado.web.StaticFileHandler, {"path": designer_path, "default_filename": "index.html"}),
            (r"/api/player-audio", PlayerAudioHandler),
            (r"/buzzersocket", BuzzerSocketHandler),
        ]
        settings = dict(
            cookie_secret="",
            template_path=os.path.join(buzzer_path, "templates"),
            static_path=os.path.join(buzzer_path, "static"),
            xsrf_cookies=False,
            websocket_ping_interval=0.19,
        )
        super(Application, self).__init__(handlers, **settings)
        self.controller = controller


class WelcomeHandler(tornado.web.RequestHandler):
    def get(self):
        # Load theme config so the buzzer web page can use theme colors
        try:
            with open(resource_path('theme_config.json'), 'r') as tf:
                theme = json.load(tf)
        except Exception:
            theme = {}
        theme_colors = theme.get('colors', theme)
        theme_json = json.dumps(theme_colors)

        self.render("index.html", messages=BuzzerSocketHandler.cache, theme=theme_colors, theme_json=theme_json)


class BuzzerHandler(tornado.web.RequestHandler):
    def post(self):
        if not self.get_cookie("test"):
            self.set_cookie("test", "test_val")
            logging.info("set cookie")
        else:
            logging.info(f"cookie: {self.get_cookie('test')}")
        # Pass theme to play page too in case it's needed
        try:
            with open(resource_path('theme_config.json'), 'r') as tf:
                theme = json.load(tf)
        except Exception:
            theme = {}
        theme_colors = theme.get('colors', theme)
        theme_json = json.dumps(theme_colors)
        self.render("play.html", messages=BuzzerSocketHandler.cache, theme=theme_colors, theme_json=theme_json)


class DesignerHandler(tornado.web.RequestHandler):
    def get(self):
        self.redirect("/designer/")


class PlayerAudioHandler(tornado.web.RequestHandler):
    def post(self):
        controller = self.application.controller
        token = self.get_body_argument("token", "")
        purpose = self.get_body_argument("purpose", "")
        sequence_id = self.get_body_argument("sequence_id", "")
        audio_files = self.request.files.get("audio", [])
        if not token or not purpose or not audio_files:
            self.set_status(400)
            self.write({"ok": False, "error": "Missing token, purpose, or audio"})
            return

        player = controller.player_with_token(token, None)
        if player is None:
            self.set_status(403)
            self.write({"ok": False, "error": "Unknown player"})
            return

        upload = audio_files[0]
        mime_type = getattr(upload, "content_type", "application/octet-stream")
        controller.player_audio(player, purpose, upload.body, mime_type, sequence_id)
        self.write({"ok": True})


class BuzzerSocketHandler(tornado.websocket.WebSocketHandler):
    cache = []
    cache_size = 400

    def initialize(self):
        # self.name = None
        self.controller = self.application.controller
        self.player = None

    def get_compression_options(self):
        # Non-None enables compression with default options.
        return {}

    def open(self):
        self.set_nodelay(True)

    def send(self, msg, text=""):
        data = {"message": msg, "text": text}
        try:
            self.write_message(data)
            logging.info(f"Sent {data}")
        except:
            logging.error(f"Error sending message {msg}", exc_info=True)

    def check_if_exists(self, token, buzzerColor):
        logging.info(f"buzzer color 1: {buzzerColor}")

        p = self.controller.player_with_token(token, buzzerColor)
        if p is None:
            if token == "":
                logging.info("Buzzer pressed but no associated player")
                self.send("UNUSED_BUZZER")
                return
            logging.info("NEW")
            self.send("NEW", tornado.escape.json_encode({"auto_host_enabled": self.controller.game.auto_host.enabled}))
        else:
            logging.info(f"Reconnected {p}")
            self.player = p
            p.connected = True
            p.waiter = self
            state = p.state()
            state["auto_host_enabled"] = self.controller.game.auto_host.enabled
            self.send("EXISTS", tornado.escape.json_encode(state))

    def on_message(self, message):
        # do this first to kill latency
        if "BUZZ" in message:
            logging.info(f"received buzzer press")
            if self.player == None:
                logging.info(f"no player associated with this buzzer; skipping")
                self.send("UNUSED_BUZZER")
                return
            self.buzz()
            return
        logging.info(f"received json message: {message}")
        parsed = tornado.escape.json_decode(message)
        msg = parsed["message"]
        text = parsed["text"]
        if msg == "NAME":
            buzzerColor = parsed["buzzerColor"]
            logging.info(f"received NAME: {text}")
            self.init_player(text, buzzerColor, parsed.get("displayName", ""))
        elif msg == "CHECK_IF_EXISTS":
            logging.info(f"Checking if {text} exists")
            buzzerColor = None
            if "buzzerColor" in parsed:
                buzzerColor = parsed["buzzerColor"]
            self.check_if_exists(text, buzzerColor)
        elif msg == "WAGER":
            self.wager(text)
        elif msg == "ANSWER":
            self.application.controller.answer(self.player, text)
        elif msg == "CLUE_PICK":
            self.application.controller.select_clue(self.player, text)
        elif msg == "CHALLENGE_REQUEST":
            self.application.controller.challenge_request(self.player)
        elif msg == "CHALLENGE_VOTE":
            self.application.controller.challenge_vote(self.player, text)
        elif msg == "JUDGEMENT_ACCEPT":
            self.application.controller.finalize_auto_judgement()
        elif msg == "START_GAME_VOTE":
            self.application.controller.start_game_vote(self.player)
        elif msg == "PLAY_AGAIN_VOTE":
            self.application.controller.play_again_vote(self.player)
        elif msg == "DISPUTE_REQUEST":
            self.application.controller.dispute_request(self.player)
        elif msg == "DISPUTE_VOTE":
            self.application.controller.dispute_vote(self.player, text)

        else:
            raise Exception("Unknown message")

    def init_player(self, name, buzzerColor, displayName=""):

        if not self.controller.accepting_players:
            logging.info("Game started!")
            self.send("GAMESTARTED")
            return

        if len(self.controller.connected_players) >= MAXPLAYERS:
            self.send("FULL")
            return

        self.player = Player(name, buzzerColor, self, displayName)
        self.application.controller.new_player(self.player)
        logging.info(
            f"New Player: {self.player} {self.request.remote_ip} {self.player.token.hex()}"
        )
        self.send("TOKEN", self.player.token.hex())
        if self.application.controller.game.auto_host.enabled:
            self.send("PROMPT_START_GAME")

    def buzz(self):
        self.application.controller.buzz(self.player)

    def wager(self, text):
        self.application.controller.wager(self.player, int(text))
        self.player.page = "null"

    def toolate(self):
        self.send("TOOLATE")

    def on_close(self):
        pass


class BuzzerController:
    def __init__(self, game):
        self.thread = None
        self.game = game
        tornado.options.parse_command_line()
        self.app = Application(
            self
        )  # this is to remove sleep mode on Macbook network card
        self.port = options.port
        self.https_port = options.https_port
        self.https_enabled = False
        self.connected_players = []
        self.accepting_players = True
        self.start_votes = set()
        self.play_again_votes = set()

    def start(self, threaded=True, tries=0):
        try:
            self.app.listen(self.port)
        except OSError as e:
            if tries>10:
                raise Exception("Cannot find open port")
            self.port += 1
            self.start(threaded, tries+1)
            return

        self.start_https()

        if threaded:
            self.thread = Thread(target=tornado.ioloop.IOLoop.current().start)
            self.thread.setDaemon(True)
            self.thread.start()
        else:
            tornado.ioloop.IOLoop.current().start()

    def restart(self):
        for p in self.connected_players:
            p.waiter.close()
        self.connected_players = []
        self.accepting_players = True

    def start_https(self):
        try:
            cert_path, key_path = self.ensure_https_cert()
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(cert_path, key_path)
            self.app.listen(self.https_port, ssl_options=ssl_ctx)
            self.https_enabled = True
            logging.info(f"HTTPS buzzer server listening at https://{self.localip()}:{self.https_port}")
        except Exception:
            self.https_enabled = False
            logging.exception("Could not start HTTPS buzzer server")

    def ensure_https_cert(self):
        cert_path = os.path.join(user_data_dir, "jparty-local.crt")
        key_path = os.path.join(user_data_dir, "jparty-local.key")
        if os.path.exists(cert_path) and os.path.exists(key_path):
            return cert_path, key_path

        local_ip = self.localip()
        with tempfile.NamedTemporaryFile("w", delete=False) as cfg:
            cfg.write(
                "[req]\n"
                "distinguished_name=req_distinguished_name\n"
                "x509_extensions=v3_req\n"
                "prompt=no\n"
                "[req_distinguished_name]\n"
                "CN=JParty Local\n"
                "[v3_req]\n"
                f"subjectAltName=IP:{local_ip},IP:127.0.0.1,DNS:localhost\n"
            )
            cfg_path = cfg.name

        try:
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-nodes",
                    "-days",
                    "3650",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    key_path,
                    "-out",
                    cert_path,
                    "-config",
                    cfg_path,
                    "-sha256",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            try:
                os.unlink(cfg_path)
            except OSError:
                pass

        return cert_path, key_path

    def buzz(self, player):
        if self.game:
            i_player = self.game.players.index(player)
            self.game.buzz_trigger.emit(i_player)
        else:
            i_player = self.connected_players.index(player)
            self.game.buzz_hint_trigger.emit(i_player)

    def wager(self, player, amount):
        i_player = self.game.players.index(player)
        if (
            self.game.auto_host.enabled
            and self.game.active_question is not None
            and self.game.active_question.dd
            and player is self.game.auto_host.player_in_control
        ):
            self.game.auto_dd_wager_trigger.emit(i_player, amount)
        else:
            self.game.wager_trigger.emit(i_player, amount)

    def answer(self, player, guess):
        if self.game and self.game.auto_host.enabled and self.game.answering_player is player and self.game.active_question is not None:
            self.game.auto_host.receive_text_answer(player, guess)
            player.page = "null"
        elif self.game:
            self.game.answer(player, guess)
            player.page = "null"

    def new_player(self, player):
        self.connected_players.append(player)
        self.game.new_player_trigger.emit()

    def select_clue(self, player, text):
        if not self.game or not self.game.auto_host.enabled:
            return
        try:
            category_index, row = [int(part) for part in str(text).split(",", 1)]
        except (TypeError, ValueError):
            return
        if player is self.game.auto_host.player_in_control:
            self.game.auto_select_clue_trigger.emit(category_index, row)

    def majority_count(self):
        return (len(self.connected_players) // 2) + 1

    def start_game_vote(self, player):
        if not self.game or not self.game.auto_host.enabled or player is None:
            return
        self.start_votes.add(player)
        if self.game.startable() and len(self.start_votes) >= self.majority_count():
            self.game.auto_start_game_trigger.emit()

    def play_again_vote(self, player):
        if not self.game or not self.game.auto_host.enabled or player is None:
            return
        self.play_again_votes.add(player)
        if len(self.play_again_votes) >= self.majority_count():
            self.game.auto_close_game_trigger.emit()

    def dispute_request(self, player):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_host.request_dispute(player)

    def dispute_vote(self, player, choice):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_host.receive_dispute_vote(player, choice)

    def player_audio(self, player, purpose, audio_bytes, mime_type, sequence_id=None):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_host.receive_audio(player, purpose, audio_bytes, mime_type, sequence_id)

    def challenge_request(self, player):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_host.request_challenge(player)

    def challenge_vote(self, player, text):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_host.receive_challenge_vote(player, text)

    def finalize_auto_judgement(self):
        if self.game and self.game.auto_host.enabled:
            self.game.auto_finalize_judgement_trigger.emit()

    @classmethod
    def localip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", options.port))
        return s.getsockname()[0]

    def host(self):
        localip = BuzzerController.localip()
        if self.port == 80:
            return f"{localip}"
        else:
            return f"{localip}:{self.port}"

    def player_url(self, prefer_https=False):
        localip = BuzzerController.localip()
        if prefer_https:
            return f"https://{localip}:{self.https_port}"
        return f"http://{self.host()}"

    def player_with_token(self, token, buzzerColor):
        for p in self.connected_players:
            logging.info(f"{p.token}, {token}")
            if p.token.hex() == token:
                logging.info("PLAYER MATCH")
                return p
            if buzzerColor != None and p.buzzercolor == buzzerColor:
                logging.info("PLAYER MATCH by buzzer color")
                return p
        return None

    def open_wagers(self, players=None):
        if players is None:
            players = self.connected_players

        for p in players:
            p.waiter.send("PROMPTWAGER", str(max(p.score, 0)))
            p.page = "wager"

    def prompt_answers(self):
        for p in self.connected_players:
            p.waiter.send("PROMPTANSWER")
            p.page = "answer"

    def toolate(self):
        for p in self.connected_players:
            p.waiter.send("TOOLATE")
