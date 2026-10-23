"""Runs with unittest + Pydantic; no network, API key or web/database deps."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.services.shortform.coach import CoachError, ShortformCoach, make_messages
from app.services.shortform.knowledge import DATA_DIR, KnowledgeBase
from app.services.shortform.research import load_research_agenda
from app.services.shortform.schemas import Brief, ChatRequest, ScriptDraft
from async_runner import run


def complete_brief(**patch):
    data = dict(topic="아침 메뉴", goal="정보 전달", audience={"segment":"자취 초보","age_range":"20대"},
                duration_sec=30, presentation_mode="hands_only", direction_style="차분한 실습",
                core_message="아침을 간단히 준비할 수 있다")
    data.update(patch)
    return Brief.model_validate(data)


def draft():
    return {"title":"아침의 한 장면", "duration_sec":30,
            "structure":{"name":"결과와 과정","reason":"핵심 과정을 순서대로 보여줍니다."},
            "scenes":[{"scene_no":1,"start_sec":0,"end_sec":30,"purpose":"과정 설명",
                       "visual":"재료를 보여준다","dialogue":"아침을 준비해요","caption":"한 끼",
                       "direction":"손과 재료를 고정 구도로 촬영"}],
            "rationale":[{"scene_nos":[1],"card_ids":["mp-intent"],"explanation":"장면을 중심 메시지에 맞춥니다."}]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase()

    def call(self, output, **kwargs):
        calls=[]
        async def ask(system,messages):
            calls.append((system,messages))
            return json.dumps(output,ensure_ascii=False) if not isinstance(output,str) else output
        args=dict(action="message",message="아침 메뉴를 알려주고 싶어요",brief=Brief(),phase="briefing",history=[])
        args.update(kwargs)
        result=run(ShortformCoach(self.kb,ask).process(**args))
        return result,calls

    def test_blank_or_oversized_messages_are_rejected(self):
        for text in [" ", "x"*6001]:
            with self.subTest(text_length=len(text)), self.assertRaises(ValidationError):
                ChatRequest(conversation_id=1,expected_version=0,message=text)

    def test_unicode_surrogate_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(conversation_id=1,expected_version=0,message="\ud800")

    def test_browser_cannot_supply_user_identity(self):
        with self.assertRaises(ValidationError):
            ChatRequest(conversation_id=1,expected_version=0,message="질문",user_id=99)

    def test_strict_numeric_fields(self):
        for value in [True, "30", 9, 181]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Brief(duration_sec=value)

    def test_revise_requires_script_id(self):
        with self.assertRaises(ValidationError):
            ChatRequest(conversation_id=1,expected_version=0,message="수정",action="revise")

    def test_partial_update_preserves_audience_and_original_topic(self):
        base=Brief(topic="아침",audience={"segment":"자취생"})
        updated=base.patched({"audience":{"age_range":"전체 연령"}})
        self.assertEqual(updated.topic,"아침")
        self.assertEqual(updated.audience.segment,"자취생")
        self.assertEqual(updated.audience.age_range,"전체 연령")

    def test_model_cannot_confirm_brief(self):
        with self.assertRaises(ValueError):
            Brief().patched({"confirmed":True})

    def test_no_people_does_not_require_characters(self):
        self.assertEqual(complete_brief(presentation_mode="no_people").missing_fields(),[])
        self.assertIn("characters",complete_brief(presentation_mode="on_camera").missing_fields())

    def test_ask_only_missing_fields_and_at_most_two(self):
        result,calls=self.call({"brief_patch":{"topic":"아침 메뉴","goal":"정보 전달"}})
        self.assertEqual(len(calls),1)
        self.assertEqual(result["reply_type"],"question")
        self.assertLessEqual(len(result["follow_up_questions"]),2)
        self.assertNotIn("topic",[q["field"] for q in result["follow_up_questions"]])

    def test_complete_brief_waits_for_confirmation(self):
        result,_=self.call({"brief_patch":{}},brief=complete_brief())
        self.assertEqual(result["phase"],"ready")
        self.assertFalse(result["brief"]["confirmed"])
        self.assertIsNone(result["script"])

    def test_generate_during_incomplete_brief_skips_ai(self):
        result,calls=self.call({},action="generate")
        self.assertEqual(calls,[])
        self.assertEqual(result["reply_type"],"question")

    def test_generation_after_ready_confirms_brief_and_resolves_sources(self):
        result,_=self.call(draft(),action="generate",brief=complete_brief(),phase="ready")
        self.assertTrue(result["brief"]["confirmed"])
        self.assertEqual(result["phase"],"drafted")
        self.assertEqual(result["references"][0]["source_id"],"moving-pictures")
        self.assertIsNone(result["references"][0]["pdf_page_start"])

    def test_unknown_reference_rejected(self):
        data=draft();data["rationale"][0]["card_ids"]=["made-up-professor"]
        with self.assertRaises(CoachError) as error:
            self.call(data,action="generate",brief=complete_brief(),phase="ready")
        self.assertEqual(error.exception.code,"AI_INVALID_RESPONSE")

    def test_research_agenda_reaches_briefing_and_generation_as_questions(self):
        for action in ["message", "generate"]:
            output = {"brief_patch": {}} if action == "message" else draft()
            _, calls = self.call(output, action=action, brief=complete_brief(), phase="ready")
            system, messages = calls[0]
            data = json.loads(messages[0]["content"].split("\n", 1)[1])
            agenda = data["research_agenda"]
            self.assertEqual(agenda["evidence_status"], "research_questions_not_findings")
            self.assertEqual(len(agenda["topics"]), 8)
            self.assertIn("검증된 연구 결과나 인용 출처가 아니다", system)
            self.assertTrue(all(not c["card_id"].startswith("rq-") for c in data["reference_cards"]))

    def test_research_question_cannot_be_cited_as_evidence(self):
        data = draft()
        data["rationale"][0]["card_ids"] = ["rq-01"]
        with self.assertRaises(CoachError) as error:
            self.call(data, action="generate", brief=complete_brief(), phase="ready")
        self.assertEqual(error.exception.code, "AI_INVALID_RESPONSE")

    def test_research_loader_rejects_claimed_findings_or_duplicate_topics(self):
        for change in ["findings", "duplicate"]:
            data = load_research_agenda()
            if change == "findings":
                data["evidence_status"] = "proven"
            else:
                data["topics"][1]["id"] = data["topics"][0]["id"]
            with tempfile.TemporaryDirectory(dir=os.environ.get("SHORTFORM_TEST_TMPDIR")) as folder:
                path = Path(folder) / "agenda.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_research_agenda(path)

    def test_incorrect_timeline_rejected(self):
        for field,value in [("start_sec",2),("end_sec",29),("scene_no",2)]:
            data=draft();data["scenes"][0][field]=value
            with self.subTest(field=field),self.assertRaises(CoachError):
                self.call(data,action="generate",brief=complete_brief(),phase="ready")

    def test_duration_cannot_be_changed_by_generation(self):
        data=draft();data["duration_sec"]=45
        with self.assertRaises(CoachError):
            self.call(data,action="generate",brief=complete_brief(),phase="ready")

    def test_invalid_json_is_safe_error(self):
        with self.assertRaises(CoachError) as error:
            self.call("not json")
        self.assertEqual(error.exception.status,502)

    def test_timeout_is_bounded_and_preserves_caller_brief(self):
        brief=complete_brief()
        async def stalled(system,messages):
            await asyncio.sleep(1)
        with self.assertRaises(CoachError) as error:
            run(ShortformCoach(self.kb,stalled,timeout=.01).process(action="generate",message="작성",brief=brief,phase="ready",history=[]))
        self.assertEqual(error.exception.code,"AI_TIMEOUT")
        self.assertFalse(brief.confirmed)

    def test_explanation_preserves_drafted_phase(self):
        brief=complete_brief(confirmed=True)
        result,_=self.call({"intent":"explanation","answer":"촬영할 수 있는 구도를 먼저 정해보세요."},brief=brief,phase="drafted")
        self.assertEqual(result["reply_type"],"explanation")
        self.assertEqual(result["phase"],"drafted")
        self.assertTrue(result["brief"]["confirmed"])

    def test_recent_history_keeps_five_in_order(self):
        history=[{"question":str(i),"answer":f"답{i}"} for i in range(8)]
        messages=make_messages({"brief":"original"},history,"현재")
        self.assertEqual(messages[1]["content"],"3")
        self.assertEqual(messages[-1]["content"],"현재")
        self.assertIn("original",messages[0]["content"])

    def test_history_budget_does_not_drop_brief(self):
        messages=make_messages({"topic":"최초 주제"},[{"question":"x"*20000,"answer":"a"}],"현재")
        self.assertEqual(len(messages),2)
        self.assertIn("최초 주제",messages[0]["content"])

    def test_pending_kim_sources_not_retrieved(self):
        self.assertEqual(len([s for s in self.kb.sources.values() if s["source_id"].startswith("kim-")]),3)
        self.assertTrue(all(not c["source_id"].startswith("kim-") for c in self.kb.cards))

    def test_commercial_scope_excludes_nc_cards(self):
        kb=KnowledgeBase(scope="commercial")
        self.assertTrue(kb.cards)
        self.assertTrue(all("NC" not in kb.sources[c["source_id"]]["license"] for c in kb.cards))

    def test_search_does_not_fill_irrelevant_matches(self):
        self.assertEqual(self.kb.search("zzyyxx-nothing"),[])
        self.assertLessEqual(len(self.kb.search("대본 구조 연출 시청자")),3)

    def test_unreviewed_cards_are_excluded(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("SHORTFORM_TEST_TMPDIR")) as folder:
            path=Path(folder)
            (path/"sources.json").write_bytes((DATA_DIR/"sources.json").read_bytes())
            data=dict(self.kb.cards[0]);data["review_status"]="draft"
            (path/"cards.jsonl").write_text(json.dumps(data),encoding="utf-8")
            self.assertEqual(KnowledgeBase(path).cards,[])

    def test_reference_resolver_cannot_invent_source(self):
        with self.assertRaises(ValueError):
            self.kb.references(["ms101-needs"],[])

    def test_schema_json_is_available_for_api_and_model(self):
        self.assertIn("properties",ChatRequest.model_json_schema())
        self.assertIn("scenes",ScriptDraft.model_json_schema()["properties"])

    def test_all_eight_research_topics_have_approved_source_cards(self):
        for number in range(1, 9):
            rq = f"rq-{number:02}"
            self.assertTrue(any(rq in c.get("research_topic_ids", []) for c in self.kb.cards), rq)

    def test_theory_aliases_retrieve_the_relevant_source(self):
        examples = {"3막구조를 알려줘":"mp-three-act", "프라이타크가 뭐야":"plot-freytag",
                    "정보격차 이론은?":"curiosity-gap", "서스펜스란?":"suspense-anticipation",
                    "인지 부하를 줄여줘":"cognitive-load", "몽타주가 궁금해":"mp-montage",
                    "연속편집 원리":"mp-continuity", "편집리듬 조절":"mp-rhythm",
                    "Show, Don’t Tell":"show-action", "프롬프트 구조화":"prompt-decomposition",
                    "암묵지를 규칙화":"tacit-elicitation", "지각적유창성":"aesthetic-fluency",
                    "창의성 평가":"creativity-criteria"}
        for query, expected in examples.items():
            with self.subTest(query=query):
                self.assertIn(expected, [c["card_id"] for c in self.kb.search(query)])

    def test_explicit_theory_outranks_old_conversation_context(self):
        cards = self.kb.search("몽타주를 설명해줘", context="시청자 타겟 공감 목적 정보 연출 대본 구조")
        self.assertEqual([c["card_id"] for c in cards], ["mp-montage"])

    def test_explanation_passes_retrieved_evidence_and_returns_provenance(self):
        output = {"intent":"explanation", "answer":"연속 편집은 공간과 시간 흐름을 이해하도록 연결합니다.",
                  "card_ids":["mp-continuity"]}
        result, calls = self.call(output, message="연속 편집을 설명해줘")
        data = json.loads(calls[0][1][0]["content"].split("\n", 1)[1])
        self.assertIn("mp-continuity", [c["card_id"] for c in data["reference_cards"]])
        self.assertEqual(result["references"][0]["source_id"], "moving-pictures")
        self.assertTrue(result["references"][0]["limitations"])

    def test_explanation_without_citation_abstains_instead_of_asserting(self):
        result, _ = self.call({"intent":"explanation", "answer":"근거 없는 성과 100% 보장"}, message="인지부하 설명")
        self.assertNotIn("100%", result["answer"])
        self.assertIn("근거를 확인하지 못했습니다", result["answer"])
        self.assertEqual(result["references"], [])

    def test_pdf_pages_and_source_url_resolve_without_invented_file_hash(self):
        cards = self.kb.search("서스펜스")
        ref = self.kb.references(["suspense-anticipation"], cards)[0]
        self.assertEqual((ref["pdf_page_start"], ref["pdf_page_end"]), (10, 10))
        self.assertEqual(ref["url"], ref["pdf_url"])
        self.assertIsNone(self.kb.sources[ref["source_id"]]["source_sha256"])
        with tempfile.TemporaryDirectory(dir=os.environ.get("SHORTFORM_TEST_TMPDIR")) as folder:
            path = Path(folder)
            (path / "sources.json").write_bytes((DATA_DIR / "sources.json").read_bytes())
            damaged = dict(next(c for c in cards if c["card_id"] == "suspense-anticipation"))
            damaged["locator"] = {**damaged["locator"], "pdf_page_end": 999}
            (path / "cards.jsonl").write_text(json.dumps(damaged), encoding="utf-8")
            with self.assertRaises(ValueError):
                KnowledgeBase(path)

    def test_unapproved_license_is_not_retrieved(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("SHORTFORM_TEST_TMPDIR")) as folder:
            path = Path(folder)
            source = dict(self.kb.sources["media-studies-101"])
            source["license"] = "CC BY-NC-ND 4.0"
            (path / "sources.json").write_text(json.dumps([source]), encoding="utf-8")
            card = next(c for c in self.kb.cards if c["source_id"] == source["source_id"])
            (path / "cards.jsonl").write_text(json.dumps(card), encoding="utf-8")
            self.assertEqual(KnowledgeBase(path).cards, [])


if __name__ == "__main__":
    unittest.main()
