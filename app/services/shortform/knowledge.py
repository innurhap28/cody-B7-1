"""Small, inspectable keyword retrieval with source and license provenance."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "shortform"
ALLOWED_LICENSES = {"CC BY 4.0", "CC BY-NC 4.0", "CC BY-NC-SA 4.0"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    return re.sub(r"[^\w가-힣]", "", text)


class KnowledgeBase:
    def __init__(self, directory: Path = DATA_DIR, *, scope: str = "educational_noncommercial"):
        if scope not in {"educational_noncommercial", "commercial"}:
            raise ValueError("Unknown knowledge usage scope")
        self.scope = scope
        source_bytes = (directory / "sources.json").read_bytes()
        card_bytes = (directory / "cards.jsonl").read_bytes()
        self.version = "kb-" + hashlib.sha256(source_bytes + b"\n" + card_bytes).hexdigest()[:16]
        sources = json.loads(source_bytes)
        self.sources = {s["source_id"]: s for s in sources}
        if len(self.sources) != len(sources):
            raise ValueError("Duplicate source IDs")
        cards = [json.loads(line) for line in card_bytes.decode("utf-8").splitlines() if line.strip()]
        if len({c["card_id"] for c in cards}) != len(cards):
            raise ValueError("Duplicate card IDs")
        self.cards = []
        for card in cards:
            source = self.sources[card["source_id"]]
            if card["review_status"] != "approved" or source["rights_status"] != "licensed":
                continue
            if source["license"] not in ALLOWED_LICENSES:
                continue
            if self.scope == "commercial" and "NC" in source["license"]:
                continue
            if not all(card.get(k) for k in ("concept", "summary", "locator", "reviewed_by", "tags")):
                raise ValueError("Incomplete source card")
            if not card.get("limitations") or not card["url"].startswith("https://"):
                raise ValueError("Missing limitations or invalid source URL")
            locator = card["locator"]
            if locator["type"] == "pdf_pages":
                start, end = locator["pdf_page_start"], locator["pdf_page_end"]
                count = source.get("pdf_page_count")
                if (type(start) is not int or type(end) is not int or type(count) is not int
                        or not 1 <= start <= end <= count or not source.get("pdf_url")):
                    raise ValueError("Invalid verified PDF page locator")
            elif locator["type"] != "html_section":
                raise ValueError("Unknown source locator")
            if not locator.get("heading"):
                raise ValueError("Missing source heading")
            self.cards.append(card)

    def search(self, query: str, *, context: str = "", limit: int = 3) -> list[dict]:
        if not 1 <= limit <= 3:
            raise ValueError("Retrieval limit must be 1..3")
        focus, background = normalize(query), normalize(context)
        terms = set(re.findall(r"[\w가-힣]+", query.casefold()))
        ranked = []
        for card in self.cards:
            text = " ".join([card["concept"], card["summary"], *card["tags"]]).casefold()
            aliases = {normalize(t) for t in [*card["tags"], *card.get("aliases", [])] if len(normalize(t)) > 1}
            direct = sum(1 for tag in aliases if tag in focus)
            contextual = sum(1 for tag in aliases if tag in background)
            score = (100 if direct else 0) + min(direct, 5) * 10 + min(contextual, 5)
            score += sum(1 for token in terms if len(token) > 1 and token in text)
            if score:
                ranked.append((score, card["card_id"], card, direct))
        # A named concept should not be padded with unrelated background cards.
        if any(item[3] for item in ranked):
            ranked = [item for item in ranked if item[3]]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:limit]]

    def references(self, ids: list[str], retrieved: list[dict]) -> list[dict]:
        allowed = {c["card_id"]: c for c in retrieved}
        if set(ids) - set(allowed):
            raise ValueError("Reference was not retrieved")
        result = []
        for card_id in dict.fromkeys(ids):
            card = allowed[card_id]
            source = self.sources[card["source_id"]]
            result.append({"card_id": card_id, "source_id": source["source_id"],
                           "source_title": source["title"], "author": source["author"],
                           "url": card["url"], "locator": card["locator"],
                           "pdf_url": source.get("pdf_url"),
                           "pdf_page_start": card["locator"].get("pdf_page_start"),
                           "pdf_page_end": card["locator"].get("pdf_page_end"),
                           "concept": card["concept"], "license": source["license"],
                           "license_url": source["license_url"], "changes": card["changes"],
                           "knowledge_version": self.version,
                           "limitations": card.get("limitations", []),
                           "application_notes": card.get("application_notes", []),
                           "research_topic_ids": card.get("research_topic_ids", [])})
        return result
