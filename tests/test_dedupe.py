from typing import Dict, Any, Set


def test_message_dedupe_by_id():
    shown: Set[str] = set()

    def should_append(msg: Dict[str, Any]) -> bool:
        mid: str = msg.get('message_id', '')
        if mid and mid in shown:
            return False
        if mid:
            shown.add(mid)
        return True

    m1: Dict[str, Any] = {"message_id": "abc", "role": "assistant", "content": "hi"}
    m2: Dict[str, Any] = {"message_id": "abc", "role": "assistant", "content": "hi"}
    m3: Dict[str, Any] = {"message_id": "xyz", "role": "assistant", "content": "hi2"}

    assert should_append(m1) is True
    assert should_append(m2) is False
    assert should_append(m3) is True





