import html
import json
import logging
import os
import re
import time
from urllib.parse import urlparse

import requests

from jparty.constants import DEFAULT_CONFIG


NOT_FOUND_IMAGE_CONTENT = b"Not Found"
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

_LOCAL_LLM_AVAILABILITY_CACHE = {}
_LOCAL_LLM_CACHE_SECONDS = 30


class ImageUnavailable(Exception):
    def __init__(self, message, allow_fallback=False):
        super().__init__(message)
        self.allow_fallback = allow_fallback


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _merged_auto_host_config(config):
    auto_host = DEFAULT_CONFIG["auto_host"].copy()
    auto_host.update((config or {}).get("auto_host", {}) or {})
    return auto_host


def image_fallback_config(config):
    fallback = DEFAULT_CONFIG["image_fallback"].copy()
    fallback.update((config or {}).get("image_fallback", {}) or {})
    return fallback


def openai_api_key(config):
    auto_host = _merged_auto_host_config(config)
    return os.environ.get("OPENAI_API_KEY") or auto_host.get("openai_api_key", "")


def pexels_api_key(config):
    fallback = image_fallback_config(config)
    return os.environ.get("PEXELS_API_KEY") or fallback.get("pexels_api_key", "")


def _normalize_base_url(base_url):
    return (base_url or "").rstrip("/")


def local_llm_available(auto_host_config, timeout=None):
    base_url = _normalize_base_url(auto_host_config.get("local_llm_base_url"))
    model = auto_host_config.get("local_llm_model")
    if not base_url or not model:
        return False

    timeout = _float_env("JPARTY_LOCAL_LLM_CHECK_TIMEOUT", timeout or 0.6)
    cache_key = (base_url, model)
    now = time.time()
    cached = _LOCAL_LLM_AVAILABILITY_CACHE.get(cache_key)
    if cached and now - cached[0] < _LOCAL_LLM_CACHE_SECONDS:
        return cached[1]

    available = False
    try:
        response = requests.get(f"{base_url}/models", timeout=timeout)
        available = bool(response.ok)
    except requests.exceptions.RequestException:
        available = False

    _LOCAL_LLM_AVAILABILITY_CACHE[cache_key] = (now, available)
    return available


def pexels_llm_available(config, check_local=True):
    if openai_api_key(config):
        return True
    if not check_local:
        return False
    return local_llm_available(_merged_auto_host_config(config))


def is_jarchive_media_link(link):
    if not isinstance(link, str):
        return False
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower()
    return host in {"j-archive.com", "www.j-archive.com"} and parsed.path.startswith("/media/")


def load_question_image(question, config, timeout=3):
    try:
        return _load_direct_image(question.image_link, timeout=timeout)
    except ImageUnavailable as exc:
        if is_jarchive_media_link(question.image_link) and exc.allow_fallback:
            fallback_content = PexelsImageFallback(config).image_content_for_question(question)
            if fallback_content:
                return fallback_content
            logging.info("Pexels fallback could not replace missing J-Archive image: %s", exc)
        else:
            logging.info("Image unavailable without J-Archive fallback: %s", exc)
    except OSError:
        logging.info("failed to load local image: %s", question.image_link, exc_info=True)

    return NOT_FOUND_IMAGE_CONTENT


def _load_direct_image(link, timeout=3):
    if not link:
        raise ImageUnavailable("No image link is configured")

    if isinstance(link, str) and link.lower().startswith(("http://", "https://")):
        return _download_remote_image(link, timeout=timeout)

    with open(link, "rb") as image_file:
        return image_file.read()


def _download_remote_image(link, timeout=3):
    try:
        response = requests.get(link, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise ImageUnavailable(f"Remote image request failed for {link}") from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        allow_fallback = getattr(response, "status_code", None) == 404
        raise ImageUnavailable(
            f"Remote image returned HTTP {getattr(response, 'status_code', 'error')} for {link}",
            allow_fallback=allow_fallback,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise ImageUnavailable(f"Remote image request failed for {link}") from exc

    if not _response_looks_like_image(response):
        raise ImageUnavailable(
            f"Remote image response was not an image for {link}",
            allow_fallback=True,
        )

    return response.content


def _response_looks_like_image(response):
    content = getattr(response, "content", b"") or b""
    if not content:
        return False

    start = content[:512].lstrip().lower()
    if start.startswith((b"<!doctype html", b"<html")) or b"<html" in start:
        return False

    if _content_has_image_signature(content):
        return True

    content_type = (getattr(response, "headers", {}) or {}).get("Content-Type", "").lower()
    if content_type and "image/" not in content_type:
        return False

    return True


def _content_has_image_signature(content):
    return (
        content.startswith(b"\xff\xd8")
        or content.startswith(b"\x89PNG\r\n\x1a\n")
        or content.startswith((b"GIF87a", b"GIF89a"))
        or content.startswith(b"BM")
        or (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
    )


class PexelsImageFallback:
    def __init__(self, config):
        self.config = config or {}
        self.fallback_config = image_fallback_config(self.config)
        self.auto_host_config = _merged_auto_host_config(self.config)

    def image_content_for_question(self, question):
        if not self.enabled():
            return None

        original_link = question.image_link
        query = self.query_for_question(question)
        if not query:
            logging.info("Pexels fallback skipped because no LLM query was generated")
            return None

        photo_url = self.search_photo_url(query)
        if not photo_url:
            logging.info("Pexels fallback found no photo for query: %s", query)
            return None

        try:
            content = _download_remote_image(
                photo_url,
                timeout=_float_env("JPARTY_PEXELS_IMAGE_TIMEOUT", "8"),
            )
        except ImageUnavailable:
            logging.info("Pexels fallback photo could not be downloaded: %s", photo_url, exc_info=True)
            return None

        question.image_link = photo_url
        question.image_content = content
        question.image_fallback_source = "pexels"
        question.image_fallback_query = query
        question.image_fallback_original_link = original_link
        logging.info("Loaded Pexels fallback image for query '%s': %s", query, photo_url)
        return content

    def enabled(self):
        return bool(self.fallback_config.get("use_pexels") and self.api_key())

    def api_key(self):
        return pexels_api_key(self.config)

    def query_for_question(self, question):
        query = None
        if local_llm_available(self.auto_host_config):
            query = self._query_from_local_llm(question)
            if query:
                return query
            logging.info("Local LLM did not return a usable Pexels query")

        api_key = openai_api_key(self.config)
        if api_key:
            return self._query_from_openai(question, api_key)

        logging.info("Pexels fallback skipped because no local LLM or OpenAI API key is available")
        return None

    def search_photo_url(self, query):
        try:
            response = requests.get(
                PEXELS_SEARCH_URL,
                headers={"Authorization": self.api_key()},
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "landscape",
                },
                timeout=_float_env("JPARTY_PEXELS_SEARCH_TIMEOUT", "8"),
            )
            response.raise_for_status()
            photos = response.json().get("photos", [])
        except Exception:
            logging.exception("Pexels search request failed")
            return None

        if not photos:
            return None

        src = photos[0].get("src", {}) or {}
        return (
            src.get("large2x")
            or src.get("large")
            or src.get("medium")
            or src.get("original")
        )

    def _query_from_local_llm(self, question):
        data = self._local_chat_json(
            self._query_prompt(question),
            timeout=_float_env("JPARTY_LOCAL_PEXELS_QUERY_TIMEOUT", "15"),
        )
        return _sanitize_query((data or {}).get("query"))

    def _query_from_openai(self, question, api_key):
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "pexels_image_query",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
        data = self._openai_json(
            self._query_prompt(question),
            schema,
            api_key,
            timeout=_float_env("JPARTY_OPENAI_PEXELS_QUERY_TIMEOUT", "12"),
        )
        return _sanitize_query((data or {}).get("query"))

    def _local_chat_json(self, prompt, timeout=30):
        try:
            base_url = _normalize_base_url(self.auto_host_config.get("local_llm_base_url"))
            model = self.auto_host_config.get("local_llm_model", "qwen2.5:7b")
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
            return _parse_json_object(content)
        except Exception:
            logging.exception("Pexels fallback local LLM query failed")
            return None

    def _openai_json(self, prompt, response_format, api_key, timeout=30):
        try:
            model = os.environ.get("JPARTY_IMAGE_QUERY_MODEL", "gpt-5-nano")
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
            logging.exception("Pexels fallback OpenAI query failed")
            return None

    def _query_prompt(self, question):
        return (
            "Create the best Pexels stock photo search query for replacing a missing "
            "image in a Jeopardy-style clue. Return only JSON with this exact shape: "
            "{\"query\": \"short visual search phrase\"}. Use the correct response "
            "as the main subject when the clue points to 'this', 'these', or another "
            "referent. Prefer concrete visual nouns and context words. Avoid words "
            "like Jeopardy, clue, screenshot, or J-Archive.\n"
            f"Category: {_plain_text(getattr(question, 'category', ''))}\n"
            f"Clue: {_plain_text(getattr(question, 'text', ''))}\n"
            f"Correct response: {_plain_text(getattr(question, 'answer', ''))}"
        )


def _parse_json_object(content):
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


def _plain_text(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_query(query):
    query = _plain_text(query).strip(" \"'")
    query = re.sub(r"\s+", " ", query)
    if len(query) < 2:
        return None
    return query[:120]
