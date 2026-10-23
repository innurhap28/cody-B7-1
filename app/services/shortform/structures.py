"""Team production blueprints selected after the brief is complete.

These are writing aids, not academic theories or measured retention promises.
Retrieved source cards remain the only permitted academic evidence.
"""
from app.services.shortform.schemas import Brief

BLUEPRINTS = (
    {"key": "demonstration", "name": "문제 장면 → 행동 시연 → 결과 확인",
     "beats": ["불편하거나 궁금한 상황을 화면으로 보여준다", "핵심 행동을 촬영 가능한 순서로 제시한다", "전후 차이와 다음 행동을 보여준다"],
     "tags": ["방법", "실습", "시연", "정리", "비교", "사용", "만들"],
     "caution": "결과를 과장하거나 모든 시청자에게 같은 효과가 있다고 단정하지 않는다."},
    {"key": "empathy", "name": "익숙한 상황 → 인물의 선택 → 작은 변화",
     "beats": ["타겟이 이해할 수 있는 일상 상황을 제시한다", "인물의 행동이나 선택으로 관점을 드러낸다", "변화한 상황으로 핵심 메시지를 마무리한다"],
     "tags": ["공감", "상황극", "일상", "감정", "인물", "관계"],
     "caution": "연령·성별만으로 경험을 일반화하지 않고 인물의 상황을 구체화한다."},
    {"key": "explanation", "name": "질문 → 핵심 설명과 시각적 예시 → 정리",
     "beats": ["답할 수 있는 질문을 제시한다", "근거가 있는 설명을 화면의 예시와 연결한다", "처음 질문에 답하고 핵심을 정리한다"],
     "tags": ["정보", "설명", "이해", "소개", "교육", "원리"],
     "caution": "과도한 궁금증 유도보다 약속한 정보의 해소와 이해 가능한 설명량을 우선한다."},
    {"key": "observation", "name": "대상 관찰 → 관점의 발견 → 한 장면의 결론",
     "beats": ["대상을 구체적인 화면으로 관찰한다", "소리·행동·구도의 변화로 관점을 발견하게 한다", "메시지와 연결되는 마지막 장면을 선택한다"],
     "tags": ["관찰", "분위기", "감성", "풍경", "사물", "기록"],
     "caution": "설명이 꼭 필요한 내용은 자막·대사로 보완하며 무조건 생략하지 않는다."},
)


def select_structures(brief: Brief) -> list[dict]:
    if brief.missing_fields():
        return []
    terms = " ".join(filter(None, (brief.topic, brief.goal, brief.direction_style, brief.core_message)))
    scored = []
    for index, option in enumerate(BLUEPRINTS):
        score = sum(2 for tag in option["tags"] if tag in terms)
        if option["key"] == "demonstration" and brief.presentation_mode == "hands_only":
            score += 2
        if option["key"] == "empathy" and brief.characters:
            score += 1
        scored.append((-score, index, option))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [{key: value for key, value in option.items() if key != "tags"} |
            {"kind": "team_production_suggestion"} for _, _, option in scored[:2]]
