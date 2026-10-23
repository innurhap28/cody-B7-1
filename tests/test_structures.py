import unittest

from app.services.shortform.schemas import Brief
from app.services.shortform.structures import select_structures


class StructureTests(unittest.TestCase):
    def complete(self, **patch):
        fields = dict(topic="책상 정리", goal="방법 시연", audience={"segment": "공부를 시작하는 대학생", "age_range": "20대"},
                      duration_sec=30, presentation_mode="hands_only", direction_style="전후 비교", core_message="작은 행동부터 시작")
        fields.update(patch)
        return Brief.model_validate(fields)

    def test_incomplete_brief_has_no_early_structure_selection(self):
        self.assertEqual(select_structures(Brief(topic="책상 정리")), [])

    def test_demonstration_selection_preserves_the_unconfirmed_brief(self):
        brief = self.complete()
        before = brief.model_dump()
        choices = select_structures(brief)
        self.assertEqual(choices[0]["key"], "demonstration")
        self.assertEqual(len(choices), 2)
        self.assertTrue(all(item["kind"] == "team_production_suggestion" for item in choices))
        self.assertEqual(brief.model_dump(), before)

    def test_empathy_and_character_choices_select_a_different_structure(self):
        brief = self.complete(topic="친구와의 오해", goal="공감", presentation_mode="on_camera",
                              characters=["친구 두 명"], direction_style="일상 상황극")
        self.assertEqual(select_structures(brief)[0]["key"], "empathy")
