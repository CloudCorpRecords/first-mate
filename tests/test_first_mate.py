"""Tests for First Mate. Stdlib unittest only.

Run from the project root:
  python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from first_mate.cli import health_payload, main
from first_mate.config import Config, load_config
from first_mate.context_dev import _html_to_text, fetch_link
from first_mate.inference import local_summary
from first_mate.server import Handler
from first_mate.ship_log import build_ship_log, save_ship_log
from first_mate.transcript import MAX_INPUT_CHARS, InputError, parse_transcript

SAMPLE = """Maya: We decided to keep it simple
Rene: I will build the first version by Friday
Maya: Notes and a link https://example.com/page
Sam: TODO check the private route
"""


class TranscriptTests(unittest.TestCase):
    def test_extracts_links_once(self):
        t = parse_transcript("A: see https://example.com/a and https://example.com/a\nB: also https://boat.dev/")
        self.assertEqual(t.links, ["https://example.com/a", "https://boat.dev/"])

    def test_decisions_and_actions(self):
        t = parse_transcript(SAMPLE)
        self.assertTrue(any("keep it simple" in d for d in t.decisions))
        self.assertTrue(any("build the first version" in a for a in t.actions))
        self.assertTrue(any("check the private route" in a for a in t.actions))

    def test_speakers_parsed(self):
        t = parse_transcript(SAMPLE)
        self.assertEqual(t.messages[0].speaker, "Maya")
        self.assertEqual(t.messages[1].speaker, "Rene")


class InferenceTests(unittest.TestCase):
    def test_local_summary_is_local_only(self):
        t = parse_transcript(SAMPLE)
        summary = local_summary(t, [])
        self.assertEqual(summary.mode, "Local only")
        self.assertTrue(summary.bullets)

    def test_unconfigured_config_is_not_live(self):
        config = Config()
        self.assertFalse(config.inference_configured)
        self.assertFalse(config.context_dev_configured)

    def test_key_without_base_url_is_not_live(self):
        # A key alone must never be treated as a live private route.
        config = Config(nyte_api_key="test-key-only")
        self.assertFalse(config.inference_configured)


class ContextDevTests(unittest.TestCase):
    def test_html_to_text_strips_tags(self):
        title, text = _html_to_text(
            "<html><head><title>Hi Boat</title></head><body><p>Hello <b>crew</b></p><script>bad()</script></body></html>"
        )
        self.assertEqual(title, "Hi Boat")
        self.assertIn("Hello crew", text)
        self.assertNotIn("bad()", text)

    def test_bad_link_is_labelled_not_fetched(self):
        config = Config(fetch_timeout=2.0)
        result = fetch_link("https://invalid.invalid/first-mate-test", config)
        self.assertFalse(result.ok)
        self.assertEqual(result.source, "Not fetched")


class ShipLogTests(unittest.TestCase):
    def test_build_and_save(self):
        config = Config(data_dir=Path(tempfile.mkdtemp()) / "store")
        # Use an unfetchable link so the test never depends on the network.
        log = build_ship_log(
            "Maya: We decided to ship it\nRene: I will build it by Friday\nMaya: link https://invalid.invalid/x",
            config,
        )
        self.assertIn("# Ship Log", log.markdown)
        self.assertIn("Privacy mode: Local only", log.markdown)
        self.assertIn("What to do next", log.markdown)
        self.assertIn("read via: Not fetched", log.markdown)
        self.assertIn("<h1>Ship Log</h1>", log.html_page)
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_ship_log(log, Path(tmp), config)
            self.assertTrue(paths["markdown"].is_file())
            self.assertTrue(paths["html"].is_file())
            self.assertTrue(paths["archive"].is_file())
            saved = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("Ship Log", saved)


class AccessTests(unittest.TestCase):
    def _log(self):
        config = Config(data_dir=Path(tempfile.mkdtemp()) / "store", fetch_timeout=2.0)
        return build_ship_log(
            "Maya: We decided to ship it\n"
            "Rene: I will build it by Friday\n"
            "Maya: link https://invalid.invalid/x",
            config,
            source_label="Test chat (Teamily group chat)",
        )

    def test_link_accesses_recorded(self):
        log = self._log()
        link_entries = [e for e in log.accesses.entries if e.name.startswith("Link access:")]
        self.assertEqual(len(link_entries), 1)
        self.assertEqual(link_entries[0].tool, "Not fetched")
        self.assertEqual(link_entries[0].result, "Failed")
        self.assertIn("https://invalid.invalid/x", link_entries[0].name)
        self.assertTrue(link_entries[0].time)

    def test_ai_access_recorded_with_correct_mode(self):
        log = self._log()
        ai_entries = [e for e in log.accesses.entries if e.name == "AI summary"]
        self.assertEqual(len(ai_entries), 1)
        self.assertEqual(ai_entries[0].tool, "Local only")
        self.assertEqual(ai_entries[0].result, "Done")
        self.assertIn("No team data left the machine", ai_entries[0].detail)

    def test_not_used_accesses_explained(self):
        log = self._log()
        not_made = {e.name: e for e in log.accesses.not_made}
        # Context.dev not used, with the no key reason and the fallback named.
        self.assertIn("Context.dev", not_made)
        self.assertIn("no key", not_made["Context.dev"].detail)
        self.assertIn("direct fetch", not_made["Context.dev"].detail)
        # NYTE not used, local summary named instead.
        self.assertIn("NY Token Exchange private route", not_made)
        self.assertIn("local summary", not_made["NY Token Exchange private route"].detail)
        # Teamily API and Boat VM non-use are also explained.
        self.assertIn("Teamily API", not_made)
        self.assertIn("Boat.dev VM", not_made)

    def test_teamily_in_hosting_and_out_recorded(self):
        log = self._log()
        names = [e.name for e in log.accesses.entries]
        self.assertIn("Teamily chat in", names)
        self.assertIn("Hosting", names)
        self.assertIn("Ship Log out", names)
        team_in = [e for e in log.accesses.entries if e.name == "Teamily chat in"][0]
        self.assertIn("3 messages", team_in.detail)
        out = [e for e in log.accesses.entries if e.name == "Ship Log out"][0]
        self.assertIn("Teamily", out.detail)
        self.assertIn("ship-log.md", out.detail)

    def test_accesses_in_markdown_and_html(self):
        log = self._log()
        self.assertIn("## All accesses", log.markdown)
        self.assertIn("Accesses that were not made, and why", log.markdown)
        self.assertIn("Context.dev: not used, no key", log.markdown)
        self.assertIn("All accesses", log.html_page)
        self.assertIn("NY Token Exchange", log.html_page)


class InputRobustnessTests(unittest.TestCase):
    def test_empty_chat_is_a_clear_error(self):
        with self.assertRaises(InputError) as ctx:
            parse_transcript("   \n  \n")
        self.assertIn("empty", str(ctx.exception))

    def test_oversized_chat_is_a_clear_error(self):
        big = "A: hello there\n" * (MAX_INPUT_CHARS // 15 + 1)
        self.assertGreater(len(big), MAX_INPUT_CHARS)
        with self.assertRaises(InputError) as ctx:
            parse_transcript(big)
        self.assertIn("too large", str(ctx.exception))

    def test_malformed_lines_do_not_crash(self):
        text = (
            "no speaker on this line\n"
            "::: only colons\n"
            "Name:\n"
            "A: ok, decision: ship it\n"
            "\x00\x01 binary junk line\n"
            "B: TODO write the notes\n"
        )
        t = parse_transcript(text)
        self.assertGreaterEqual(len(t.messages), 5)
        joined = " ".join(m.text for m in t.messages)
        self.assertNotIn("\x00", joined)
        self.assertNotIn("\x01", joined)
        self.assertTrue(any("ship it" in d for d in t.decisions))

    def test_cli_missing_file_returns_2_without_traceback(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["run", "/nonexistent/first-mate-nope.txt"])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_cli_empty_file_returns_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("  \n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["run", str(path), "--out", tmp])
            self.assertEqual(code, 2)
            self.assertIn("empty", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())

    def test_cli_non_utf8_file_returns_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary.bin"
            path.write_bytes(b"\xff\xfe\x00not text")
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["run", str(path), "--out", tmp])
            self.assertEqual(code, 2)
            self.assertIn("UTF-8", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())

    def test_cli_run_happy_path_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat = Path(tmp) / "chat.txt"
            chat.write_text(SAMPLE, encoding="utf-8")
            env = {"FIRST_MATE_DATA_DIR": str(Path(tmp) / "store")}
            err = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=False):
                with redirect_stderr(err):
                    code = main(["run", str(chat), "--out", tmp])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "ship-log.md").is_file())
            meta = json.loads((Path(tmp) / "ship-log-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["counts"]["messages"], 4)
            self.assertEqual(meta["privacy_mode"], "Local only")


class ConfigCheckTests(unittest.TestCase):
    def test_bad_port_env_falls_back_to_default(self):
        # A typo in FIRST_MATE_PORT must not crash startup.
        with mock.patch.dict(os.environ, {"FIRST_MATE_PORT": "not-a-number"}, clear=False):
            config = load_config()
        self.assertEqual(config.port, 8000)

    def test_bad_timeout_env_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"FIRST_MATE_FETCH_TIMEOUT": "soon"}, clear=False):
            config = load_config()
        self.assertEqual(config.fetch_timeout, 8.0)

    def test_partial_private_route_warns_and_stays_local(self):
        config = Config(nyte_api_key="key-only")
        self.assertFalse(config.inference_configured)
        warnings = config.config_warnings()
        self.assertTrue(any("partly configured" in w for w in warnings))
        summary = config.mode_summary()
        self.assertEqual(summary["privacy_mode"], "Local only")
        self.assertEqual(summary["inference_route"], "Local summary")
        self.assertEqual(summary["hosting"], "local")

    def test_fully_configured_mode_summary(self):
        config = Config(
            nyte_api_key="k",
            nyte_base_url="https://example.invalid",
            nyte_model="m",
            context_dev_api_key="ck",
            on_boat_vm=True,
        )
        summary = config.mode_summary()
        self.assertEqual(summary["privacy_mode"], "Private via NYTE")
        self.assertEqual(summary["link_reading"], "Context.dev")
        self.assertEqual(summary["hosting"], "Boat VM")
        self.assertEqual(summary["warnings"], [])

    def test_health_payload_reports_modes_and_storage(self):
        payload = health_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["data_dir_writable"])
        self.assertIn("routes", payload)
        self.assertIn(payload["routes"]["privacy_mode"], ("Local only", "Private via NYTE"))
        self.assertIn("warnings", payload["routes"])

    def test_config_command_prints_one_json_object(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["config"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["app"], "first-mate")
        self.assertIn("privacy_mode", payload)
        self.assertIn("link_reading", payload)
        self.assertIn("warnings", payload)


class MetadataTests(unittest.TestCase):
    TEXT = (
        "Maya: We decided to ship it\n"
        "Rene: I will build it by Friday\n"
        "Maya: link https://invalid.invalid/x"
    )

    def _config(self, tmp: str) -> Config:
        return Config(data_dir=Path(tmp) / "store", fetch_timeout=2.0)

    def test_run_metadata_counts_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_ship_log(self.TEXT, self._config(tmp))
        md = log.metadata
        self.assertTrue(md["run_id"])
        self.assertIn("started_at", md)
        self.assertIn("finished_at", md)
        self.assertEqual(md["counts"]["messages"], 3)
        self.assertEqual(md["counts"]["links"], 1)
        self.assertEqual(md["counts"]["links_read_ok"], 0)
        self.assertEqual(md["counts"]["links_failed"], 1)
        self.assertEqual(md["counts"]["decisions"], 1)
        self.assertEqual(md["counts"]["actions"], 1)
        self.assertEqual(md["privacy_mode"], "Local only")
        self.assertEqual(md["mode"]["hosting"], "local")
        self.assertEqual(md["mode"]["link_reading"], "Direct fetch")

    def test_metadata_saved_with_ship_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            log = build_ship_log(self.TEXT, config)
            paths = save_ship_log(log, Path(tmp) / "out", config)
            self.assertTrue(paths["metadata"].is_file())
            self.assertTrue(paths["archive_metadata"].is_file())
            saved = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            self.assertEqual(saved["run_id"], log.metadata["run_id"])
            self.assertEqual(saved["counts"]["messages"], 3)
            archived = json.loads(paths["archive_metadata"].read_text(encoding="utf-8"))
            self.assertEqual(archived["run_id"], log.metadata["run_id"])


class ServerRobustnessTests(unittest.TestCase):
    def _start(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def test_empty_chat_post_is_400(self):
        server = self._start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request(
                "POST",
                "/ship-log",
                body="chat=",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 400)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_oversized_body_is_413_without_reading_it(self):
        server = self._start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.putrequest("POST", "/ship-log")
            conn.putheader("Content-Length", "50000000")
            conn.endheaders()
            resp = conn.getresponse()
            body = resp.read()
            self.assertEqual(resp.status, 413)
            self.assertIn(b"too large", body)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_bad_content_length_is_400(self):
        server = self._start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.putrequest("POST", "/ship-log")
            conn.putheader("Content-Length", "banana")
            conn.endheaders()
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 400)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
