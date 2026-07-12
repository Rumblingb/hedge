import unittest

from scripts.edge_discovery_audit import resolved_subject_summary


class EdgeDiscoveryAuditTests(unittest.TestCase):
    def test_resolved_subject_summary_keeps_broad_and_subject_counts_visible(self):
        summary = resolved_subject_summary({
            "items": [
                {
                    "externalId": "arg-2026",
                    "status": "joined-research-only",
                    "resolvedMatchCount": 312,
                    "subjectSpecificMatchCount": 14,
                }
            ]
        })

        self.assertEqual(summary, [
            {
                "externalId": "arg-2026",
                "status": "joined-research-only",
                "resolvedMatchCount": 312,
                "subjectSpecificMatchCount": 14,
            }
        ])


if __name__ == "__main__":
    unittest.main()
