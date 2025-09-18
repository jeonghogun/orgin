"""Utility templates and formatting helpers for review conversations."""

from typing import Dict, Any, Iterable


def build_intro_message(topic: str, instruction: str) -> str:
    """Return a markdown intro message for a newly created review session."""

    lines = [
        "### 검토 세션 안내",
        "",
        f"**주제**: {topic}",
        f"**지침**: {instruction}",
        "",
        "세 명의 AGI 패널이 최대 4 라운드에 걸쳐 독립 분석 → 상호 검토 → 통합 정리 → 결론 정렬 순으로 의견을 교환합니다.",
        "모든 패널이 '추가 주장 없음'을 표시하면 라운드는 조기에 종료됩니다.",
        "각 라운드 사이에는 다른 패널의 요약본만 공유되어 토큰 사용량을 최소화합니다.",
        "마지막에는 관찰자가 토론 내용을 종합해 최종 보고서를 제공합니다.",
    ]
    return "\n".join(lines)


def _format_list_section(title: str, values: Iterable[str]) -> str:
    values = [value for value in values if value]
    if not values:
        return ""
    lines = [f"**{title}**"]
    lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)


def build_final_report_message(topic: str, final_report: Dict[str, Any]) -> str:
    """Format the final observer report into markdown."""

    executive_summary = final_report.get("executive_summary") or final_report.get("summary") or ""
    consensus = final_report.get("strongest_consensus") or final_report.get("consensus") or []
    disagreements = final_report.get("remaining_disagreements") or final_report.get("disagreements") or []
    recommendations = final_report.get("recommendations") or final_report.get("action_items") or []

    sections = [
        "### 관찰자 최종 보고서",
        "",
        f"**주제**: {topic}",
    ]

    if executive_summary:
        sections.extend(["", "**종합 요약**", executive_summary])

    for title, values in (
        ("강한 합의", consensus),
        ("남은 쟁점", disagreements),
        ("우선 실행 제안", recommendations),
    ):
        formatted = _format_list_section(title, values)
        if formatted:
            sections.extend(["", formatted])

    return "\n".join(sections)

