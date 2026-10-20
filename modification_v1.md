# Translation Studio --- Modification V1

## Independent Translation Verification, Document IR Integrity, and PDF Round-Trip Validation

**Version:** 1.0\
**Status:** Proposed implementation specification\
**Purpose:** Extend the existing Translation Studio implementation plan
with independent quality gates for source IR recovery, Bodhan Translate
output, translated IR alignment, and generated PDF content.

------------------------------------------------------------------------

## 1. Objectives

This modification addresses three independent classes of defects:

1.  **Source IR recovery defects:** visual PDF lines are mistaken for
    semantic paragraphs; blocks are split, merged, duplicated, or
    reordered; equations and technical relationships are lost.
2.  **Translation defects:** Bodhan Translate returns extra or missing
    content, duplicated phrases, suspicious symbols, incorrect
    characters, inconsistent terminology, or unnatural/incorrect
    language.
3.  **Reconstruction defects:** translated blocks are mapped
    incorrectly, paragraph continuity is lost, math is broken, or
    rendered PDF text differs from the approved translated IR.

A successful OCR or translation API response is not evidence that the
content is correct. Each stage must pass its own validation gate.

## 2. Scope and non-goals

This specification extends the existing architecture: Bodhan OCR on
every page, PyMuPDF native extraction on every page, OCR/native
reconciliation, semantic Document IR, protected spans, translation,
layout adaptation, rendering, and visual QA.

It does not introduce local LLM hosting, model training/fine-tuning, or
a guarantee of pixel-perfect PDF reproduction. PyMuPDF remains a native
PDF extraction/rendering tool, not an OCR engine. A second language
model may assist review but cannot be the sole authority for
correctness.

## 3. Required pipeline

``` text
PDF
 |
 +--> Bodhan OCR on every page
 +--> PyMuPDF native extraction on every page
 |
 v
OCR/native reconciliation
 |
 v
Source semantic Document IR recovery
 |
 v
GATE A: Source IR integrity validation
 |
 v
Protected-span extraction and semantic segmentation
 |
 v
Bodhan Translate
 |
 v
GATE B: Independent translation verification
 |
 v
GATE C: Translated IR and source-target alignment validation
 |
 v
PDF layout/reconstruction
 |
 v
GATE D: Generated PDF text round-trip validation
 |
 v
GATE E: Typography, layout, and visual QA
 |
 v
Deliver PDF OR block for retry/review
```

Every gate returns one of: - `PASS` - `RETRY` - `REVIEW_REQUIRED` -
`FAIL`

Record gate status, issue codes, evidence references, attempt number,
policy version, and timestamp. Do not infer a gate pass from an upstream
API success.

## 4. Source Document IR recovery

### 4.1 Distinguish visual lines from semantic content

The IR must distinguish: - `VISUAL_LINE`: a line created by PDF
layout. - `SENTENCE`: a linguistic unit. - `PARAGRAPH`: a semantic
paragraph. - `BLOCK`: a typed document element (heading, paragraph, list
item, table, code, equation, caption, etc.). - `PAGE_REGION`: geometric
region containing one or more blocks.

A paragraph wrapping over several PDF lines remains one logical
paragraph unless the source semantics/layout indicate a real paragraph
break. Do not translate wrapped visual lines independently.

### 4.2 Stable identity and relationships

Every block must have a stable ID preserved through translation and
rendering. Extend the existing IR schema rather than creating a
competing schema. Required information:

``` json
{
  "block_id": "stable-id",
  "parent_block_id": null,
  "document_order": 0,
  "page_index": 0,
  "block_type": "PARAGRAPH",
  "text": "Source text",
  "source_text_hash": "sha256:...",
  "geometry": {"coordinate_space": "pdf_points", "bbox": [0, 0, 100, 40]},
  "relationships": {
    "continues_from_block_id": null,
    "continues_to_block_id": null,
    "list_id": null,
    "table_id": null,
    "caption_for_block_id": null
  },
  "provenance": {
    "native_extraction_refs": [],
    "ocr_refs": [],
    "reconciliation_status": "MATCHED"
  }
}
```

### 4.3 Paragraph recovery rules

Use multiple signals: - Font/style continuity, alignment, indentation,
and line spacing. - Sentence punctuation and language-aware sentence
boundaries. - Hyphenation at line endings. - Column/page continuation. -
List markers and numbering. - Heading/paragraph style transitions. -
OCR/native extraction agreement and geometry.

Rules: 1. Never make each PDF line a paragraph by default. 2. Never
merge blocks based only on proximity. 3. Preserve explicit paragraph
boundaries. 4. Keep list items, table cells, code/configuration lines,
and equations structurally distinct. 5. Preserve inline math inside its
parent paragraph. 6. Mark ambiguous segmentation with confidence and
evidence. 7. If ambiguity can change meaning or structure, return
`REVIEW_REQUIRED`.

### 4.4 Reading order and relationship validation

Detect: - Incorrect multi-column reading order. - Blocks ordered by
vertical coordinate when column-wise reading is required. - Captions
detached from figures/tables. - Footnotes inserted into body
paragraphs. - Headers/footers mixed into body text. - Duplicate blocks
from overlapping OCR/native extraction. - Continuation paragraphs
incorrectly treated as unrelated blocks. - Invalid parent/child
references and broken list/table membership.

### 4.5 Source IR validator

Implement `source_ir_validator` with checks for unique IDs,
content-region coverage, duplicate/empty blocks, paragraph
splits/merges, reading order, parent-child integrity, list/table
integrity, equation integrity, protected spans, and extraction
provenance.

Track separate confidence values: - `extraction_confidence` -
`paragraph_segmentation_confidence` - `reading_order_confidence` -
`block_classification_confidence` - `reconciliation_confidence`

An issue record should include `issue_code`, severity, block IDs, page
indices, evidence, and recommended action. Critical source IR failures
block translation.

## 5. Protected spans and technical content

Before translation, identify: - Numbers, percentages, decimals, signs,
ranges. - Units and unit expressions. - Equations, variables, operators,
and mathematical notation. - Currency values. - URLs, email addresses,
paths, filenames, package names. - Commands, flags, code,
YAML/JSON/XML. - API names, environment variables, versions, and
identifiers. - Figure/table/equation references and other significant
labels.

Each protected span needs a stable ID, exact source value, type, parent
block, position, and preservation policy.

If placeholders are used: - Use opaque collision-resistant tokens and a
per-block registry. - Validate required token count and identity. -
Detect missing, duplicate, malformed, or modified tokens. - Restore only
after token validation. - Reject output containing internal
placeholders, including `DOCUMENT_CONTENT`. - Never leak token wrappers
into the final PDF.

Preservation policy must be type-aware. Commands, URLs, paths,
identifiers, and code may require exact string preservation.
Numbers/units must preserve value and association. Equations should be
compared structurally where possible. Do not silently resolve critical
mismatches.

## 6. Bodhan Translate integration

### 6.1 Immutable evidence

For each request, retain an access-controlled artifact containing
provider/model identifier, request/correlation ID, source block ID/hash,
translation profile and glossary versions, protected-span registry
version, raw response, parsed target, provider status, latency, retry
count, and timestamps.

Keep full content out of ordinary logs and metric labels. Apply
retention controls.

### 6.2 Translation granularity

Translate semantic blocks, not PDF visual lines: - Paragraphs as logical
paragraphs. - Headings, list items, table cells, captions, and footnotes
as typed units with suitable context. - Code/configuration/equations
through protected or specialized paths. - Preserve source block IDs and
order. - If provider limits require splitting, split at
sentence/semantic boundaries, preserve a parent translation group and
ordered segment IDs, then reassemble and validate before completion.

### 6.3 Translation profile

Provide source/target languages, domain, glossary, preferred/avoided
terms, transliteration rules, treatment of product/UI labels,
technical-English retention policy, register, and number/unit/currency
policy. Version the profile and glossary.

## 7. Independent translation verification

### 7.1 Principle

Bodhan Translate generates a candidate; it does not certify its own
quality. Use multiple independent checks. No single score or reviewer
model can override a hard integrity failure.

### 7.2 Deterministic checks

**Response validity** - Non-empty response with expected type and
encoding. - Provider error envelopes must not be treated as translated
text. - No unresolved template variables, sentinel tokens, or
placeholders. - No invalid Unicode sequences or unexpected control
characters.

**Protected-span integrity** - Every required token exists with expected
count. - No protected token is modified or duplicated. - Numeric values
and units remain associated with the correct entities. - Equations and
identifiers pass their specific checks.

**Duplicate detection** - Repeated words or short phrases. - Repeated
complete sentences or terminal clauses. - Duplicate translated blocks. -
Repetition caused by concatenating provider chunks.

Use target-language-aware tokenization. Avoid flagging legitimate
repetition in lists, formulas, or intentional emphasis.

**Character and script anomaly detection** - Unicode replacement
character `U+FFFD`. - Unexpected private-use or unassigned code
points. - Unexpected control/format characters. - Broken combining-mark
or grapheme sequences. - Unexplained script mixing inside
words/technical terms. - Suspicious repeated punctuation or malformed
symbol runs.

Use Unicode- and script-aware rules. Valid Devanagari combining marks,
virama/halant, nukta, grapheme clusters, ZWJ/ZWNJ where appropriate,
mathematical symbols, currency signs, and approved Latin technical terms
must not be rejected. Do not use ASCII-only checks or simplistic
`ord(c)` thresholds.

**Coverage/length anomaly checks** - Empty or implausibly short
output. - Large unexplained expansion. - A paragraph reduced to a
fragment. - Missing target-language content. - Suspected
sentence/list-item omission.

Length ratios are warnings only; calibrate by language pair and content
type. They are not proof of correctness.

### 7.3 Semantic completeness and independent language review

Assess: - Omitted facts, conditions, qualifiers, and instructions. -
Added unsupported claims or explanations. - Correct subjects,
quantities, actions, and relationships. - Negation, comparison,
causality, and conditional meaning. - Correct ordering where order
affects meaning. - Technical and mathematical meaning.

An independently configured external reviewer may assess semantic
fidelity, grammar, and fluency. Its response must be structured and
include evidence spans. It is advisory: - It cannot silently edit the
translation. - It cannot override deterministic protected-span/numeric
failures. - Reviewer provider/model and prompt version must be
recorded. - Critical conflicts require human review. - If no reviewer is
configured, report `NOT_CONFIGURED`; never report full semantic
verification.

Store separate dimensions: `meaning_fidelity`, `completeness`,
`fluency`, `grammar`, `terminology_consistency`, `character_integrity`,
`duplication`, `protected_span_integrity`, `numeric_consistency`,
`structure_compatibility`.

Do not average away critical failures.

### 7.4 Issue codes

At minimum: - `EMPTY_TRANSLATION` - `PROVIDER_ERROR_AS_TEXT` -
`PLACEHOLDER_LEAKAGE` - `PROTECTED_TOKEN_MISSING` -
`PROTECTED_TOKEN_DUPLICATED` - `PROTECTED_TOKEN_MODIFIED` -
`NUMERIC_VALUE_MISMATCH` - `UNIT_ASSOCIATION_MISMATCH` -
`EQUATION_MISMATCH` - `DUPLICATE_WORD` - `DUPLICATE_PHRASE` -
`DUPLICATE_SENTENCE` - `SUSPICIOUS_CHARACTER` - `INVALID_UNICODE` -
`SCRIPT_MIXING_ANOMALY` - `PUNCTUATION_ANOMALY` - `OMISSION_SUSPECTED` -
`ADDITION_SUSPECTED` - `MEANING_CONFLICT` - `TERMINOLOGY_INCONSISTENT` -
`LOW_FLUENCY` - `SOURCE_BLOCK_MAPPING_ERROR` -
`TARGET_BLOCK_ORDER_ERROR` - `PARAGRAPH_FRAGMENTATION` -
`PARAGRAPH_MERGE_SUSPECTED`

Issue records must include ID, code, severity, stage, source block ID,
evidence references, explanation, confidence, recommended action, and
reviewer type/provider/model. Store text excerpts only in
access-controlled artifacts.

## 8. Retry and correction policy

Use bounded, configurable retries. Suggested starting policy: - Initial
translation attempt. - One targeted retry for a correctable quality
issue. - A further retry only if it changes a meaningful input (context,
glossary, segmentation) and policy allows it. - After the budget is
exhausted, return `REVIEW_REQUIRED`.

Retry only affected blocks where possible. Include source block,
adjacent context, profile/glossary version, protected-span rules, and
validator findings. Do not retry blocks that already passed.

Run the same validation suite on every candidate. Reject candidates with
hard numeric/protected-span failures. Do not choose by length or
provider confidence alone. If candidates materially disagree, request
human review.

Any proposed correction must be stored separately from the raw provider
response, explicitly applied through an auditable workflow, and fully
revalidated. No unvalidated automatic rewriting.

## 9. Translated IR and source-target alignment

Every translated block must reference source block IDs. Preserve parent
relationships, document order, block type, target language, source hash,
translation response ID, validation report ID, and status.

Rules: - Never map by array index alone. - Every translatable source
block has a target mapping or explicit skip reason. - No unexpected or
duplicate target block. - Preserve order unless an explicit structural
policy allows change. - Preserve paragraph identity and continuity. -
Preserve list nesting/numbering, table row/cell mappings, captions,
footnotes, references, and math placement. - Any one-to-many or
many-to-one mapping requires an explicit mapping record and reason. - A
failed Gate B block cannot pass Gate C. - No rendering until all
required target blocks pass.

Implement `translated_ir_validator` to check block coverage, mapping,
ordering, structure, protected spans, math, and placeholder leakage.

## 10. Example specific Problem 47 regression fixture
Here is real english version of Problem 47:
    Problem 47: An ethylene refining plant receives 500 kg/hr of 50% pure ethylene. It refines it into two types of outputs 1 and 2. Type 1 has 90% purity. Type 2 has 70% purity. The raw material cost is Rs 40/kg. The selling price of Type 1 is Rs 200/kg and that of Type 2 is Rs 120/kg. Packaging facilities can handle up to 200 kg/hr of Type 1 and 225 kg/hr of Type 2. The transportation cost is Rs 8/kg for Type 1 and Rs 16/kg for Type 2, and the total transportation cost should not exceed Rs 4000/hr. Formulate the optimization problem to maximize profit and state all constraints. Determine the optimum solution by the graphical method of Linear Programming (LP). 

Here is the translated version (english -> hindi):
    **समस्या 47:** एक एथिलीन शोधन संयंत्र को $50\%$ शुद्ध एथिलीन का $500\text{
    किग्रा/घंटा}$ प्राप्त होता है। यह
    इसे दो प्रकार के आउटपुट $1$ और $2$ में परिष्कृत करता है। टाइप $1$ की शुद्धता
    $90\%$ है। टाइप $2$ की शुद्धता $70\%$ है।
    शुद्धता। कच्चा माल की लागत $\text{Rs } 40/\text{kg}$ है। टाइप $1$ का विक्रय
    मूल्य $\text{Rs } 200/\text{kg}$ है और
    टाइप $2$ का है $\text{Rs } 120/\text{kg}$। पैकेजिंग सुविधाएँ टाइप $1$ के
    $200\text{ kg/hr}$ तक को संभाल सकती हैं।
    और टाइप $2$ का $225\text{ kg/hr}$। परिवहन लागत टाइप $1$ के लिए $\text{Rs }
    8/\text{kg}$ और $\text{Rs } 16/\text{kg}$ है।
    टाइप $2$ के लिए, और कुल परिवहन लागत $\text{Rs } 4000/\text{hr}$ से अधिक नहीं
    होनी चाहिए। सूत्रबद्ध करें
    लाभ को अधिकतम करने के लिए अनुकूलन समस्या और सभी बाधाओं को बताएं। निर्धारित करें
    कि
    रैखिक प्रोग्रामिंग (Linear Programming) की ग्राफिकल विधि द्वारा इष्टतम समाधान।

Use the supplied hindi translation of the ethylene-refinery
linear-programming problem as a regression fixture. The authoritative
source paragraph must be retained with the test data. Expected facts:

-   Feed: 500 kg/hour.
-   Feed purity: 50% ethylene.
-   Products: Type 1 and Type 2.
-   Type 1 purity: 90%; Type 2 purity: 70%.
-   Raw material cost: Rs 40/kg.
-   Type 1 selling price: Rs 200/kg; Type 2: Rs 120/kg.
-   Type 1 packaging capacity: 200 kg/hour; Type 2: 225 kg/hour.
-   Type 1 transport cost: Rs 8/kg; Type 2: Rs 16/kg.
-   Total transport cost limit: Rs 4,000/hour.
-   Task: formulate the profit-maximization problem, state all
    constraints, and determine the optimum using the graphical method of
    linear programming.

The test must detect: - The repeated `शुद्धता` phrase in the supplied
target. - Awkward/incorrect phrasing. - Ambiguous association of
transport costs with Type 1 and Type 2. - Paragraph fragmentation around
conjunctions and task instructions. - Inline math/unit formatting broken
across text boundaries. - Missing/added meaning and changed numerical
associations.

Do not hard-code rejection of particular Marathi words. Use duplicate
detection, semantic role/relationship validation, terminology checks,
and source-target alignment.

Acceptance: - All authoritative facts and task instructions are
present. - Every number/unit is associated with the correct product or
constraint. - No unexplained duplicate phrase/sentence. - No material
omission or unsupported addition. - Source paragraph maps to the correct
logical target paragraph(s). - Math and units survive reconstruction. -
Unresolved product/cost association yields `REVIEW_REQUIRED`, never
`PASS`.

Version the source fixture, expected fact representation, defective
translation, and expected issue codes.

## 11. PDF text round-trip validation

After rendering: 1. Re-open the generated PDF with PyMuPDF. 2. Extract
text and spans from every page. 3. Reconstruct reading order using
render metadata and geometry. 4. Compare extracted text with approved
translated IR at block/region level. 5. Check protected tokens, numbers,
equations, and block identities. 6. Record round-trip results separately
from visual QA.

Detect missing/extra/duplicated text, broken math, lost units/symbols,
incorrect reading order, wrong page/region placement, glyph extraction
failures, placeholder leakage, clipping, and overlap.

Whole-document string comparison alone is insufficient. PDF text
extraction does not prove visual correctness; retain separate
visual/layout checks.

## 12. Indic-script and Unicode typography validation

Use Unicode-aware validation and script-aware shaping. Account for
combining marks, virama/halant, nukta, reordering, valid ZWJ/ZWNJ,
grapheme clusters, and embedded Latin technical terms.

Use a shaping engine such as HarfBuzz/OpenType shaping before line
breaking. Measure shaped glyph advances and wrap at valid word/grapheme
boundaries. Detect missing glyphs, broken conjuncts, detached marks,
substitutions, grapheme breaks, clipping, and overlap.

Document a Unicode normalization policy. Do not blindly normalize
protected strings, identifiers, or semantically significant sequences.
Keep source and raw provider output immutable.

## 13. Validation report

Produce machine-readable and human-readable reports per job and per
block.

``` json
{
  "job_id": "job-id",
  "source_language": "en",
  "target_language": "mr",
  "policy_version": "1.0",
  "overall_status": "REVIEW_REQUIRED",
  "gates": {
    "source_ir": {"status": "PASS", "issue_count": 0},
    "translation": {"status": "REVIEW_REQUIRED", "issue_count": 2},
    "translated_ir": {"status": "NOT_RUN", "issue_count": 0},
    "pdf_round_trip": {"status": "NOT_RUN", "issue_count": 0},
    "visual_qa": {"status": "NOT_RUN", "issue_count": 0}
  },
  "block_results": [],
  "issues": [],
  "metrics": {}
}
```

Include gate status, issue counts, block results, evidence references,
retry history, reviewer type, provider/model, glossary/policy versions,
timestamps, and stage durations. Protect source/target excerpts with
access controls.

## 14. Suggested interfaces and module layout

Adapt to existing services and reuse existing code where possible.

``` python
class SourceIRValidator:
    def validate(self, source_ir, extraction_evidence) -> ValidationReport: ...

class ProtectedSpanValidator:
    def validate(self, source_block, translated_block, registry) -> ValidationReport: ...

class TranslationQualityGate:
    def validate(self, source_block, translated_block, profile, glossary) -> ValidationReport: ...

class TranslationAlignmentValidator:
    def validate(self, source_ir, translated_ir, mapping) -> ValidationReport: ...

class PdfTextRoundTripValidator:
    def validate(self, generated_pdf, approved_translated_ir, render_manifest) -> ValidationReport: ...

class TranslationRetryManager:
    def decide(self, report, attempt, policy) -> RetryDecision: ...
```

Suggested additions:

``` text
packages/
  document/semantic/
    paragraph_recovery.py
    reading_order_validator.py
    block_relationship_validator.py
    source_ir_validator.py
  translation/validation/
    translation_quality_gate.py
    semantic_completeness.py
    duplicate_content_detector.py
    character_anomaly_detector.py
    terminology_validator.py
    numerical_consistency.py
    protected_span_validator.py
    translation_alignment.py
    translation_retry_manager.py
    validation_report.py
  rendering/validation/
    translated_ir_validator.py
    pdf_text_roundtrip.py
    math_expression_validator.py
    paragraph_continuity.py
  validation/
    document_integrity_gate.py
    validation_issue.py
    validation_metrics.py
```

Keep validators deterministic and side-effect free where possible.
Provider calls and human review belong in orchestration/services.

## 15. Configuration

Align names with the existing settings system and `.env.example`.

``` dotenv
TRANSLATION_VALIDATION_ENABLED=true
TRANSLATION_VALIDATION_POLICY_VERSION=1
TRANSLATION_MAX_RETRIES=2
TRANSLATION_RETRY_ON_DUPLICATION=true
TRANSLATION_RETRY_ON_CHARACTER_ANOMALY=true
TRANSLATION_RETRY_ON_SEMANTIC_FAILURE=true

TRANSLATION_REVIEW_PROVIDER=
TRANSLATION_REVIEW_MODEL=
TRANSLATION_REVIEW_REQUIRED_FOR_TECHNICAL_DOCS=false

SOURCE_IR_VALIDATION_ENABLED=true
TRANSLATED_IR_VALIDATION_ENABLED=true
PDF_TEXT_ROUNDTRIP_VALIDATION_ENABLED=true
PARAGRAPH_CONTINUITY_VALIDATION_ENABLED=true

UNICODE_ANOMALY_VALIDATION_ENABLED=true
SCRIPT_VALIDATION_STRICTNESS=balanced

STORE_RAW_TRANSLATION_RESPONSE=true
TRANSLATION_ARTIFACT_RETENTION_DAYS=30
```

Provider credentials must use the existing secret-management mechanism.
Reviewer absence must be explicit. Thresholds must be
language-pair/content-type specific and versioned, not scattered
constants. Enable mandatory human approval for technical content when
risk requires it.

## 16. Observability

Counters: - `source_ir_validation_failures_total` -
`source_ir_paragraph_split_suspected_total` -
`source_ir_duplicate_blocks_total` -
`translation_validation_failures_total` -
`translation_duplicate_content_total` -
`translation_character_anomalies_total` -
`translation_protected_span_failures_total` -
`translation_numeric_mismatches_total` -
`translated_ir_mapping_failures_total` -
`pdf_text_roundtrip_failures_total` - `translation_retry_total` -
`translation_review_required_total`

Track durations for source IR validation, translation validation,
independent review, retry, translated IR validation, and PDF round-trip.

Track ratios for first-attempt pass rate, retry rate, human-review rate,
source-target mapping coverage, protected-span preservation, and PDF
round-trip coverage.

Never use raw source or translated text as metric labels.

## 17. Test strategy

### Unit tests

-   Wrapped-line paragraph reconstruction.
-   Paragraph continuation across pages.
-   Multi-column reading order.
-   List/table boundaries.
-   Duplicate phrase/sentence detection.
-   Valid and invalid Devanagari sequences.
-   Unicode replacement/control/private-use anomalies.
-   Protected token missing/duplicate/modified.
-   Numeric/unit association.
-   Equation integrity.
-   Source-target block mapping.
-   Retry decisions.
-   PDF text round-trip.

### Integration tests

1.  Born-digital selectable-text PDF.
2.  Image-only scanned PDF.
3.  Mixed text/image PDF.
4.  Garbled native text layer.
5.  OCR/native disagreement.
6.  Bodhan Translate duplicate output.
7.  Suspicious characters/symbols.
8.  Omitted sentence or condition.
9.  Changed number, unit, or product association.
10. Correct text but broken block mapping.
11. Renderer duplicates/splits paragraphs.
12. Renderer breaks inline math/units.
13. Missing font/glyph and Indic shaping failures.
14. Provider timeout, rate limit, malformed response, and retry
    exhaustion.

Maintain a versioned corpus of source PDFs, expected source IR,
protected spans, approved translations, intentionally defective
translations, expected issue codes, and render assertions. Critical
expected facts must be reviewed and version-controlled, not generated
solely by a model.

## 18. Acceptance criteria

**Source IR** - \[ \] Visual line wraps are not automatically semantic
paragraph boundaries. - \[ \] Suspected splits/merges and reading-order
errors are detected. - \[ \] Parent-child, list, table, equation, and
provenance integrity is checked. - \[ \] Critical source IR defects
block translation.

**Translation** - \[ \] Provider API success is not quality success. -
\[ \] Duplicate, omission/addition, and character anomalies are
detected. - \[ \] Valid Indic sequences are not rejected by simplistic
character rules. - \[ \] Protected spans, numbers, units, and equations
are verified. - \[ \] Reviewer absence is `NOT_CONFIGURED`, not a
pass. - \[ \] Retries are bounded and auditable.

**Translated IR** - \[ \] Stable source-target block mapping is
preserved. - \[ \] Missing, duplicate, reordered, and fragmented blocks
are detected. - \[ \] Paragraph continuity is independent of visual page
wrapping. - \[ \] Failed blocks cannot enter rendering.

**PDF** - \[ \] Generated text is extracted and compared with approved
translated IR. - \[ \] Missing/extra/duplicate text and broken math are
detected. - \[ \] Text round-trip and visual QA are separate gates. - \[
\] Indic shaping, glyphs, clipping, and overlap are checked.

**Operations** - \[ \] Each gate creates a structured report. - \[ \]
Metrics do not expose document content. - \[ \] Provider response,
retry, glossary, and policy versions are traceable. - \[ \] Problem 47
and multilingual regression tests pass.

## 19. Implementation milestones

1.  **Contracts/evidence model:** extend current IR with stable IDs,
    relationships, hashes, provenance; define common
    reports/statuses/issue codes.
2.  **Source IR integrity:** improve paragraph recovery, reading order,
    relationship validation, fixtures, and Gate A.
3.  **Deterministic translation validation:** response, placeholder,
    protected-span, numeric, unit, equation, duplicate, Unicode, and
    terminology checks.
4.  **Independent review/retry:** optional external reviewer adapter,
    structured evidence, bounded retry, human-review handoff.
5.  **Translated IR alignment:** stable mappings,
    structure/order/coverage validation, Gate C.
6.  **PDF round-trip:** PyMuPDF extraction of generated PDF, comparison
    with approved target IR, separate visual QA.
7.  **Regression/production hardening:** Problem 47, multilingual/Indic
    corpus, threshold calibration, metrics, retention, and runbooks.

## 20. Job states and user-facing behavior

Suggested states: - `INGESTED` - `SOURCE_IR_VALIDATING` -
`SOURCE_IR_REVIEW_REQUIRED` - `TRANSLATING` - `TRANSLATION_VALIDATING` -
`TRANSLATION_RETRYING` - `TRANSLATION_REVIEW_REQUIRED` -
`TRANSLATED_IR_VALIDATING` - `RENDERING` - `PDF_ROUNDTRIP_VALIDATING` -
`VISUAL_QA` - `COMPLETED` - `FAILED_QUALITY` - `FAILED_SYSTEM`

Distinguish: - `FAILED_SYSTEM`: infrastructure/provider execution
failure. - `FAILED_QUALITY`: document/content integrity did not meet
policy. - `REVIEW_REQUIRED`: safe correctness cannot be established
automatically.

The UI should show page/block location, issue category/severity,
permitted evidence excerpt, retry availability, review requirement, and
whether PDF delivery is blocked.

## 21. Security and reliability

-   Restrict access to raw provider requests/responses and document
    text.
-   Redact text from ordinary logs, traces, and metrics.
-   Apply retention/deletion policy to validation artifacts.
-   Keep immutable audit records for translation corrections.
-   Apply timeouts, rate limits, and circuit breakers to reviewer
    adapters.
-   Treat reviewer output as untrusted; it cannot modify IR or invoke
    tools.
-   Make validators idempotent where possible.
-   Prevent retries from creating duplicate blocks or duplicate billing
    events.
-   Use idempotency keys/correlation IDs where supported.

## 22. Implementation decisions to record

Record: 1. Which current IR classes will be extended. 2. Which external
provider, if any, will perform independent semantic review. 3. Initial
supported language pairs/domains. 4. Authoritative glossary source. 5.
Content types requiring human approval. 6. Language-pair-specific
anomaly thresholds. 7. Raw artifact retention/access policy. 8. Whether
target paragraph structure may differ for specific language pairs.

Do not delay deterministic checks while selecting a reviewer provider.
Build the reviewer interface so a provider can be configured later.

## 23. Final principle

Translation Studio must independently establish that: 1. The source
document was recovered correctly. 2. The translation preserves meaning
and technical facts. 3. The translated IR preserves source structure and
relationships. 4. The generated PDF contains the approved translated
content. 5. The rendered document is typographically and visually
acceptable.

If any condition cannot be established, retry safely, request review, or
block delivery. Never silently mark uncertain or corrupted content as
successful.
