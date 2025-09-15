# 프롬프트 관리 고도화 설계안

## 1. 목표

현재의 단순 `.txt` 파일 기반 프롬프트 관리 시스템을 개선하여, 중앙 집중화된 관리, 버전 관리, 그리고 A/B 테스트가 용이한 고도화된 시스템을 구축하는 것을 목표로 합니다.

## 2. 문제점 분석

현재 시스템(`prompt_service`와 `prompts/*.txt`)은 프롬프트를 코드와 분리하는 1차 목표는 달성했지만, 다음과 같은 한계가 있습니다.
- **분산된 관리:** 프롬프트가 여러 파일에 흩어져 있어 전체를 파악하기 어렵습니다.
- **버전 관리의 부재:** 특정 프롬프트의 이전 버전을 보관하거나, 여러 버전을 동시에 관리하기가 어렵습니다.
- **실험의 어려움:** 새로운 버전의 프롬프트를 테스트(A/B 테스트)하려면 파일명을 변경하고 코드 호출부를 직접 수정해야 하는 번거로움이 있습니다.

## 3. 제안: YAML 기반 중앙 집중형 프롬프트 관리 시스템

단일 `app/prompts/prompts.yml` 파일을 사용하여 모든 프롬프트를 중앙에서 관리하는 시스템을 제안합니다.

### 3.1. YAML 스키마 설계

```yaml
# app/prompts/prompts.yml

# --- Review Prompts ---
review_initial_analysis:
  description: "리뷰 프로세스의 1라운드(독립 분석)를 위한 프롬프트입니다."
  default_version: v1
  versions:
    v1:
      template: |
        Topic: {topic}
        Instruction: {instruction}

        Provide your independent analysis of the topic, **prioritizing the user's specific instruction above.**
        - Be realistic and logical.
        - Provide clear reasoning, evidence, pros/cons, and possible implications.
        - Do not assume what other panelists will say.
        - Your output must be in the specified JSON format.
        - The JSON schema you must adhere to is:
          {{
            "round": 1,
            "key_takeaway": "A brief summary of the main finding.",
            "arguments": [
              "Core argument 1 (with reasoning)",
              "Core argument 2 (with reasoning)"
            ],
            "risks": ["Anticipated risk 1", "Potential risk 2"],
            "opportunities": ["Discovered opportunity 1", "Potential opportunity 2"]
          }}

    v2_experimental:
      template: |
        # 이것은 v2 실험용 프롬프트입니다.
        Topic: {topic}
        Instruction: {instruction}
        ...

review_rebuttal:
  description: "리뷰 프로세스의 2라운드(반박)를 위한 프롬프트입니다."
  default_version: v1
  versions:
    v1:
      template: |
        Rebuttal Round.
        Here are the summaries of the initial arguments:
        {rebuttal_context}
        ...

# ... (다른 프롬프트들도 동일한 구조로 추가) ...
```

- **중앙 파일:** 모든 프롬프트는 `prompts.yml` 파일 하나에 정의됩니다.
- **프롬프트 키:** 각 프롬프트는 `review_initial_analysis`와 같은 고유한 키를 가집니다.
- **버전 관리:** `versions` 맵 안에 `v1`, `v2_experimental` 등 여러 버전을 동시에 정의할 수 있습니다.
- **기본값 지정:** `default_version` 키를 통해 해당 프롬프트의 기본 버전을 지정합니다.

### 3.2. `prompt_service` 개선 설계

`app/services/prompt_service.py`를 다음과 같이 개선합니다.

- **YAML 파싱:** `PyYAML` 라이브러리를 사용하여 `prompts.yml` 파일을 로드하고 파싱합니다.
- **`get_prompt` 메서드 시그니처 변경:**
  ```python
  def get_prompt(self, name: str, version: Optional[str] = None, **kwargs: Any) -> str:
  ```
- **로직:**
  1. `name`으로 프롬프트 블록을 찾습니다.
  2. `version` 인자가 제공되면 해당 버전의 템플릿을 사용합니다.
  3. `version` 인자가 없으면 `default_version`에 지정된 버전의 템플릿을 사용합니다.
  4. 찾은 템플릿을 `kwargs`로 포맷하여 반환합니다.

### 3.3. 기대 효과

- **중앙화된 관리:** 단일 파일에서 모든 프롬프트를 관리하여 가시성과 유지보수성이 향상됩니다.
- **안전한 A/B 테스트:** 운영 코드(`review_tasks.py`)를 변경하지 않고, `get_prompt` 호출 시 `version` 인자만 달리하여 새로운 프롬프트를 안전하게 테스트할 수 있습니다.
- **명시적인 버전 관리:** 프롬프트의 변경 이력을 버전 번호로 명확하게 관리하고, 언제든지 특정 버전으로 롤백할 수 있습니다.
