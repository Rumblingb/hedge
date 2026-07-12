import tempfile
import unittest
from pathlib import Path

from scripts.paper_source_cards import (
    PaperSeed,
    build_report,
    default_markdown_path,
    redact_contact_text,
    render_markdown,
)


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, text: str, title: str = "", author: str = ""):
        self.metadata = {"/Title": title, "/Author": author}
        self.pages = [FakePage(text)]


class PaperSourceCardsTest(unittest.TestCase):
    def test_personal_pdf_is_excluded_from_alpha_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BB GCC Leader 1.0.pdf"
            path.write_bytes(b"%PDF-1.4")
            seed = PaperSeed(path, "research-only", "Review relevance before extraction")

            report = build_report(
                seeds=[seed],
                reader_factory=lambda _path: FakeReader(
                    "BASKARAN BALASUBRAMANIAN Executive Leader Technology Services",
                    title="BB GCC Leader",
                ),
            )

        card = report["cards"][0]
        self.assertEqual(card["decision"], "not-bill-alpha")
        self.assertEqual(card["lane"], "exclude")
        self.assertEqual(card["tradableVariable"], "none")
        self.assertEqual(card["textSample"], "[redacted: excluded non-alpha document]")
        self.assertFalse(report["readyForExecution"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["touchesBroker"])

    def test_multimodal_futures_paper_is_candidate_with_caution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ssrn-6702398.pdf"
            path.write_bytes(b"%PDF-1.4")
            seed = PaperSeed(path, "candidate", "Identify thesis")

            report = build_report(
                seeds=[seed],
                reader_factory=lambda _path: FakeReader(
                    "Design of a Quantitative Futures Trading Model Incorporating Multimodal Feature Fusion and Tail Risk Control. Transformer benchmark.",
                    title="Design of a Quantitative Futures Trading Model Incorporating Multimodal Feature Fusion and Tail Risk Control",
                ),
            )

        card = report["cards"][0]
        self.assertEqual(card["decision"], "candidate-with-caution")
        self.assertEqual(card["lane"], "futures")
        self.assertIn("leak", " ".join(card["contraryChecks"]).lower())

    def test_markdown_renders_research_only_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Investing in Volatility.pdf"
            path.write_bytes(b"%PDF-1.4")
            seed = PaperSeed(path, "candidate", "Convert volatility regime claims")
            report = build_report(
                seeds=[seed],
                reader_factory=lambda _path: FakeReader("Goldman Sachs Investing in Volatility"),
            )
            markdown = render_markdown(report)

        self.assertIn("Ready for execution/demo/live: `false`", markdown)
        self.assertIn("volatility regime overlay", markdown)
        self.assertIn("Contrary Checks", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_default_markdown_path_uses_current_date(self):
        path = default_markdown_path()

        self.assertRegex(path.name, r"^Paper-Source-Cards-\d{4}-\d{2}-\d{2}\.md$")
        self.assertNotEqual(path.name, "Paper-Source-Cards-2026-05-30.md")

    def test_text_samples_redact_contact_details(self):
        text = "Research author 19707728293@163.com phone 212-902-0129"
        redacted = redact_contact_text(text)
        self.assertNotIn("@163.com", redacted)
        self.assertNotIn("212-902-0129", redacted)
        self.assertIn("[redacted-email]", redacted)
        self.assertIn("[redacted-phone]", redacted)


if __name__ == "__main__":
    unittest.main()
