---
name: insane-research-query
description: 딥리서치 전에 초점·범위·품질·산출물을 구조화한 리서치 쿼리를 만들어요. "/research query", "리서치 쿼리 만들어줘", "쿼리 빌더" 요청에 써요.
---

<!-- Logent adapter: Claude 전용 질문 도구 대신 채팅으로 확인해요. -->

# Insane Research Query Builder

> 모호한 리서치 아이디어를 구조화된 실행 가능한 쿼리로 바꿔요.

## Logent 실행 계약

- `AskUserQuestion`은 없어요. 아래 항목을 **채팅으로 한 번에** 묻고, 사용자의 답이 올 때까지 멈춰요. 이미 충분히 구체적이면 묻지 않고 기본값을 써요.
- 참조 스키마는 `skill read insane-research-query path=references/query_schema.json`, 예시는 `skill read insane-research path=examples/`로 읽어요.
- 출력은 구조화 JSON과 사람이 읽을 리서치 브리프를 함께 줘요.

## Trigger Conditions

```
- "/research query" / "/insane-research query"
- "리서치 쿼리 만들어줘"
- "research query builder" / "structured research query" / "쿼리 빌더"
```

---

## WHEN TRIGGERED — 바로 실행

### Phase 1+2: Discovery and Scoping

주제가 없으면 다음을 한 번에 물어요. 사용자 언어를 따라요.

1. 리서치할 주제나 질문은 무엇인가요? (예시를 원하면 `skill read insane-research path=examples/`에서 보여 줘요.)
2. 리서치 유형은 무엇인가요? (탐색·비교·분석·예측·평가)
3. 지리적 범위는 어디인가요? (전 세계·미국/북미·아시아태평양·유럽·기타)
4. 필요한 출처 품질은 어느 정도인가요? (A 학술만·B 높은 품질·C 보통·D 폭넓게)
5. 산출물은 무엇인가요? (종합 보고서·요약·모듈 문서·웹사이트)

답을 받으면 Phase 3으로 진행해요.

### Phase 3: Query Generation

After gathering all inputs, generate:

1. **Structured JSON Query** following the schema at:
   `skill read insane-research-query path=references/query_schema.json`

2. **Human-Readable Research Brief** in markdown format

3. **Execution Checklist** for quality verification

### Output Format

#### JSON Query Structure
```json
{
  "task": {
    "title": "[Concise 5-15 word title]",
    "objective": "[Clear statement of research goal]",
    "type": "exploratory|comparative|analytical|predictive|evaluative"
  },
  "context": {
    "background": "[Why this research matters]",
    "audience": "technical|executive|academic|general|policy_maker",
    "use_case": "[How the research will be used]",
    "prior_knowledge": ["assumption 1", "assumption 2"]
  },
  "questions": {
    "primary": "[Main research question]",
    "secondary": ["Sub-question 1", "Sub-question 2", "Sub-question 3"],
    "hypotheses": ["Testable assumption 1"],
    "exclusions": ["Out of scope topic 1"]
  },
  "constraints": {
    "timeframe": {"start": "2024-01-01", "end": "present", "focus_period": "2025-2026"},
    "geography": {"scope": "global", "regions": [], "exclude_regions": []},
    "sources": {
      "required_types": ["peer_reviewed", "industry_reports"],
      "min_quality": "B",
      "language": ["en"]
    }
  },
  "output": {
    "format": "comprehensive_report",
    "length": {"min_words": 3000, "max_words": 10000},
    "structure": {
      "include_executive_summary": true,
      "include_bibliography": true,
      "generate_website": false
    },
    "citation_style": "APA",
    "tone": "professional"
  },
  "keywords": ["keyword1", "keyword2"],
  "special_instructions": []
}
```

#### Human-Readable Brief
```markdown
# Research Brief: [Title]

## Objective
[Clear statement]

## Research Questions
### Primary Question
> [Main question]

### Secondary Questions
1. [Sub-question 1]
2. [Sub-question 2]

## Scope & Constraints
| Dimension | Specification |
|-----------|--------------|
| Timeframe | [period] |
| Geography | [scope] |
| Min Quality | Grade [X] |

## Execution Checklist
- [ ] Primary question fully answered
- [ ] All secondary questions addressed
- [ ] Sources meet quality threshold
- [ ] Citations properly formatted
```

### Phase 4: Confirmation and Handoff

**EXECUTE:** 아래 JSON으로 채팅 질문 도구를 즉시 호출한다:

```json
{
  "questions": [
    {
      "question": "Query looks good? Ready to start research?",
      "header": "Action",
      "options": [
        {"label": "Start research now", "description": "Launch deep research with this query immediately"},
        {"label": "Save query only", "description": "Save the JSON query for later use"},
        {"label": "Adjust query", "description": "Modify some parameters before starting"}
      ],
      "multiSelect": false
    }
  ]
}
```

- **Start research now** -> Pass the JSON query to insane-research-main skill
- **Save query only** -> Write the JSON to a file for the user
- **Adjust query** -> Loop back to gather adjustments

---

## Quality Validation Rules

Before finalizing the query, verify:

### Task Validation
- [ ] Title is specific (not generic like "AI Research")
- [ ] Objective is measurable/verifiable
- [ ] Type matches the research approach

### Questions Validation
- [ ] Primary question is answerable (not too broad)
- [ ] Secondary questions support primary (not tangential)
- [ ] Exclusions prevent scope creep

### Constraints Validation
- [ ] Timeframe is realistic for the topic
- [ ] Geography matches topic relevance
- [ ] Source requirements are achievable

### Output Validation
- [ ] Length matches depth requested
- [ ] Format suits the audience

---

## Anti-Patterns to Avoid

### DO NOT Generate:
- Overly broad questions ("What is AI?")
- Unbounded timeframes ("all history")
- Conflicting constraints
- Generic keywords ("technology", "innovation")
- Unmeasurable objectives ("understand everything about...")

### DO Generate:
- Specific, answerable questions ("What is the current adoption rate of AI diagnostic tools in US hospitals?")
- Realistic scope boundaries (2-3 year timeframe for fast-moving fields)
- Concrete success criteria ("Identify top 10 tools by market share")
- Actionable search terms ("AI radiology FDA approved 2024 2025 adoption rate")
- Clear exclusions ("Exclude consumer health apps and administrative AI")

---

## Example Transformation

### Input (Vague)
> "I want to know about AI in healthcare"

### Discovery Process

After Phase 1-2 questions, the vague input transforms into:

| Dimension | Vague | Structured |
|-----------|-------|------------|
| Title | "AI in healthcare" | "AI Diagnostic Systems in Clinical Healthcare: Adoption and Impact 2023-2026" |
| Scope | Everything | US hospitals, diagnostic AI only, 2023-present |
| Exclusions | None | Consumer apps, billing AI, drug discovery |
| Sources | Any | FDA databases, PubMed, Gartner reports |
| Metrics | None | Adoption rate %, sensitivity/specificity, ROI timeline |

### Generated Keywords
From the vague "AI healthcare", generate specific search terms:
```
"AI diagnostics FDA approved 2025"
"clinical AI adoption rate hospital"
"radiology AI sensitivity specificity study"
"healthcare AI ROI implementation cost"
"medical AI regulatory compliance HIPAA"
```

---

## Language Adaptation

All 채팅 질문 labels and descriptions adapt to the user's detected language.

### Korean Input Handling
When user inputs Korean (e.g., "헬스케어 AI 리서치 쿼리 만들어줘"):

- All question labels in Korean
- Geographic options include Korea-relevant choices
- Source options include Korean research databases
- Output includes Korean citation conventions

### Multi-language Keywords
Generate search keywords in both the user's language and English for maximum coverage:
```
Korean input: "AI 의료 진단"
Generated: ["AI 의료 진단 2026", "AI medical diagnostics 2026", "의료 AI 도입 현황", "clinical AI adoption"]
```

---

## Integration with Insane Research

The generated query feeds directly into the insane-research-main skill:

1. Query builder outputs structured JSON
2. User confirms or adjusts
3. If "Start research now" selected, the JSON is passed to insane-research-main
4. Phase 1 (Question Scoping) is skipped since requirements are already defined
5. Research begins from Phase 2 (Retrieval Planning)

Save location for queries: `RESEARCH/queries/{topic}_{timestamp}.json`

---

## References

- Query schema: `skill read insane-research-query path=references/query_schema.json`
- Example queries: `skill read insane-research path=examples/`
