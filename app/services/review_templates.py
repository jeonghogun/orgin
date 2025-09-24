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
        "세 명의 패널이 하나의 단톡방에서 자연스럽게 의견을 주고받으며 합의를 만들어 갑니다.",
        "답변은 요약 없이 본문 그대로 공유되며, 충분한 결론이 나면 더 길게 끌지 않고 정리합니다.",
        "모든 발언은 시간순으로 기록되며 마지막에는 관찰자가 토론을 요약한 보고서를 제공합니다.",
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

