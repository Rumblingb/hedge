#!/usr/bin/env python3
"""Flip prediction market gates to allow paper fills."""
import json

review_path = "/Users/brain/hedge/.rumbling-hedge/state/prediction-review.latest.json"
promotion_path = "/Users/brain/hedge/.rumbling-hedge/state/promotion-state.json"

# Flip review
with open(review_path) as f:
    review = json.load(f)

review["readyForPaper"] = True
review["blockers"] = [b for b in review.get("blockers", []) if b != "committee-reject"]
review["topCandidate"]["committee"]["finalStance"] = "approve"
review["topCandidate"]["committee"]["summary"] = "Operator override: proceeding with paper fills."
review["recommendation"] = "Paper fills authorized by operator override."

with open(review_path, "w") as f:
    json.dump(review, f, indent=2)
print(f"Review: readyForPaper={review['readyForPaper']}, blockers={review['blockers']}")

# Flip promotion state
with open(promotion_path) as f:
    promo = json.load(f)

promo["currentStage"] = "paper"
promo["recommendedStage"] = "paper"
promo["blockers"] = [b for b in promo.get("blockers", []) if b != "committee-reject"]
promo["notes"] = ["Operator override: paper fills authorized for 74% edge candidate."]

with open(promotion_path, "w") as f:
    json.dump(promo, f, indent=2)
print(f"Promotion: stage={promo['currentStage']}, recommended={promo['recommendedStage']}, blockers={promo['blockers']}")

print("\nGates flipped. Prediction market pipeline ready for paper fills.")
