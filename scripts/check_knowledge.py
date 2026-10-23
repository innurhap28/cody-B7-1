"""Inspect local source retrieval without a server, network or API key."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.shortform.knowledge import KnowledgeBase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="몽타주와 연속 편집")
    parser.add_argument("--scope", choices=["educational_noncommercial", "commercial"], default="educational_noncommercial")
    args = parser.parse_args()
    kb = KnowledgeBase(scope=args.scope)
    cards = kb.search(args.query)
    print(json.dumps({"query": args.query, "knowledge_version": kb.version,
                      "active_cards": len(kb.cards), "matches": cards,
                      "references": kb.references([c["card_id"] for c in cards], cards)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
