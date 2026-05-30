import json
import hashlib
import html
import logging
import os
import random
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

try:
    import requests
except ImportError:
    requests = None
try:
    import simpleaudio as sa
except ImportError:
    sa = None

from jparty.paths import user_data_dir
from jparty.constants import AUTO_HOST_DAILY_DOUBLE_TIMEOUT

DEFAULT_AUTO_HOST_CONFIG = {
    "enabled": False,
    "ai_provider": "openai",
    "tts_voice": "coral",
    "local_llm_base_url": "http://localhost:11434/v1",
    "local_llm_model": "qwen2.5:7b",
    "local_stt_base_url": "http://localhost:8082/v1",
    "local_stt_model": "whisper",
    "local_tts_base_url": "http://localhost:8880/v1",
    "local_tts_model": "macos-say",
    "local_tts_preset": "macos_say",
    "local_tts_voice": "",
    "selection_mode": "voice_with_gui_fallback",
    "answer_judging": "auto_with_challenge",
    "leniency": "normal",
    "auto_judge_confidence": 0.82,
    "host_review_confidence": 0.55,
    "speech_normalization": True,
}

HOST_TTS_INSTRUCTIONS = (
    "Sound like a warm, lively game-show host with natural rises and pauses. "
    "Keep the pace upbeat and clear, add a touch of anticipation, and do not "
    "add extra words."
)

DEFAULT_HOST_TTS_SPEED = 1.12

CORRECT_FEEDBACK_LINES = [
    "Yes! That's right, {player}.",
    "Correct! Nice pull, {player}.",
    "That's it, {player}. Well played.",
    "Right you are, {player}.",
    "You got it, {player}.",
]

INCORRECT_FEEDBACK_LINES = [
    "No, sorry.",
    "Not quite.",
    "Sorry, that's not it.",
    "No, we can't take that.",
    "Good try, but no.",
]

NEXT_CLUE_LINES = [
    "{player}, you're in control. Pick the next clue.",
    "{player}, the board is yours. Choose the next clue.",
    "{player}, keep it rolling. Pick the next clue.",
    "{player}, where are we going next?",
    "{player}, you're in control.",
    "{player}, Pick the next clue.",
    "{player}, the board is yours.",
    "{player}, keep it rolling.",
]

TTS_KEEP_SPELLED_WORDS = {
    "AI",
    "API",
    "BBC",
    "CIA",
    "DNA",
    "DVD",
    "FBI",
    "HTML",
    "HTTP",
    "JFK",
    "MLB",
    "NASA",
    "NBA",
    "NFL",
    "NHL",
    "TV",
    "UK",
    "UN",
    "US",
    "USA",
    "USSR",
    "WWW",
}


@dataclass
class Judgement:
    is_correct: bool
    confidence: float
    reason: str
    transcript: str


class AutoHostAI:
    def __init__(self, config):
        self.config = DEFAULT_AUTO_HOST_CONFIG.copy()
        self.config.update(config or {})
        self.provider = self.config.get("ai_provider", "openai")
        self._speech_lock = threading.Lock()
        self._speech_normalization_cache = {}

    def api_key(self):
        return os.environ.get("OPENAI_API_KEY") or self.config.get("openai_api_key", "")

    def transcribe(self, audio_bytes, mime_type="audio/webm"):
        if not audio_bytes:
            return ""

        api_key = self.api_key()
        if self.provider == "openai" and api_key:
            if requests is None:
                logging.error("Auto Host OpenAI transcription requires the requests package")
                return ""
            return self._openai_transcribe(audio_bytes, mime_type, api_key)
        if self.provider == "local":
            if requests is None:
                logging.error("Auto Host local transcription requires the requests package")
                return ""
            return self._local_transcribe(audio_bytes, mime_type)

        logging.info("Auto Host transcription skipped because no provider/API key is configured")
        return ""

    def parse_clue_selection(self, transcript, board):
        transcript = (transcript or "").strip()
        if not transcript or board is None:
            return None

        parsed = self._heuristic_parse_clue(transcript, board)
        if parsed is not None:
            return parsed

        api_key = self.api_key()
        if self.provider == "openai" and api_key:
            if requests is None:
                logging.error("Auto Host OpenAI clue parsing requires the requests package")
                return None
            parsed = self._openai_parse_clue(transcript, board, api_key)
            if parsed is not None:
                return parsed
        if self.provider == "local":
            if requests is None:
                logging.error("Auto Host local clue parsing requires the requests package")
                return None
            parsed = self._local_parse_clue(transcript, board)
            if parsed is not None:
                return parsed

        return None

    def judge_answer(self, clue, transcript, leniency="normal"):
        transcript = (transcript or "").strip()
        if not transcript or clue is None:
            return Judgement(False, 0.0, "No answer was captured.", transcript)

        fast_judgement = self._fast_judge_answer(clue, transcript)
        if fast_judgement is not None:
            return fast_judgement
        fast_rejection = self._fast_reject_answer(clue, transcript)
        if fast_rejection is not None:
            return fast_rejection

        api_key = self.api_key()
        if self.provider == "openai" and api_key:
            if requests is None:
                logging.error("Auto Host OpenAI answer judging requires the requests package")
                return self._heuristic_judge_answer(clue, transcript)
            judged = self._openai_judge_answer(clue, transcript, leniency, api_key)
            if judged is not None:
                return judged
        if self.provider == "local":
            if requests is None:
                logging.error("Auto Host local answer judging requires the requests package")
                return self._heuristic_judge_answer(clue, transcript)
            judged = self._local_judge_answer(clue, transcript, leniency)
            if judged is not None:
                return judged

        return self._heuristic_judge_answer(clue, transcript)

    def speech_file(self, text, purpose="host"):
        text = (text or "").strip()
        api_key = self.api_key()
        if not text or requests is None:
            return None

        if self.provider == "local":
            return self._local_speech_file(text, purpose)

        if self.provider != "openai" or not api_key:
            return None

        voice = self.config.get("tts_voice", "coral")
        model = os.environ.get("JPARTY_TTS_MODEL", "gpt-4o-mini-tts")
        speed = self._tts_speed()
        cache_dir = os.path.join(user_data_dir, "auto_host_audio_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{model}|{voice}|{speed}|{HOST_TTS_INSTRUCTIONS}|{purpose}|{text}".encode("utf-8")
        ).hexdigest()
        path = os.path.join(cache_dir, f"{cache_key}.wav")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path

        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "voice": voice,
                    "input": text,
                    "instructions": HOST_TTS_INSTRUCTIONS,
                    "response_format": "wav",
                    "speed": speed,
                },
                timeout=45,
            )
            response.raise_for_status()
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as audio_file:
                audio_file.write(response.content)
            os.replace(tmp_path, path)
            return path
        except Exception:
            logging.exception("Auto Host TTS generation failed")
            return None

    def _openai_transcribe(self, audio_bytes, mime_type, api_key):
        suffix = self._suffix_for_mime(mime_type)
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp.seek(0)
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": os.environ.get("JPARTY_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")},
                files={"file": (f"audio{suffix}", tmp, mime_type or "application/octet-stream")},
                timeout=30,
            )
        response.raise_for_status()
        data = response.json()
        return data.get("text", "").strip()

    def _local_transcribe(self, audio_bytes, mime_type):
        suffix = self._suffix_for_mime(mime_type)
        base_url = self._normalize_base_url(self.config.get("local_stt_base_url"))
        model = self.config.get("local_stt_model", "whisper")
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                tmp.seek(0)
                response = requests.post(
                    f"{base_url}/audio/transcriptions",
                    data={"model": model},
                    files={"file": (f"audio{suffix}", tmp, mime_type or "application/octet-stream")},
                    timeout=float(os.environ.get("JPARTY_LOCAL_STT_TIMEOUT", "30")),
                )
            response.raise_for_status()
            data = response.json()
            return data.get("text", "").strip()
        except Exception:
            logging.exception("Auto Host local transcription failed")
            return ""

    def _openai_parse_clue(self, transcript, board, api_key):
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "clue_selection",
                "schema": {
                    "type": "object",
                    "properties": {
                        "category_index": {"type": "integer"},
                        "value": {"type": "integer"},
                        "needs_gui": {"type": "boolean"},
                    },
                    "required": ["category_index", "value", "needs_gui"],
                    "additionalProperties": False,
                },
            },
        }
        categories = [{"index": i, "name": c} for i, c in enumerate(board.categories)]
        prompt = (
            "Select the Jeopardy clue from this spoken request. "
            "If ambiguous, set needs_gui true.\n"
            f"Categories: {json.dumps(categories)}\n"
            f"Available values: {sorted({q.value for q in board.questions if not q.complete})}\n"
            f"Spoken request: {transcript}"
        )
        data = self._openai_json(
            prompt,
            schema,
            api_key,
            timeout=float(os.environ.get("JPARTY_CLUE_PARSE_TIMEOUT", "4")),
        )
        if not data or data.get("needs_gui"):
            return None
        return self._clue_by_category_value(board, data.get("category_index"), data.get("value"))

    def _openai_judge_answer(self, clue, transcript, leniency, api_key):
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "answer_judgement",
                "schema": {
                    "type": "object",
                    "properties": {
                        "is_correct": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["is_correct", "confidence", "reason"],
                    "additionalProperties": False,
                },
            },
        }
        prompt = (
            "You are judging a Jeopardy answer. Be fair, account for wording variants, "
            "and apply this leniency level: "
            f"{leniency}.\nClue: {clue.text}\nExpected answer: {clue.answer}\n"
            f"Player answer transcript: {transcript}"
        )
        data = self._openai_json(
            prompt,
            schema,
            api_key,
            timeout=float(os.environ.get("JPARTY_JUDGE_TIMEOUT", "8")),
        )
        if not data:
            return None
        return Judgement(
            bool(data.get("is_correct")),
            float(data.get("confidence", 0.0)),
            str(data.get("reason", "")).strip(),
            transcript,
        )

    def _local_parse_clue(self, transcript, board):
        categories = [{"index": i, "name": c} for i, c in enumerate(board.categories)]
        prompt = (
            "Return only JSON for the selected Jeopardy clue. "
            "Use this exact shape: {\"category_index\": 0, \"value\": 200, \"needs_gui\": false}. "
            "If the spoken request is ambiguous, set needs_gui true.\n"
            f"Categories: {json.dumps(categories)}\n"
            f"Available values: {sorted({q.value for q in board.questions if not q.complete})}\n"
            f"Spoken request: {transcript}"
        )
        data = self._local_chat_json(prompt, timeout=float(os.environ.get("JPARTY_LOCAL_CLUE_PARSE_TIMEOUT", "12")))
        if not data or data.get("needs_gui"):
            return None
        return self._clue_by_category_value(board, data.get("category_index"), data.get("value"))

    def _local_judge_answer(self, clue, transcript, leniency):
        prompt = (
            "You are judging a Jeopardy answer. Return only JSON with this exact shape: "
            "{\"is_correct\": true, \"confidence\": 0.0, \"reason\": \"short reason\"}. "
            "Be fair, account for wording variants, and apply this leniency level: "
            f"{leniency}.\nClue: {clue.text}\nExpected answer: {clue.answer}\n"
            f"Player answer transcript: {transcript}"
        )
        data = self._local_chat_json(prompt, timeout=float(os.environ.get("JPARTY_LOCAL_JUDGE_TIMEOUT", "20")))
        if not data:
            return None
        return Judgement(
            bool(data.get("is_correct")),
            float(data.get("confidence", 0.0)),
            str(data.get("reason", "")).strip(),
            transcript,
        )

    def _local_chat_json(self, prompt, timeout=30):
        try:
            base_url = self._normalize_base_url(self.config.get("local_llm_base_url"))
            model = self.config.get("local_llm_model", "qwen2.5:7b")
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_json_object(content)
        except Exception:
            logging.exception("Auto Host local structured request failed")
            return None

    def _local_speech_file(self, text, purpose):
        voice = self.config.get("local_tts_voice", "")
        model = self.config.get("local_tts_model", "macos-say")
        base_url = self._normalize_base_url(self.config.get("local_tts_base_url"))
        speed = self._tts_speed()
        spoken_text = self._tts_spoken_text(text, model)
        cache_dir = os.path.join(user_data_dir, "auto_host_audio_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha256(
            f"local|{base_url}|{model}|{voice}|{speed}|{purpose}|{spoken_text}".encode("utf-8")
        ).hexdigest()
        path = os.path.join(cache_dir, f"{cache_key}.wav")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path

        with self._speech_lock:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return path
            return self._generate_local_speech_file(base_url, model, voice, speed, spoken_text, path)

    def _generate_local_speech_file(self, base_url, model, voice, speed, text, path):
        try:
            response = self._post_local_speech(base_url, model, voice, speed, text)
            if not response.ok:
                if (
                    model == "macos-say"
                    and "Unsupported model: macos-say" in getattr(response, "text", "")
                ):
                    logging.error(
                        "Auto Host is configured for macOS Personal Voice, but %s is not the macOS say bridge. "
                        "Run scripts/stop_full_local_auto_host_macos.sh, then scripts/start_full_local_auto_host_macos.sh.",
                        base_url,
                    )
                logging.error(
                    "Auto Host local TTS returned %s from %s: %s",
                    response.status_code,
                    base_url,
                    response.text[:500],
                )
                response.raise_for_status()
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as audio_file:
                audio_file.write(response.content)
            os.replace(tmp_path, path)
            return path
        except Exception as exc:
            logging.warning("Auto Host local TTS generation skipped: %s", exc)
            return None

    def _post_local_speech(self, base_url, request_model, voice, speed, text):
        timeout = float(os.environ.get("JPARTY_LOCAL_TTS_TIMEOUT", self._local_tts_default_timeout(base_url)))
        attempts = int(os.environ.get("JPARTY_LOCAL_TTS_ATTEMPTS", "2"))
        last_error = None
        for attempt in range(max(1, attempts)):
            try:
                return requests.post(
                    f"{base_url}/audio/speech",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": request_model,
                        "voice": voice,
                        "input": text,
                        "response_format": "wav",
                        "speed": speed,
                    },
                    timeout=timeout,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                logging.warning(
                    "Auto Host local TTS connection failed at %s; retrying once: %s",
                    base_url,
                    exc,
                )
                time.sleep(1.0)
        raise last_error

    def _local_tts_default_timeout(self, base_url):
        return "45"

    def should_preload_audio(self):
        return True

    def should_preload_speech_text(self):
        return (
            self.provider == "local"
            and self.config.get("speech_normalization", True)
            and requests is not None
        )

    def _tts_spoken_text(self, text, model):
        text = html.unescape(text or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.replace("_", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if model in ("kokoro",):
            text = self._soften_all_caps_for_tts(text)
        return text

    def _soften_all_caps_for_tts(self, text):
        def replace_word(match):
            word = match.group(0)
            normalized = re.sub(r"[^A-Z0-9]", "", word)
            if normalized in TTS_KEEP_SPELLED_WORDS:
                return word
            if len(normalized) <= 2 or any(char.isdigit() for char in normalized):
                return word
            if not re.search(r"[AEIOUY]", normalized):
                return word
            return word.lower()

        return re.sub(r"\b[A-Z][A-Z0-9'-]{2,}\b", replace_word, text)

    def normalize_clue_for_speech(self, text):
        original = html.unescape(text or "")
        original = re.sub(r"<[^>]+>", " ", original)
        original = re.sub(r"\s+", " ", original).strip()
        fallback = self._basic_speech_normalize(original)
        if (
            not self.config.get("speech_normalization", True)
            or self.provider != "local"
            or requests is None
        ):
            return fallback

        base_url = self._normalize_base_url(self.config.get("local_llm_base_url"))
        model = self.config.get("local_llm_model", "qwen2.5:7b")
        cache_key = (base_url, model, original)
        if cache_key in self._speech_normalization_cache:
            return self._speech_normalization_cache[cache_key]

        normalized = self._local_normalize_speech_text(original)
        if normalized:
            normalized = self._basic_speech_normalize(normalized)
        if not self._plausible_speech_normalization(original, normalized):
            normalized = fallback
        self._speech_normalization_cache[cache_key] = normalized
        return normalized

    def _local_normalize_speech_text(self, text):
        prompt = (
            "You prepare Jeopardy clues for text-to-speech. Keep the clue EXACTLY the same "
            "words, but expand the abbreviations so that they are pronounced correctly when passed through text to speech. Expand abbreviations, symbols, "
            "initialisms with periods, and number shorthand like \"No. 1\" into "
            "\"number one\". Preserve the clue's meaning and facts. Do not in any circumstance answer "
            "the clue. Do not add commentary. Do not change anything else. Return only JSON with this exact "
            "shape: {\"spoken_text\": \"...\"}.\n"
            f"Clue: {text}"
        )
        data = self._local_chat_json(
            prompt,
            timeout=float(os.environ.get("JPARTY_LOCAL_SPEECH_NORMALIZE_TIMEOUT", "15")),
        )
        if not data:
            return None
        return str(data.get("spoken_text", "")).strip()

    def _basic_speech_normalize(self, text):
        text = html.unescape(text or "")
        text = re.sub(r"<[^>]+>", " ", text)

        def number_abbrev(match):
            number_text = match.group(1)
            return f"number {self._small_number_to_words(number_text) or number_text}"

        replacements = [
            (r"\b[Nn]o\.\s*(\d+)\b", number_abbrev),
            (r"#\s*(\d+)\b", number_abbrev),
            (r"\b[Ss]t\.", "Saint"),
            (r"\b[Mm]t\.", "Mount"),
            (r"\b[Dd]r\.", "Doctor"),
            (r"\b[Mm]r\.", "Mister"),
            (r"\b[Mm]rs\.", "Misses"),
            (r"\b[Mm]s\.", "Miz"),
            (r"\b[Jj]r\.", "Junior"),
            (r"\b[Ss]r\.", "Senior"),
            (r"\be\.g\.", "for example"),
            (r"\bi\.e\.", "that is"),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        text = text.replace("&", " and ")
        return re.sub(r"\s+", " ", text).strip()

    def _small_number_to_words(self, value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        words = {
            0: "zero",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
            11: "eleven",
            12: "twelve",
            13: "thirteen",
            14: "fourteen",
            15: "fifteen",
            16: "sixteen",
            17: "seventeen",
            18: "eighteen",
            19: "nineteen",
            20: "twenty",
        }
        return words.get(number)

    def _plausible_speech_normalization(self, original, normalized):
        if not normalized:
            return False
        if "{" in normalized or "}" in normalized:
            return False
        if len(normalized) > max(len(original) * 3, len(original) + 120):
            return False
        return True

    def _tts_speed(self):
        return float(os.environ.get("JPARTY_TTS_SPEED", DEFAULT_HOST_TTS_SPEED))

    def _openai_json(self, prompt, response_format, api_key, timeout=30):
        try:
            model = os.environ.get("JPARTY_JUDGE_MODEL", "gpt-5-nano")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": response_format,
            }
            if not model.startswith("gpt-5"):
                payload["temperature"] = 0
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            logging.exception("Auto Host OpenAI structured request failed")
            return None

    def _parse_json_object(self, content):
        content = (content or "").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None

    def _normalize_base_url(self, base_url):
        return (base_url or "").rstrip("/")

    def _heuristic_parse_clue(self, transcript, board):
        text = self._normalize(transcript)
        value = self._parse_clue_value(text, board)
        if value is None:
            return None

        best_index = None
        best_score = 0
        for i, category in enumerate(board.categories):
            category_text = self._normalize(category)
            score = SequenceMatcher(None, category_text, text).ratio()
            if category_text in text:
                score += 0.5
            category_number_match = re.search(r"\bcategory\s+(\d+)\b", text)
            if category_number_match and int(category_number_match.group(1)) == i + 1:
                score += 0.6
            category_word_match = re.search(r"\bcategory\s+(one|two|three|four|five|six)\b", text)
            if category_word_match:
                category_words = ["one", "two", "three", "four", "five", "six"]
                if category_words.index(category_word_match.group(1)) == i:
                    score += 0.6
            ordinal_match = re.search(r"\b(first|second|third|fourth|fifth|sixth)\s+category\b", text)
            if ordinal_match:
                ordinals = ["first", "second", "third", "fourth", "fifth", "sixth"]
                if ordinals.index(ordinal_match.group(1)) == i:
                    score += 0.6
            if score > best_score:
                best_index = i
                best_score = score

        if best_index is None or best_score < 0.35:
            return None
        return self._clue_by_category_value(board, best_index, value)

    def _parse_clue_value(self, text, board):
        value_match = re.search(r"\b(\d{3,4})\b", text)
        if value_match:
            return int(value_match.group(1))

        values = sorted({q.value for q in board.questions if not q.complete}, reverse=True)
        for value in values:
            if self._normalize(self._value_to_words(value)) in text:
                return value

        row_words = {
            "top": 0,
            "first": 0,
            "second": 1,
            "third": 2,
            "fourth": 3,
            "fifth": 4,
            "bottom": 4,
        }
        for word, row in row_words.items():
            if re.search(rf"\b{word}\s+(row|clue)\b", text):
                row_values = sorted({q.value for q in board.questions if q.index[1] == row and not q.complete})
                if row_values:
                    return row_values[0]
        return None

    def _value_to_words(self, value):
        names = {
            100: "one hundred",
            200: "two hundred",
            300: "three hundred",
            400: "four hundred",
            500: "five hundred",
            600: "six hundred",
            800: "eight hundred",
            1000: "one thousand",
            1200: "twelve hundred",
            1600: "sixteen hundred",
            2000: "two thousand",
        }
        return names.get(int(value), str(value))

    def _heuristic_judge_answer(self, clue, transcript):
        expected = self._normalize_answer(clue.answer)
        given = self._normalize_answer(transcript)
        ratio = SequenceMatcher(None, expected, given).ratio()
        contains = expected and (expected in given or given in expected)
        is_correct = contains or ratio >= 0.78
        confidence = 0.9 if contains else ratio
        reason = "Matched expected answer." if is_correct else "Did not closely match expected answer."
        return Judgement(is_correct, confidence, reason, transcript)

    def _fast_judge_answer(self, clue, transcript):
        expected = self._normalize_answer(clue.answer)
        given = self._normalize_answer(transcript)
        if not expected or not given:
            return None

        ratio = SequenceMatcher(None, expected, given).ratio()
        extra_words_match = expected in given and len(expected) >= 4
        if expected == given or extra_words_match or ratio >= 0.93:
            return Judgement(True, 0.98, "Fast match to expected answer.", transcript)
        return None

    def _fast_reject_answer(self, clue, transcript):
        expected = self._normalize_answer(clue.answer)
        given = self._normalize_answer(transcript)
        if not expected or not given:
            return None

        ratio = SequenceMatcher(None, expected, given).ratio()
        shared_words = set(expected.split()) & set(given.split())
        if ratio <= 0.12 and not shared_words:
            return Judgement(False, 0.97, "Fast rejection; answer did not resemble expected response.", transcript)
        return None

    def _clue_by_category_value(self, board, category_index, value):
        try:
            category_index = int(category_index)
            value = int(value)
        except (TypeError, ValueError):
            return None
        for q in sorted(board.questions, key=lambda clue: (clue.index[1], clue.index[0])):
            if q.index[0] == category_index and q.value == value and not q.complete:
                return q
        return None

    def _normalize(self, value):
        value = (value or "").lower()
        value = re.sub(r"[^a-z0-9 ]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def _normalize_answer(self, value):
        value = self._normalize(value)
        value = re.sub(r"^(what|who|where|when|why|how) (is|are|was|were) ", "", value)
        value = re.sub(r"^(a|an|the) ", "", value)
        return value.strip()

    def _suffix_for_mime(self, mime_type):
        if "wav" in (mime_type or ""):
            return ".wav"
        if "mp4" in (mime_type or "") or "m4a" in (mime_type or ""):
            return ".m4a"
        if "ogg" in (mime_type or ""):
            return ".ogg"
        return ".webm"


class AutoHostController:
    def __init__(self, game):
        self.game = game
        self.config = self._config()
        self.ai = AutoHostAI(self.config)
        self.player_in_control = None
        self.pending_judgement = None
        self.challenge_votes = {}
        self.challenge_open = False
        self.last_resolved_clue = None
        self.dispute_open = False
        self.dispute_votes = {}
        self.dispute_counts = {}
        self._dispute_timer = None
        self._finalize_timer = None
        self._suppress_next_board_prompt = False
        self._resume_clue_selection_after_dispute = False

    @property
    def enabled(self):
        return bool(self._config().get("enabled", False))

    def _config(self):
        config = getattr(self.game, "config", {}) or {}
        merged = DEFAULT_AUTO_HOST_CONFIG.copy()
        merged.update(config.get("auto_host", {}) or {})
        return merged

    def refresh_config(self):
        self.config = self._config()
        self.ai = AutoHostAI(self.config)

    def on_new_player(self, player):
        if not self.enabled:
            return
        if self.player_in_control is None:
            self.set_player_in_control(player)
        self.preload_buzz_acknowledgement(player)

    def on_game_started(self):
        self.refresh_config()
        self.dispute_counts = {}
        self._resume_clue_selection_after_dispute = False
        if not self.enabled or not self.game.players:
            return
        if self.player_in_control not in self.game.players:
            self.set_player_in_control(self.game.players[0])
        self.preload_round_audio(self.game.current_round)
        for player in self.game.players:
            self.preload_buzz_acknowledgement(player)
        self.play_intro_then_prompt()

    def after_back_to_board(self):
        if not self.enabled or not self.game.current_round or self.game.current_round.__class__.__name__ == "FinalBoard":
            return
        if self.game.active_question is not None:
            return
        if self._suppress_next_board_prompt:
            self._suppress_next_board_prompt = False
            return
        if all(q.complete for q in self.game.current_round.questions):
            return
        if self.player_in_control is None and self.game.players:
            self.set_player_in_control(self.game.players[0])
        threading.Thread(target=self._speak_next_clue_then_prompt, daemon=True).start()

    def set_player_in_control(self, player):
        self.player_in_control = player
        if self.game.host_display is not None:
            self.game.set_player_in_control(player)

    def prompt_clue_selection(self):
        if self.dispute_open:
            self._resume_clue_selection_after_dispute = True
            return
        player = self.player_in_control
        if not player or not player.waiter:
            return
        payload = self.board_payload()
        payload["auto_start_delay_ms"] = 800
        player.page = "select"
        player.auto_payload = payload
        player.waiter.send("PROMPT_SELECT_CLUE", json.dumps(payload))
        for other_player in self.game.players:
            if other_player is not player and other_player.waiter:
                other_player.waiter.send(
                    "AUTO_HOST_CONTROLS",
                    json.dumps({"can_dispute": self.can_request_dispute()}),
                )
        player.waiter.send(
            "AUTO_HOST_CONTROLS",
            json.dumps({"can_dispute": self.can_request_dispute()}),
        )

    def board_payload(self):
        board = self.game.current_round
        if board is None:
            return {"categories": [], "clues": []}
        clues = []
        for q in sorted(board.questions, key=lambda clue: (clue.index[1], clue.index[0])):
            clues.append({
                "category_index": q.index[0],
                "row": q.index[1],
                "category": q.category,
                "value": q.value,
                "complete": q.complete,
            })
        return {"categories": board.categories, "clues": clues}

    def select_clue(self, category_index, row):
        if not self.enabled or self.game.current_round is None or self.game.active_question is not None:
            return
        clue = self.game.current_round.get_question(int(category_index), int(row))
        if clue is not None and not clue.complete:
            self.last_resolved_clue = None
            for player in self.game.players:
                if player.waiter:
                    player.waiter.send("AUTO_HOST_CONTROLS", json.dumps({"can_dispute": False}))
            self.send_all_to_buzz()
            self.game.load_question(clue)

    def send_all_to_buzz(self):
        if self.dispute_open:
            return
        for player in self.game.players:
            player.page = "buzz"
            player.auto_payload = {}
            if player.waiter:
                player.waiter.send("PROMPT_BUZZ")
                player.waiter.send(
                    "AUTO_HOST_CONTROLS",
                    json.dumps({"can_dispute": self.can_request_dispute()}),
                )

    def on_clue_loaded(self, clue):
        if clue is None:
            self.game.auto_open_responses_trigger.emit()
            return
        threading.Thread(target=self._read_clue_then_open, args=(clue,), daemon=True).start()

    def preload_round_audio(self, board):
        if not self.enabled or board is None:
            return
        include_audio = self.ai.should_preload_audio()
        if not include_audio and not self.ai.should_preload_speech_text():
            return
        threading.Thread(target=self._preload_round_audio, args=(board, include_audio), daemon=True).start()

    def preload_buzz_acknowledgement(self, player):
        if not self.enabled or player is None or not self.ai.should_preload_audio():
            return
        threading.Thread(
            target=self.ai.speech_file,
            args=(self.buzz_acknowledgement_text(player), f"buzz-{self._player_name(player)}"),
            daemon=True,
        ).start()

    def play_intro_then_prompt(self):
        threading.Thread(target=self._play_intro_then_prompt, daemon=True).start()

    def intro_text(self):
        board = self.game.current_round
        categories = self.category_announcement_text(getattr(board, "categories", []))
        player_name = self._player_name(self.player_in_control)
        return (
            "Welcome to JParty. I'll be your host for this game. "
            f"Today's categories are: {categories} "
            f"{player_name}, you joined first, so you have control. Please pick the first clue."
        )

    def clue_text(self, clue):
        if clue is None:
            return ""
        cached = getattr(clue, "_auto_host_spoken_text", None)
        if cached:
            return cached
        spoken_text = self.ai.normalize_clue_for_speech(getattr(clue, "text", ""))
        setattr(clue, "_auto_host_spoken_text", spoken_text)
        return spoken_text

    def category_announcement_text(self, categories):
        categories = [str(category).strip() for category in (categories or []) if str(category).strip()]
        if not categories:
            return "The categories are still loading."
        return " ".join(f"{category}." for category in categories)

    def daily_double_prompt_text(self, player, max_wager):
        return (
            f"Daily Double. {self._player_name(player)}, you can wager up to {max_wager}. "
            "Please say or enter your wager."
        )

    def correct_feedback_text(self, player):
        return random.choice(CORRECT_FEEDBACK_LINES).format(player=self._player_name(player))

    def incorrect_feedback_text(self):
        return random.choice(INCORRECT_FEEDBACK_LINES)

    def buzz_acknowledgement_text(self, player):
        return f"{self._player_name(player)}?"

    def stumped_text(self, clue):
        if clue is None:
            return "Time is up."
        return f"The correct response was: {clue.answer}."

    def next_clue_prompt_text(self):
        return random.choice(NEXT_CLUE_LINES).format(player=self._player_name(self.player_in_control))

    def _preload_round_audio(self, board, include_audio=True):
        if include_audio:
            self.ai.speech_file(self.intro_text(), "intro")
        for clue in sorted(board.questions, key=lambda q: (q.index[1], q.index[0])):
            if not clue.complete:
                text = self.clue_text(clue)
                if include_audio:
                    self.ai.speech_file(text, f"clue-{clue.index[0]}-{clue.index[1]}")

    def _play_intro_then_prompt(self):
        self._play_text_and_wait(self.intro_text(), "intro")
        self.prompt_clue_selection()

    def on_round_started(self):
        if not self.enabled or not self.game.current_round:
            return
        self.preload_round_audio(self.game.current_round)
        threading.Thread(target=self._announce_round_started, daemon=True).start()

    def _announce_round_started(self):
        board = self.game.current_round
        if board.__class__.__name__ == "FinalBoard":
            text = self.final_round_text(board)
            self._play_text_and_wait(text, "final-intro")
            return

        text = self.round_intro_text(board)
        self._play_text_and_wait(text, "round-intro")
        self.prompt_clue_selection()

    def round_intro_text(self, board):
        categories = self.category_announcement_text(getattr(board, "categories", []))
        player_name = self._player_name(self.player_in_control)
        round_name = "Double Jeopardy" if getattr(board, "dj", False) else "the next round"
        return (
            f"Great job so far. Welcome to {round_name}. "
            f"The categories are: {categories} "
            f"{player_name}, you have control. Pick the next clue."
        )

    def final_round_text(self, board):
        category = getattr(board, "category", None)
        if not category and getattr(board, "question", None) is not None:
            category = board.question.category
        return f"Welcome to Final Jeopardy. The category is: {category}. Please enter your wagers."

    def final_clue_intro_text(self):
        return "All right, wagers are locked. Here is the Final Jeopardy clue."

    def final_good_luck_text(self):
        return "Good luck!"

    def on_final_wagers_complete(self):
        if not self.enabled:
            return
        threading.Thread(target=self._open_final_then_read_clue, daemon=True).start()

    def _open_final_then_read_clue(self):
        self._play_text_and_wait(self.final_clue_intro_text(), "final-clue-intro")
        self.game.auto_open_final_trigger.emit()
        time.sleep(0.4)
        question = getattr(self.game.current_round, "question", None)
        if question is not None:
            self._play_text_and_wait(self.clue_text(question), "final-clue")
        self._play_text_and_wait(self.final_good_luck_text(), "final-good-luck")
        self.game.auto_final_open_responses_trigger.emit()

    def judge_final_responses(self):
        if not self.enabled:
            return
        threading.Thread(target=self._judge_final_responses, daemon=True).start()

    def _judge_final_responses(self):
        question = getattr(self.game.current_round, "question", None)
        if question is None:
            return
        players = list(getattr(self.game, "players", []))
        if not players:
            return
        time.sleep(float(os.environ.get("JPARTY_FINAL_REVIEW_PAUSE", "3")))
        self._play_text_and_wait("Time is up. Let's see what everyone said.", "final-review-start")
        for _player in sorted(players, key=lambda p: p.score):
            self.game.auto_final_next_player_trigger.emit()
            time.sleep(0.35)
            player = self.game.answering_player
            if player is None:
                return
            self.game.auto_final_show_answer_trigger.emit()
            time.sleep(0.25)
            answer = getattr(player, "finalanswer", "")
            judgement = self.ai.judge_answer(question, answer, self.config.get("leniency", "normal"))
            spoken_answer = answer.strip() if answer and answer.strip() else "no response"
            if judgement.is_correct:
                self._play_text_and_wait(
                    f"{self._player_name(player)} said {spoken_answer}. That's correct.",
                    f"final-correct-{self._player_name(player)}",
                )
                self.game.auto_final_correct_trigger.emit()
            else:
                self._play_text_and_wait(
                    f"{self._player_name(player)} said {spoken_answer}. That's not correct.",
                    f"final-incorrect-{self._player_name(player)}",
                )
                self.game.auto_final_incorrect_trigger.emit()
            time.sleep(0.4)
        self._play_text_and_wait(
            f"The correct Final Jeopardy response was: {question.answer}.",
            "final-answer-reveal",
        )
        self.game.auto_final_next_player_trigger.emit()

    def remember_resolved_clue(self, awarded_player):
        clue = getattr(self.game, "active_question", None)
        if clue is None:
            return
        self.last_resolved_clue = {
            "clue": clue,
            "answer": clue.answer,
            "value": clue.value,
            "awarded_player": awarded_player,
            "answering_player": getattr(self.game, "answering_player", None),
            "was_daily_double": bool(getattr(clue, "dd", False)),
            "was_correct": awarded_player is not None,
        }

    def request_dispute(self, player):
        if (
            not self.can_request_dispute()
            or player not in self.game.players
        ):
            return
        if self.dispute_counts.get(player, 0) >= 5:
            if player.waiter:
                player.waiter.send(
                    "AUTO_HOST_FALLBACK",
                    "You have reached your 5 dispute limit for this game.",
                )
            return
        self.dispute_counts[player] = self.dispute_counts.get(player, 0) + 1
        self.dispute_open = True
        self.dispute_votes = {}
        self._resume_clue_selection_after_dispute = True
        answer = self.last_resolved_clue["answer"]
        message = (
            f"{self._player_name(player)} has disputed the last answer, which was {answer}. "
            "Please vote on who should have received the correct points, if anyone."
        )
        options = [{"id": f"player:{i}", "label": self._player_name(p)} for i, p in enumerate(self.game.players)]
        options.append({"id": "nobody", "label": "Nobody"})
        payload = json.dumps({"message": message, "options": options, "seconds_remaining": 30})
        for voter in self.game.players:
            voter.page = "dispute"
            voter.auto_payload = json.loads(payload)
            if voter.waiter:
                voter.waiter.send("DISPUTE_OPEN", payload)
        threading.Thread(target=self._play_text_and_wait, args=(message, "dispute-open"), daemon=True).start()
        self._start_dispute_timer()

    def can_request_dispute(self):
        board = getattr(self.game, "current_round", None)
        if (
            not self.enabled
            or self.dispute_open
            or not self.last_resolved_clue
            or board is None
            or board.__class__.__name__ == "FinalBoard"
            or getattr(self.game, "active_question", None) is not None
            or getattr(self.game, "answering_player", None) is not None
            or getattr(self.game, "accepting_responses", False)
            or getattr(self.game, "soliciting_player", False)
        ):
            return False
        if self.player_in_control is None or getattr(self.player_in_control, "page", None) != "select":
            return False
        return not all(q.complete for q in getattr(board, "questions", []))

    def receive_dispute_vote(self, player, choice):
        if not self.dispute_open or player not in self.game.players:
            return
        valid_choices = {"nobody"} | {f"player:{i}" for i, _p in enumerate(self.game.players)}
        if choice not in valid_choices:
            return
        self.dispute_votes[player] = choice
        if player.waiter:
            player.waiter.send("DISPUTE_VOTE_RECORDED", "Vote recorded.")
        if len(self.dispute_votes) >= len(self.game.players):
            self.resolve_dispute()

    def resolve_dispute(self):
        if not self.dispute_open:
            return
        self._cancel_dispute_timer()
        self.dispute_open = False
        result = self._dispute_plurality_result()
        if result is None:
            self._send_dispute_result("No clear dispute result. The game continues as normal.")
        else:
            self.apply_dispute_result(result)
        if self._resume_clue_selection_after_dispute:
            self._resume_clue_selection_after_dispute = False
            if (
                self.game.active_question is None
                and self.game.current_round is not None
                and self.game.current_round.__class__.__name__ != "FinalBoard"
                and not all(q.complete for q in self.game.current_round.questions)
            ):
                self.prompt_clue_selection()

    def _dispute_plurality_result(self):
        if not self.dispute_votes:
            return None
        counts = {}
        for choice in self.dispute_votes.values():
            counts[choice] = counts.get(choice, 0) + 1
        top_count = max(counts.values())
        winners = [choice for choice, count in counts.items() if count == top_count]
        if len(winners) != 1:
            return None
        return winners[0]

    def apply_dispute_result(self, result):
        record = self.last_resolved_clue
        if not record:
            return
        old_player = record.get("awarded_player")
        value = int(record.get("value", 0))
        new_player = None
        if str(result).startswith("player:"):
            try:
                new_player = self.game.players[int(result.split(":", 1)[1])]
            except (ValueError, IndexError):
                new_player = None

        if old_player is not None:
            self.game.set_score(old_player, old_player.score - value)
            if self._dispute_should_apply_incorrect_penalty(record, old_player, new_player):
                self.game.set_score(old_player, old_player.score - value)

        if new_player is not None:
            correction = value
            if self._dispute_should_restore_incorrect_penalty(record, new_player, old_player):
                correction += value
            self.game.set_score(new_player, new_player.score + correction)
            self.game.set_player_in_control(new_player)
            self.player_in_control = new_player
            message = f"Dispute accepted. {self._player_name(new_player)} receives the points."
        else:
            message = "Dispute accepted. Nobody receives the points."
        record["awarded_player"] = new_player
        record["was_correct"] = new_player is not None
        self._send_dispute_result(message)
        threading.Thread(target=self._play_text_and_wait, args=(message, "dispute-result"), daemon=True).start()

    def _dispute_should_apply_incorrect_penalty(self, record, old_player, new_player):
        return (
            bool(record.get("was_correct"))
            and self._record_was_daily_double(record)
            and self._wrong_answers_subtract_points()
            and self._record_answering_player(record, old_player) is old_player
            and new_player is not old_player
        )

    def _dispute_should_restore_incorrect_penalty(self, record, new_player, old_player):
        if record.get("was_correct"):
            return False
        answering_player = record.get("answering_player")
        if answering_player is None:
            return new_player is not old_player
        return self._wrong_answers_subtract_points() and new_player is answering_player

    def _record_was_daily_double(self, record):
        clue = record.get("clue")
        return bool(record.get("was_daily_double", getattr(clue, "dd", False)))

    def _record_answering_player(self, record, fallback=None):
        return record.get("answering_player") or fallback

    def _wrong_answers_subtract_points(self):
        config = getattr(self.game, "config", {}) or {}
        return str(config.get("allownegative", "True")).lower() == "true"

    def _send_dispute_result(self, message):
        for player in self.game.players:
            player.page = "buzz"
            player.auto_payload = {}
            if player.waiter:
                player.waiter.send("DISPUTE_RESULT", message)

    def _start_dispute_timer(self):
        self._cancel_dispute_timer()
        self._dispute_timer = threading.Timer(30.0, self.resolve_dispute)
        self._dispute_timer.daemon = True
        self._dispute_timer.start()

    def _cancel_dispute_timer(self):
        if self._dispute_timer:
            self._dispute_timer.cancel()
            self._dispute_timer = None

    def _read_clue_then_open(self, clue):
        self._play_text_and_wait(self.clue_text(clue), f"clue-{clue.index[0]}-{clue.index[1]}")
        self.game.auto_open_responses_trigger.emit()

    def _play_text_and_wait(self, text, purpose):
        path = self.ai.speech_file(text, purpose)
        if not path or sa is None:
            return
        try:
            play_obj = sa.WaveObject.from_wave_file(path).play()
            play_obj.wait_done()
        except Exception:
            logging.exception("Auto Host failed to play TTS audio")

    def acknowledge_buzz(self, player):
        if not self.enabled:
            return
        self.prompt_answer_wait(player)
        threading.Thread(target=self._acknowledge_buzz_then_record, args=(player,), daemon=True).start()

    def _acknowledge_buzz_then_record(self, player):
        self._play_text_and_wait(self.buzz_acknowledgement_text(player), f"buzz-{self._player_name(player)}")
        self.prompt_answer(player, auto_start=True)

    def speak_feedback(self, text, purpose):
        if not self.enabled:
            return
        threading.Thread(target=self._play_text_and_wait, args=(text, purpose), daemon=True).start()

    def announce_stumped(self, clue):
        if not self.enabled:
            return
        threading.Thread(target=self._announce_stumped_then_board, args=(clue,), daemon=True).start()

    def _announce_stumped_then_board(self, clue):
        self._play_text_and_wait(self.stumped_text(clue), "stumped")
        self.game.auto_back_to_board_trigger.emit()

    def briefly_prompt_next_clue(self):
        if not self.enabled or self.player_in_control is None:
            return
        self.speak_feedback(self.next_clue_prompt_text(), "next-clue")

    def _speak_next_clue_then_prompt(self):
        if not self.enabled or self.player_in_control is None:
            return
        self._play_text_and_wait(self.next_clue_prompt_text(), "next-clue")
        if self.dispute_open:
            self._resume_clue_selection_after_dispute = True
            return
        self.prompt_clue_selection()

    def receive_audio(self, player, purpose, audio_bytes, mime_type, sequence_id=None):
        if not self.enabled or self.dispute_open:
            return
        threading.Thread(
            target=self._process_audio,
            args=(player, purpose, audio_bytes, mime_type, sequence_id),
            daemon=True,
        ).start()

    def _process_audio(self, player, purpose, audio_bytes, mime_type, sequence_id):
        try:
            transcript = self.ai.transcribe(audio_bytes, mime_type)
            logging.info("Auto Host transcript for %s: %s", purpose, transcript)
            if purpose == "clue_selection":
                if not transcript.strip():
                    self._send_player_needs_gui(player, "I did not catch that. Please try speaking again or tap a clue.")
                    return
                if player is not self.player_in_control or player.page != "select" or self.game.active_question is not None:
                    return
                clue = self.ai.parse_clue_selection(transcript, self.game.current_round)
                if clue is None:
                    self._send_player_needs_gui(player, "Could not identify the clue. Please tap one.")
                    return
                if player is not self.player_in_control or player.page != "select" or self.game.active_question is not None:
                    return
                self.game.auto_select_clue_trigger.emit(clue.index[0], clue.index[1])
            elif purpose == "answer":
                if not transcript.strip():
                    self.prompt_answer(player, auto_start=False, message="I did not catch an answer. Tap record and try again.")
                    return
                self.game.auto_answer_text_trigger.emit(self.game.players.index(player), transcript)
            elif purpose == "daily_double_wager":
                amount = self._parse_amount(transcript)
                if amount is None:
                    self._send_player_needs_gui(player, "Could not identify the wager. Please type it.")
                    return
                self.game.auto_dd_wager_trigger.emit(self.game.players.index(player), amount)
        except Exception:
            logging.exception("Auto Host audio processing failed")
            self._send_player_needs_gui(player, "Audio processing failed. Please use the on-screen fallback.")

    def receive_text_answer(self, player, answer):
        if not self.enabled or player is None:
            return
        self.game.auto_answer_text_trigger.emit(self.game.players.index(player), answer)

    def judge_answer(self, player_index, transcript):
        if not self.enabled or self.game.active_question is None:
            return
        if not (transcript or "").strip():
            player = self.game.players[player_index]
            self.prompt_answer(player, auto_start=False, message="I did not catch an answer. Tap record and try again.")
            return
        player = self.game.players[player_index]
        if self.game.answering_player is not player:
            return
        judgement = self.ai.judge_answer(
            self.game.active_question,
            transcript,
            self.config.get("leniency", "normal"),
        )
        self.open_pending_judgement(player, judgement)

    def open_pending_judgement(self, player, judgement):
        self.pending_judgement = {"player": player, "judgement": judgement}
        self.challenge_votes = {}
        self.challenge_open = False
        self.finalize_pending_judgement()

    def request_challenge(self, player):
        if not self.pending_judgement or self.pending_judgement["player"] is not player:
            return
        self.challenge_open = True
        self._cancel_finalize_timer()
        payload = json.dumps({"answering_player": self._player_name(player)})
        voters = [p for p in self.game.players if p is not player]
        for voter in voters:
            voter.page = "challenge"
            voter.auto_payload = json.loads(payload)
            voter.waiter.send("CHALLENGE_OPEN", payload)
        if not voters:
            self.finalize_pending_judgement()
        else:
            self._start_finalize_timer()

    def receive_challenge_vote(self, player, vote_text):
        if not self.pending_judgement or not self.challenge_open:
            return
        if player is self.pending_judgement["player"]:
            return
        vote = str(vote_text).lower() == "correct"
        self.challenge_votes[player] = vote
        player.page = "buzz"
        player.waiter.send("CHALLENGE_RESULT", json.dumps({"recorded": True}))
        voters = [p for p in self.game.players if p is not self.pending_judgement["player"]]
        if len(self.challenge_votes) >= len(voters):
            self.finalize_pending_judgement()

    def finalize_pending_judgement(self):
        if not self.pending_judgement:
            return
        judgement = self.pending_judgement["judgement"]
        is_correct = judgement.is_correct
        if self.challenge_votes:
            correct_votes = sum(1 for v in self.challenge_votes.values() if v)
            incorrect_votes = sum(1 for v in self.challenge_votes.values() if not v)
            if correct_votes > incorrect_votes:
                is_correct = True
            elif incorrect_votes > correct_votes:
                is_correct = False

        self._cancel_finalize_timer()
        player = self.pending_judgement["player"]
        judgement_payload = {
            "verdict": "correct" if is_correct else "incorrect",
            "confidence": judgement.confidence,
            "reason": judgement.reason,
            "transcript": judgement.transcript,
            "can_challenge": False,
        }
        self.pending_judgement = None
        self.challenge_votes = {}
        self.challenge_open = False
        correct_prompt_player = None
        daily_double_incorrect_clue = None
        for p in self.game.players:
            p.auto_payload = {}
            if p.page in ("judgement", "challenge"):
                p.page = "buzz"
        if is_correct:
            self.remember_resolved_clue(player)
            self._suppress_next_board_prompt = True
            self.game.correct_answer()
            correct_prompt_player = player
        else:
            self.remember_resolved_clue(None)
            if getattr(self.game.active_question, "dd", False):
                daily_double_incorrect_clue = self.game.active_question
                self._suppress_next_board_prompt = True
            else:
                self.speak_feedback(self.incorrect_feedback_text(), "incorrect-feedback")
            self.game.incorrect_answer()
        final_wagering_started = self._current_round_is_final() and getattr(player, "page", None) == "wager"
        if player.waiter and not final_wagering_started:
            player.waiter.send("JUDGEMENT_RESULT", json.dumps(judgement_payload))
        if correct_prompt_player is not None and not self._current_round_is_final():
            threading.Thread(
                target=self._speak_correct_then_prompt_next_clue,
                args=(correct_prompt_player,),
                daemon=True,
            ).start()
        if daily_double_incorrect_clue is not None and not self._current_round_is_final():
            threading.Thread(
                target=self._speak_daily_double_incorrect_then_prompt_next_clue,
                args=(daily_double_incorrect_clue,),
                daemon=True,
            ).start()
        if not is_correct and self.game.active_question is not None and player.waiter:
            player.waiter.send("CHALLENGE_RESULT", json.dumps({"final": "incorrect"}))

    def _speak_correct_then_prompt_next_clue(self, player):
        self._play_text_and_wait(self.correct_feedback_text(player), "correct-feedback")
        if not self._can_prompt_next_clue():
            return
        if self.player_in_control is None:
            self.player_in_control = player
        self._speak_next_clue_then_prompt()

    def _speak_daily_double_incorrect_then_prompt_next_clue(self, clue):
        self._play_text_and_wait(self.incorrect_feedback_text(), "daily-double-incorrect-feedback")
        self._play_text_and_wait(self.stumped_text(clue), "daily-double-answer-reveal")
        if not self._can_prompt_next_clue():
            return
        self._speak_next_clue_then_prompt()

    def _current_round_is_final(self):
        board = getattr(self.game, "current_round", None)
        return board is not None and board.__class__.__name__ == "FinalBoard"

    def _can_prompt_next_clue(self):
        board = getattr(self.game, "current_round", None)
        if not self.enabled or getattr(self.game, "active_question", None) is not None:
            return False
        if board is None or board.__class__.__name__ == "FinalBoard":
            return False
        return not all(q.complete for q in getattr(board, "questions", []))

    def prompt_answer(self, player, auto_start=False, message="Speak now", recording_timeout_ms=None):
        if not self.enabled or not player or not player.waiter:
            return
        player.page = "buzz"
        player.auto_payload = {
            "answer_state": "ready",
            "prompt": message,
            "auto_start": auto_start,
        }
        if recording_timeout_ms is not None:
            player.auto_payload["recording_timeout_ms"] = recording_timeout_ms
        payload = json.dumps(player.auto_payload)
        player.waiter.send("PROMPT_RECORD_ANSWER_AUTO" if auto_start else "PROMPT_RECORD_ANSWER", payload)

    def prompt_answer_wait(self, player):
        if not self.enabled or not player or not player.waiter:
            return
        player.page = "buzz"
        player.auto_payload = {
            "answer_state": "waiting",
            "prompt": "Wait to talk...",
        }
        player.waiter.send("PROMPT_WAIT_ANSWER", json.dumps(player.auto_payload))

    def prompt_daily_double_wager(self):
        if not self.enabled or not self.player_in_control:
            return False
        player = self.player_in_control
        max_wager = self.max_daily_double_wager(player)
        self.game.answering_player = player
        player.page = "dd_wager"
        player.auto_payload = {"max_wager": max_wager}
        player.waiter.send("PROMPT_DD_WAGER", str(max_wager))
        threading.Thread(
            target=self._prompt_daily_double_wager_after_sound,
            args=(player, max_wager),
            daemon=True,
        ).start()
        return True

    def _prompt_daily_double_wager_after_sound(self, player, max_wager):
        time.sleep(1.6)
        self._play_text_and_wait(self.daily_double_prompt_text(player, max_wager), "daily-double")

    def apply_daily_double_wager(self, player_index, amount):
        if not self.enabled or self.game.active_question is None:
            return
        player = self.game.players[player_index]
        if player is not self.player_in_control:
            return
        max_wager = self.max_daily_double_wager(player)
        try:
            wager = int(amount)
        except (TypeError, ValueError):
            self.retry_daily_double_wager(player, max_wager)
            return
        if wager < 0 or wager > max_wager:
            self.retry_daily_double_wager(player, max_wager)
            return
        self.game.active_question.value = wager
        self.game.keystroke_manager.activate("CORRECT_ANSWER", "INCORRECT_ANSWER")
        self.game.dc.question_widget.show_question()
        threading.Thread(
            target=self._read_daily_double_clue_then_record,
            args=(player, self.game.active_question),
            daemon=True,
        ).start()

    def _read_daily_double_clue_then_record(self, player, clue):
        self._play_text_and_wait(self.clue_text(clue), f"dd-clue-{clue.index[0]}-{clue.index[1]}")
        self.prompt_answer(player, auto_start=True, recording_timeout_ms=AUTO_HOST_DAILY_DOUBLE_TIMEOUT * 1000)

    def retry_daily_double_wager(self, player, max_wager):
        message = f"That wager is not valid. You can wager from 0 to {max_wager}. Try again."
        player.page = "dd_wager"
        player.auto_payload = {"max_wager": max_wager}
        if player.waiter:
            player.waiter.send("PROMPT_DD_WAGER", str(max_wager))
            player.waiter.send("AUTO_HOST_FALLBACK", message)
        threading.Thread(
            target=self._play_text_and_wait,
            args=(message, "daily-double-invalid-wager"),
            daemon=True,
        ).start()

    def max_daily_double_wager(self, player):
        if self.game.current_round is self.game.data.rounds[0]:
            return max(player.score, 1000)
        return max(player.score, 2000)

    def _send_player_needs_gui(self, player, message):
        if player and player.waiter:
            player.waiter.send("AUTO_HOST_FALLBACK", message)

    def _parse_amount(self, transcript):
        text = (transcript or "").lower().replace(",", "")
        if self.player_in_control is not None and any(
            phrase in text
            for phrase in (
                "true daily double",
                "all in",
                "all-in",
                "all of it",
                "everything",
                "max",
                "maximum",
            )
        ):
            return self.max_daily_double_wager(self.player_in_control)
        match = re.search(r"\b(\d+)\b", text)
        if match:
            return int(match.group(1))
        return self._parse_spoken_number(text)

    def _parse_spoken_number(self, text):
        words = re.findall(r"[a-z]+", text)
        if not words:
            return None
        ones = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
        }
        tens = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }
        total = 0
        current = 0
        found = False
        for word in words:
            if word == "and":
                continue
            if word in ones:
                current += ones[word]
                found = True
            elif word in tens:
                current += tens[word]
                found = True
            elif word == "hundred":
                current = max(current, 1) * 100
                found = True
            elif word in ("thousand", "grand"):
                total += max(current, 1) * 1000
                current = 0
                found = True
            else:
                continue
        if not found:
            return None
        return total + current

    def _start_finalize_timer(self):
        self._cancel_finalize_timer()
        self._finalize_timer = threading.Timer(8.0, self.game.auto_finalize_judgement_trigger.emit)
        self._finalize_timer.daemon = True
        self._finalize_timer.start()

    def _cancel_finalize_timer(self):
        if self._finalize_timer:
            self._finalize_timer.cancel()
            self._finalize_timer = None

    def _player_name(self, player):
        display_name = getattr(player, "display_name", "")
        if display_name:
            return str(display_name)
        name = getattr(player, "name", "")
        return "Player" if str(name).startswith("data:image") else str(name)
