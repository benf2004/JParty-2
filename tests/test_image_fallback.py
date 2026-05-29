import os
import unittest
from unittest.mock import patch

import requests

from jparty.image_fallback import NOT_FOUND_IMAGE_CONTENT, load_question_image


class FakeQuestion:
    def __init__(self, image_link):
        self.image_link = image_link
        self.image_content = None
        self.text = (
            "I got a ring in 2016 thanks to a thrilling Game 7 win over Steph, "
            "Klay, Dray and these defending champs"
        )
        self.answer = "Golden State Warriors"
        self.category = "Sports"


class FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200, headers=None):
        self._json_data = json_data or {}
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.ok = 200 <= status_code < 400
        self.text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def fallback_config(openai_key="openai-key", pexels_key="pexels-key"):
    return {
        "image_fallback": {
            "use_pexels": True,
            "pexels_api_key": pexels_key,
        },
        "auto_host": {
            "openai_api_key": openai_key,
            "local_llm_base_url": "http://localhost:11434/v1",
            "local_llm_model": "qwen2.5:7b",
        },
    }


class ImageFallbackTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_working_jarchive_image_does_not_call_pexels(self):
        question = FakeQuestion("https://www.j-archive.com/media/2026-05-28_J_29.jpg")

        with patch("jparty.image_fallback.requests.get") as get_mock, patch(
            "jparty.image_fallback.PexelsImageFallback.image_content_for_question"
        ) as fallback_mock:
            get_mock.return_value = FakeResponse(
                content=b"jpeg-bytes",
                headers={"Content-Type": "image/jpeg"},
            )

            content = load_question_image(question, fallback_config())

        self.assertEqual(content, b"jpeg-bytes")
        fallback_mock.assert_not_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_missing_jarchive_image_uses_local_llm_and_pexels(self):
        question = FakeQuestion("https://www.j-archive.com/media/2026-05-28_J_29.jpg")
        pexels_json = {
            "photos": [
                {
                    "src": {
                        "large": "https://images.pexels.com/photos/basketball.jpeg",
                    }
                }
            ]
        }

        with patch("jparty.image_fallback.local_llm_available", return_value=True), patch(
            "jparty.image_fallback.requests.post"
        ) as post_mock, patch("jparty.image_fallback.requests.get") as get_mock:
            post_mock.return_value = FakeResponse(
                json_data={"choices": [{"message": {"content": '{"query": "basketball championship team"}'}}]},
                content=b"{}",
            )
            get_mock.side_effect = [
                FakeResponse(
                    content=b"<html>not found</html>",
                    status_code=404,
                    headers={"Content-Type": "text/html"},
                ),
                FakeResponse(json_data=pexels_json, content=b"{}", headers={"Content-Type": "application/json"}),
                FakeResponse(content=b"pexels-image", headers={"Content-Type": "image/jpeg"}),
            ]

            content = load_question_image(question, fallback_config())

        self.assertEqual(content, b"pexels-image")
        self.assertEqual(question.image_fallback_source, "pexels")
        self.assertEqual(question.image_fallback_query, "basketball championship team")
        self.assertEqual(question.image_link, "https://images.pexels.com/photos/basketball.jpeg")
        self.assertEqual(post_mock.call_args.args[0], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(get_mock.call_args_list[1].kwargs["headers"]["Authorization"], "pexels-key")
        self.assertEqual(get_mock.call_args_list[1].kwargs["params"]["query"], "basketball championship team")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_missing_non_jarchive_image_does_not_use_pexels(self):
        question = FakeQuestion("https://example.com/missing.jpg")

        with patch("jparty.image_fallback.requests.get") as get_mock, patch(
            "jparty.image_fallback.PexelsImageFallback.image_content_for_question"
        ) as fallback_mock:
            get_mock.return_value = FakeResponse(
                content=b"<html>not found</html>",
                status_code=404,
                headers={"Content-Type": "text/html"},
            )

            content = load_question_image(question, fallback_config())

        self.assertEqual(content, NOT_FOUND_IMAGE_CONTENT)
        fallback_mock.assert_not_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_jarchive_timeout_does_not_use_pexels(self):
        question = FakeQuestion("https://www.j-archive.com/media/2026-05-28_J_29.jpg")

        with patch("jparty.image_fallback.requests.get", side_effect=requests.exceptions.Timeout), patch(
            "jparty.image_fallback.PexelsImageFallback.image_content_for_question"
        ) as fallback_mock:
            content = load_question_image(question, fallback_config())

        self.assertEqual(content, NOT_FOUND_IMAGE_CONTENT)
        fallback_mock.assert_not_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_openai_generates_query_when_local_llm_is_unavailable(self):
        question = FakeQuestion("https://www.j-archive.com/media/2026-05-28_J_29.jpg")
        pexels_json = {
            "photos": [
                {
                    "src": {
                        "large2x": "https://images.pexels.com/photos/arena.jpeg",
                    }
                }
            ]
        }

        with patch("jparty.image_fallback.local_llm_available", return_value=False), patch(
            "jparty.image_fallback.requests.post"
        ) as post_mock, patch("jparty.image_fallback.requests.get") as get_mock:
            post_mock.return_value = FakeResponse(
                json_data={"choices": [{"message": {"content": '{"query": "professional basketball arena"}'}}]},
                content=b"{}",
            )
            get_mock.side_effect = [
                FakeResponse(
                    content=b"<html>not found</html>",
                    status_code=404,
                    headers={"Content-Type": "text/html"},
                ),
                FakeResponse(json_data=pexels_json, content=b"{}", headers={"Content-Type": "application/json"}),
                FakeResponse(content=b"pexels-openai-image", headers={"Content-Type": "image/jpeg"}),
            ]

            content = load_question_image(question, fallback_config(openai_key="saved-openai-key"))

        self.assertEqual(content, b"pexels-openai-image")
        self.assertEqual(post_mock.call_args.args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(post_mock.call_args.kwargs["headers"]["Authorization"], "Bearer saved-openai-key")
        self.assertEqual(get_mock.call_args_list[1].kwargs["params"]["query"], "professional basketball arena")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "PEXELS_API_KEY": ""})
    def test_missing_pexels_key_skips_fallback(self):
        question = FakeQuestion("https://www.j-archive.com/media/2026-05-28_J_29.jpg")

        with patch("jparty.image_fallback.requests.get") as get_mock, patch(
            "jparty.image_fallback.requests.post"
        ) as post_mock:
            get_mock.return_value = FakeResponse(
                content=b"<html>not found</html>",
                status_code=404,
                headers={"Content-Type": "text/html"},
            )

            content = load_question_image(question, fallback_config(pexels_key=""))

        self.assertEqual(content, NOT_FOUND_IMAGE_CONTENT)
        post_mock.assert_not_called()
        self.assertEqual(get_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
