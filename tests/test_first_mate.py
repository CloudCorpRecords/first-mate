"""Tests for First Mate. Stdlib unittest only.

Run from the project root:
  python3 -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from first_mate.config import Config
from first_mate.context_dev import _html_to_text, fetch_link
from first_mate.inference import local_summary
from first_mate.ship_log import build_ship_log, save_ship_log
from first_mate.transcript import parse_transcript

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


if __name__ == "__main__":
    unittest.main()
