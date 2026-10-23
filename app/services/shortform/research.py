"""Team editorial guidance, separate from citable source cards."""
import hashlib
import json
from pathlib import Path

from app.services.shortform.knowledge import DATA_DIR


def load_research_agenda(path: Path = DATA_DIR / "research_agenda.json") -> dict:
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get("evidence_status") != "research_questions_not_findings":
        raise ValueError("Research questions must not be labeled as findings")
    topics = data["topics"]
    if len(topics) != 8 or {t["id"] for t in topics} != {f"rq-{i:02}" for i in range(1, 9)}:
        raise ValueError("Expected eight unique research topics")
    if any(not all(t.get(k) for k in ("question", "theory_candidates", "coaching_checks", "evidence_needed")) for t in topics):
        raise ValueError("Incomplete research topic")
    return {**data, "version": "agenda-" + hashlib.sha256(raw).hexdigest()[:16]}
