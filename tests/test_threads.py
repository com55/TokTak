"""Threads regression tests; never import/start the live bot."""
import ast
import asyncio
import html
import importlib.util
import re
import types
import unittest
from pathlib import Path
from typing import Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urljoin, urlparse

import aiohttp


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("threads_under_test", ROOT / "module/threads.py")
threads = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(threads)
SHARE = "https://www.threads.com/share/Example123"
FIXER = "https://fixthreads.seria.moe/share/Example123"
VIDEO = "https://scontent.cdninstagram.com/clip.mp4?x=1&y=2"
IMAGE = "https://scontent.fbcdn.net/photo.jpg"


class Response:
    def __init__(self, status=200, content_type="text/html", body="", location=None, delay=0):
        self.status = status
        self.content_type = content_type
        self.body = body
        self.headers = {} if location is None else {"Location": location}
        self.delay = delay
        self.closed = False
        self.reads = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()

    async def text(self):
        self.reads += 1
        await asyncio.sleep(self.delay)
        return self.body

    def close(self):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def metadata(kind="og:video", url=VIDEO):
    return f'<meta content="{html.escape(url, quote=True)}"\n property="{kind}">'


def load_main_definitions():
    tree = ast.parse((ROOT / "main.py").read_text())
    nodes = [node for node in tree.body
             if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
             and node.name in {"Validator", "on_message", "send_reply"}]
    for node in nodes:
        node.decorator_list = []
    namespace = dict(
        re=re, urlparse=urlparse, urljoin=urljoin, html=html, asyncio=asyncio,
        Optional=Optional, Tuple=Tuple, get_threads_fixer_url=threads.get_threads_fixer_url,
        threads_media_ok=AsyncMock(return_value=True), FETCHING_MESSAGE="Fetching...",
        discord=types.SimpleNamespace(Message=object, AllowedMentions=types.SimpleNamespace(none=lambda: "none")),
        logger=Mock(), bot=types.SimpleNamespace(channel_ids=[], process_commands=AsyncMock()),
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "main.py"), "exec"), namespace)
    return namespace


class Links(unittest.TestCase):
    def test_accepts_and_normalizes_post_and_share_links(self):
        for host in ("threads.com", "www.threads.com", "threads.net", "www.threads.net"):
            for path in ("/share/Example123", "/@some.user/post/Ab_c-12"):
                with self.subTest(host=host, path=path):
                    self.assertEqual(threads.get_threads_fixer_url(f"https://{host}{path}?xmt=abc#x"),
                                     f"https://fixthreads.seria.moe{path}")

    def test_rejects_invalid_input(self):
        for url in (
            "http://threads.com/share/a", "https://evilthreads.com/share/a",
            "https://threads.com.evil.test/share/a", "https://sub.threads.com/share/a",
            "https://threads.com@evil.test/share/a", "https://x@threads.com/share/a",
            "https://threads.com:444/share/a", "https://threads.com:bad/share/a",
            "https://threads.com/", "https://threads.com/@user", "https://threads.com/share/",
            "https://threads.com/share/a/extra", "https://threads.com/@user/post/a/extra",
            "https://threads.com/share/%2f%2fevil.test", "https://threads.com/share/..",
            "https://threads.com/share/a\\evil", "https://threads.com/\nshare/a",
            "https://[invalid/share/a",
        ):
            with self.subTest(url=url):
                self.assertIsNone(threads.get_threads_fixer_url(url))

    def test_explicit_https_port_and_trailing_slash(self):
        self.assertEqual(threads.get_threads_fixer_url("https://THREADS.COM:443/share/a/"),
                         "https://fixthreads.seria.moe/share/a/")

    def test_validator_preserves_other_platforms(self):
        validator = load_main_definitions()["Validator"]
        self.assertEqual(validator.validate(SHARE), ("Threads", FIXER))
        for url, source in (("https://instagram.com/reel/abc/", "Instagram"),
                            ("https://facebook.com/share/v/abc/", "Facebook"),
                            ("https://tiktok.com/@u/video/123/", "TikTok")):
            self.assertEqual(validator.validate(url)[0], source)
        self.assertEqual(validator.validate("https://threads.com.evil.test/share/a")[0], "Invalid URL")


class Media(unittest.IsolatedAsyncioTestCase):
    async def check(self, responses, expected, url=FIXER):
        session = Session(responses)
        with patch.object(threads.aiohttp, "ClientSession", return_value=session) as factory:
            self.assertEqual(await threads.threads_media_ok(url), expected)
        if factory.called:
            self.assertIsInstance(factory.call_args.kwargs["cookie_jar"], aiohttp.DummyCookieJar)
            self.assertFalse(factory.call_args.kwargs.get("trust_env", False))
        for _, kwargs in session.calls:
            self.assertFalse(kwargs["allow_redirects"])
            self.assertNotIn("Cookie", kwargs["headers"])
            self.assertNotIn("Authorization", kwargs["headers"])
        return session

    async def test_video_probed_once_without_reading_body(self):
        for key in ("og:video", "og:video:secure_url", "twitter:player:stream"):
            with self.subTest(key=key):
                probe = Response(206, "video/mp4")
                session = await self.check([Response(body=metadata(key)), probe], True)
                self.assertEqual(session.calls[1][0], VIDEO)
                self.assertEqual(session.calls[1][1]["headers"]["Range"], "bytes=0-0")
                self.assertTrue(probe.closed)
                self.assertEqual(probe.reads, 0)

    async def test_image_probed_and_requires_image_content_type(self):
        for content_type, status, expected in (("image/jpeg", 200, True), ("image/png", 206, True),
                                               ("text/html", 200, False), ("image/jpeg", 403, False)):
            with self.subTest(content_type=content_type, status=status):
                response = Response(status, content_type)
                session = await self.check([Response(body=metadata("og:image", IMAGE)), response], expected)
                self.assertEqual(session.calls[1][0], IMAGE)
                self.assertTrue(response.closed)
                self.assertEqual(response.reads, 0)

    async def test_bad_video_never_falls_back_to_poster(self):
        page = metadata() + metadata("og:image", IMAGE)
        for response in (Response(200, "image/jpeg"), Response(403, "video/mp4")):
            session = await self.check([Response(body=page), response], False)
            self.assertEqual(len(session.calls), 2)
        for value in ("", "http://scontent.fbcdn.net/a.mp4", "https://evil.test/clip"):
            session = await self.check([Response(body=metadata(url=value) + metadata("og:image", IMAGE))], False)
            self.assertEqual(len(session.calls), 1)

    async def test_missing_or_text_only_metadata_rejected(self):
        for body in ("", '<meta property="og:title" content="A text post">', "Log in", "<html>429</html>"):
            await self.check([Response(body=body)], False)

    async def test_metadata_status_and_content_type(self):
        for response in (Response(429), Response(500), Response(200, "image/jpeg", metadata())):
            await self.check([response], False)

    async def test_unsafe_extracted_media_is_never_requested(self):
        for url in ("https://evil.test/a", "http://scontent.fbcdn.net/a", "file:///etc/passwd",
                    "https://fbcdn.net.evil.test/a", "https://evilfbcdn.net/a",
                    "https://user@scontent.fbcdn.net/a", "https://scontent.fbcdn.net:444/a",
                    "https://scontent.fbcdn.net:bad/a", "//127.0.0.1/a", "/local-video.mp4",
                    "https://[invalid/a", "https://scontent.fbcdn.net/a\nfile"):
            with self.subTest(url=url):
                session = await self.check([Response(body=metadata(url=url))], False)
                self.assertEqual(len(session.calls), 1)

    async def test_untrusted_metadata_origin_is_never_requested(self):
        for url in ("https://evil.test/share/a", "http://fixthreads.seria.moe/share/a",
                    "https://user@fixthreads.seria.moe/share/a", "https://fixthreads.seria.moe:444/share/a"):
            session = await self.check([], False, url)
            self.assertEqual(session.calls, [])

    async def test_relative_redirects_and_allowed_cdn_redirects(self):
        session = await self.check([
            Response(302, location="/@user/post/abc"), Response(body=metadata()),
            Response(307, location="https://scontent.fbcdn.net/clip.mp4"),
            Response(302, location="/final.mp4"), Response(206, "video/mp4"),
        ], True)
        self.assertEqual(session.calls[1][0], "https://fixthreads.seria.moe/@user/post/abc")
        self.assertEqual(session.calls[-1][0], "https://scontent.fbcdn.net/final.mp4")

    async def test_bad_redirects_rejected_before_destination_request(self):
        for destination in ("https://evil.test/a", "http://fixthreads.seria.moe/a",
                            "https://scontent.fbcdn.net/a", "https://threads.com/accounts/login",
                            "https://user@fixthreads.seria.moe/a", "https://fixthreads.seria.moe:444/a", None):
            with self.subTest(destination=destination):
                session = await self.check([Response(302, location=destination)], False)
                self.assertEqual(len(session.calls), 1)
        session = await self.check([Response(body=metadata()), Response(302, location="https://evil.test/a")], False)
        self.assertEqual(len(session.calls), 2)

    async def test_redirect_limit_allows_three_but_not_four(self):
        session = await self.check([Response(302, location="/next")] * 3 +
                                   [Response(body=metadata()), Response(206, "video/mp4")], True)
        self.assertEqual(len(session.calls), 5)
        session = await self.check([Response(302, location="/next")] * 4, False)
        self.assertEqual(len(session.calls), 4)
        session = await self.check([Response(body=metadata())] +
                                   [Response(302, location=VIDEO)] * 4, False)
        self.assertEqual(len(session.calls), 5)

    async def test_network_errors_and_timeouts_fail_cleanly(self):
        for error in (aiohttp.ClientError("offline"), asyncio.TimeoutError()):
            await self.check([error], False)
            await self.check([Response(body=metadata()), error], False)

    async def test_combined_budget_expires_during_metadata(self):
        wait_for = asyncio.wait_for

        async def short_budget(awaitable, timeout):
            self.assertEqual(timeout, 15)
            return await wait_for(awaitable, timeout=0.01)

        response = Response(body=metadata(), delay=0.1)
        with patch.object(threads.asyncio, "wait_for", side_effect=short_budget):
            await self.check([response], False)
        self.assertTrue(response.closed)


class Integration(unittest.IsolatedAsyncioTestCase):
    async def test_message_detection_routes_both_threads_domains(self):
        namespace = load_main_definitions()
        namespace["send_reply"] = AsyncMock()
        message = types.SimpleNamespace(author=types.SimpleNamespace(bot=False),
                                        channel=types.SimpleNamespace(id=123),
                                        content=(f"{SHARE} https://threads.net/@u/post/abc "
                                                 "https://threads.com:443/share/a https://THREADS.COM/share/a"))
        await namespace["on_message"](message)
        self.assertEqual([call.args[1] for call in namespace["send_reply"].await_args_list],
                         [SHARE, "https://threads.net/@u/post/abc", "https://threads.com:443/share/a",
                          "https://THREADS.COM/share/a"])
        namespace["bot"].process_commands.assert_awaited_once_with(message)

    async def run_reply(self, media_ok=True, embedded=True, probe_error=None):
        namespace = load_main_definitions()
        placeholder = types.SimpleNamespace(edit=AsyncMock(), delete=AsyncMock(), id=456)
        error = types.SimpleNamespace(delete=AsyncMock())
        message = types.SimpleNamespace(reply=AsyncMock(side_effect=[placeholder, error]), edit=AsyncMock(),
                                        channel=types.SimpleNamespace(fetch_message=AsyncMock(
                                            return_value=types.SimpleNamespace(embeds=[types.SimpleNamespace(title="A post")]
                                                                              if embedded else []))))
        namespace["threads_media_ok"] = AsyncMock(return_value=media_ok, side_effect=probe_error)
        clock = Mock()
        clock.time.side_effect = [0, 0, 11]
        with patch.object(asyncio, "sleep", new=AsyncMock()), patch.object(asyncio, "get_event_loop", return_value=clock):
            await namespace["send_reply"](message, SHARE)
        return namespace, message, placeholder, error

    async def test_confirmed_embed_suppresses_original_and_disables_mentions(self):
        namespace, message, placeholder, _ = await self.run_reply()
        namespace["threads_media_ok"].assert_awaited_once_with(FIXER)
        message.edit.assert_awaited_once_with(suppress=True)
        self.assertIn(FIXER, placeholder.edit.await_args.kwargs["content"])
        self.assertEqual(placeholder.edit.await_args.kwargs["allowed_mentions"], "none")
        self.assertEqual(message.reply.await_args_list[0].kwargs["allowed_mentions"], "none")
        placeholder.delete.assert_not_awaited()

    async def test_failed_probe_or_embed_cleans_up_without_suppression(self):
        for media_ok, embedded, error_value in ((False, True, None), (True, False, None),
                                                 (True, True, aiohttp.ClientError("offline"))):
            with self.subTest(media_ok=media_ok, embedded=embedded, error=error_value):
                _, message, placeholder, error = await self.run_reply(media_ok, embedded, error_value)
                message.edit.assert_not_awaited()
                placeholder.delete.assert_awaited_once()
                error.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
