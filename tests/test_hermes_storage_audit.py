import unittest
import tempfile
from pathlib import Path

from scripts.hermes_storage_audit import archive_verification, bytes_to_human, classify_entry, cleanup_plan, shell_quote


class HermesStorageAuditTests(unittest.TestCase):
    def test_classifies_active_state_as_do_not_move(self):
        item = classify_entry(Path("/Users/brain/.hermes/state.db"), 2_000_000_000)

        self.assertEqual(item["tier"], "hot-active")
        self.assertEqual(item["action"], "do-not-move")

    def test_classifies_state_snapshots_as_checksum_archive_candidate(self):
        item = classify_entry(Path("/Users/brain/.hermes/state-snapshots"), 2_000_000_000)

        self.assertEqual(item["tier"], "cold-snapshot-candidate")
        self.assertIn("checksum", item["action"])

    def test_bytes_to_human_formats_large_values(self):
        self.assertEqual(bytes_to_human(0), "0B")
        self.assertEqual(bytes_to_human(1024), "1.0KB")
        self.assertEqual(bytes_to_human(1024 * 1024 * 1024), "1.0GB")

    def test_shell_quote_handles_spaces_and_quotes(self):
        self.assertEqual(shell_quote("/Volumes/Seagate Expansion Drive/x"), "'/Volumes/Seagate Expansion Drive/x'")
        self.assertEqual(shell_quote("a'b"), "'a'\"'\"'b'")

    def test_cleanup_plan_is_non_destructive_and_protects_active_state(self):
        report = {
            "archiveRoot": "/Volumes/Seagate Expansion Drive/hedge-data/local-archives/hermes-runtime",
            "entries": [
                {
                    "name": "state-snapshots",
                    "path": "/Users/brain/.hermes/state-snapshots",
                    "size": "1.9GB",
                    "bytes": 2_000_000_000,
                }
            ],
            "profiles": [
                {
                    "name": "nemotron-fast",
                    "path": "/Users/brain/.hermes/profiles/nemotron-fast",
                    "size": "6.7GB",
                    "bytes": 7_000_000_000,
                    "hasOllamaModels": True,
                    "hasRustupToolchain": False,
                    "action": "confirm-profile-inactive-before-archive",
                }
            ],
        }

        phases = cleanup_plan(report)

        self.assertTrue(all(phase["executeManually"] is False for phase in phases))
        self.assertTrue(all(phase["destructive"] is False for phase in phases))
        self.assertTrue(any(phase["id"] == "active-state-do-not-touch" for phase in phases))
        snapshot_phase = next(phase for phase in phases if phase["id"] == "archive-state-snapshots-copy-only")
        self.assertTrue(any("rsync -a" in command for command in snapshot_phase["commands"]))

    def test_archive_verification_requires_counts_bytes_and_checksum_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            dst = root / "archive"
            src.mkdir()
            dst.mkdir()
            (src / "state.db").write_text("abc", encoding="utf-8")
            (dst / "state.db").write_text("abc", encoding="utf-8")
            (root / "archive.sha256").write_text("checksum  state.db\n", encoding="utf-8")

            result = archive_verification(src, dst)

        self.assertTrue(result["countMatches"])
        self.assertTrue(result["bytesMatch"])
        self.assertTrue(result["archiveCoversSource"])
        self.assertTrue(result["checksumManifestExists"])
        self.assertTrue(result["copyLooksComplete"])

    def test_archive_verification_allows_destination_superset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            dst = root / "archive"
            src.mkdir()
            dst.mkdir()
            (src / "state.db").write_text("abc", encoding="utf-8")
            (dst / "state.db").write_text("abc", encoding="utf-8")
            (dst / "older-state.db").write_text("older", encoding="utf-8")
            (root / "archive.sha256").write_text("checksum  state.db\n", encoding="utf-8")

            result = archive_verification(src, dst)

        self.assertFalse(result["countMatches"])
        self.assertFalse(result["bytesMatch"])
        self.assertTrue(result["archiveCoversSource"])
        self.assertTrue(result["copyLooksComplete"])

    def test_archive_verification_blocks_incomplete_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            dst = root / "archive"
            src.mkdir()
            dst.mkdir()
            (src / "state.db").write_text("abc", encoding="utf-8")

            result = archive_verification(src, dst)

        self.assertFalse(result["copyLooksComplete"])
        self.assertFalse(result["archiveCoversSource"])


if __name__ == "__main__":
    unittest.main()
