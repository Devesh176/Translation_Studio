# Modification V2 — Translation Quality, Document Integrity, Provider Orchestration, and PDF Fidelity

**Project:** Translation Studio  
**Document:** Modification V2  
**Purpose:** Implementation specification for improving the existing PDF translation application  
**Status:** Proposed implementation  
**Relationship:** Extends Modification V1; does not replace the existing architecture.

---

# 1. Objective

Modification V2 improves the existing Translation Studio application so that translated PDFs preserve the source document's:

- Complete content and meaning.
- Section and paragraph structure.
- Reading order and hierarchy.
- Lists, numbering, and indentation.
- Commands, configuration blocks, identifiers, URLs, and other technical content.
- Technical facts, values, units, and relationships.
- Typography and visual design.
- Page composition and document usability.

It also introduces controlled integration between Bodhan services and OpenRouter services.

The application must not consider a translation successful merely because a translation API returns a response or a PDF renderer generates a file.

A translated PDF must pass independent validation at every important stage before release.

## 1.1 Primary goals

1. Improve source PDF extraction and semantic Document IR recovery.
2. Prevent duplication, omission, reordering, and fragmentation of extracted content.
3. Protect technical and structured content from unwanted translation or modification.
4. Improve translation quality through independent verification.
5. Introduce configurable Bodhan and OpenRouter provider orchestration.
6. Validate source-target semantic alignment.
7. Improve Indic-script typography and Unicode rendering.
8. Improve translated PDF reconstruction and pagination.
9. Introduce final PDF text round-trip validation.
10. Add visual regression and document-quality reporting.
11. Establish reusable regression tests for all observed failure classes.
12. Prevent defective PDFs from being released as successful translations.

## 1.2 Definition of success

The application should achieve:

- Complete source-content recovery.
- Complete translation of translatable content.
- No unexplained duplicated or missing content.
- No unintended changes to protected technical content.
- No incorrect associations between entities, values, units, labels, or instructions.
- Correct target-language grammar and readability.
- Correct script shaping and font rendering.
- Preservation of document hierarchy and design intent.
- Correct final PDF text extraction.
- No critical layout defects.

A literal pixel-for-pixel match between source and target PDFs is not required. Different languages naturally produce different line lengths and page counts.

The target is semantic fidelity, technical correctness, and strong visual similarity.

---

# 2. Scope

## 2.1 Included

This modification covers the following application components:

- PDF extraction.
- OCR integration.
- Native text extraction.
- OCR/native reconciliation.
- Source Document IR construction.
- Source IR validation.
- Paragraph and section reconstruction.
- Protected-span identification.
- Technical translation profiles.
- Translation-provider orchestration.
- Bodhan Translate integration.
- OpenRouter integration.
- Independent translation verification.
- Targeted translation retries.
- Source-target alignment.
- Expected-facts extraction and validation.
- Unicode normalization and validation.
- Indic-script text shaping.
- Font management.
- Layout reflow.
- PDF reconstruction.
- PDF round-trip validation.
- Visual regression.
- Quality reporting.
- Job states and release gates.
- Regression testing.
- Observability and metrics.

## 2.2 Excluded

The following are outside the scope of Modification V2:

- Training or fine-tuning custom language models.
- Hosting local LLMs or GPU-based translation models.
- Replacing the existing Docker/Kubernetes deployment architecture.
- Replacing Bodhan as the existing primary service without an explicit configuration decision.
- Guaranteeing pixel-perfect matching between different writing systems.
- Automatically accepting unresolved semantic disagreements.
- Automatically rewriting entire documents when only individual nodes have failed validation.

External API services remain the preferred approach.

---

# 3. Required End-to-End Architecture

The existing pipeline must be extended into a staged document-transformation and validation workflow.

## 3.1 Target workflow

```text
Original PDF
    |
    v
PDF Preflight
    |
    +----------------------------+
    |                            |
    v                            v
Bodhan OCR                 PyMuPDF Native Extraction
Every Page                 Every Page
    |                            |
    +-------------+--------------+
                  |
                  v
       Source Extraction Reconciliation
                  |
                  v
          Source Semantic Document IR
                  |
                  v
           Source IR Validation
                  |
           PASS / RETRY / REVIEW
                  |
                  v
          Protected Span Detection
                  |
                  v
       Technical Translation Profile
                  |
                  v
           Primary Translation
              Bodhan
                  |
                  v
          Translated Document IR
                  |
                  v
       Independent Translation Review
             OpenRouter
                  |
                  v
          Translation Validation
                  |
          PASS / RETRY / REVIEW
                  |
                  v
       Targeted Provider Correction
          Bodhan or OpenRouter
                  |
                  v
       Source-Target IR Alignment
                  |
                  v
       Expected-Facts Validation
                  |
                  v
         Translated IR Validation
                  |
                  v
           Hindi/Target Text Shaping
                  |
                  v
             Layout Reflow
                  |
                  v
              PDF Rendering
                  |
                  v
         PDF Text Round-Trip Validation
                  |
                  v
            Visual Regression QA
                  |
                  v
             Release Validation
                  |
            PASS / FAIL / REVIEW
                  |
                  v
           Final Translated PDF
```

## 3.2 Design principles

The implementation must follow these principles:

1. The original source PDF is authoritative.
2. Source IR is the authoritative representation of source structure and content.
3. Translation providers may translate eligible text but must not redefine document structure.
4. Protected content must remain associated with its original source node.
5. Translation verification must be independent of the primary translation response.
6. Rendering must consume validated translated IR, not unstructured translation strings.
7. Final PDF text must be checked against translated IR.
8. Critical validation failures must prevent release.
9. Retries must be bounded and node-specific.
10. All provider decisions must be deterministic and auditable.

---

# 4. PDF Preflight and Source Extraction Improvements

## 4.1 PDF preflight

Before extraction begins, inspect the source PDF.

Collect:

- Page count.
- Page dimensions.
- Page rotation.
- PDF metadata.
- Embedded fonts.
- Text availability.
- Image availability.
- Scanned-page indicators.
- Page-level text density.
- Page-level image coverage.
- Text-block bounding boxes.
- Document encryption or access restrictions.
- Existing annotations where relevant.

Classify pages as:

- Digitally generated.
- Scanned.
- Mixed digital and scanned.
- Image-heavy.
- Text-heavy.
- Unknown or unsupported.

Classification is for choosing extraction and rendering strategies. It must not be used to skip required OCR or native extraction.

## 4.2 OCR and native extraction

Continue the existing V1 requirement:

- Run Bodhan OCR on every page.
- Run PyMuPDF native extraction on every page.
- Reconcile both extraction results.

PyMuPDF native extraction must never be described or treated as OCR.

Store the output of each extraction method separately before reconciliation.

### OCR extraction record

Each OCR result should include:

```json
{
  "page_number": 1,
  "text": "Extracted text",
  "confidence": 0.98,
  "bbox": [10, 20, 300, 60],
  "language": "eng",
  "source": "bodhan_ocr",
  "block_type": "text"
}
```

The confidence and bounding-box values are illustrative.

Use the actual values supplied by the provider. If a field is unavailable, store null rather than inventing a value.

### Native extraction record

Each native extraction result should include:

```json
{
  "page_number": 1,
  "text": "Extracted text",
  "bbox": [10, 20, 300, 60],
  "font_name": "EmbeddedFont",
  "font_size": 11,
  "source": "pymupdf_native",
  "block_type": "text"
}
```

Record actual extraction metadata where available.

## 4.3 Reconciliation

Implement a dedicated source reconciliation component.

It must:

1. Compare OCR and native extraction results.
2. Match text blocks using page coordinates and text similarity.
3. Identify duplicate extraction of the same visual region.
4. Identify content present in only one extraction result.
5. Identify material text disagreements.
6. Preserve extraction provenance.
7. Produce confidence and reconciliation status.
8. Flag ambiguous blocks for review.

Do not simply concatenate OCR output and native extraction output.

Do not automatically discard a text block merely because it resembles another block. Repeated text may be legitimate.

### Reconciliation result

```json
{
  "node_candidate_id": "candidate-001",
  "page_number": 1,
  "native_text": "Native text",
  "ocr_text": "OCR text",
  "reconciled_text": "Selected text",
  "reconciliation_status": "MATCHED",
  "confidence": 0.98,
  "provenance": [
    "pymupdf_native",
    "bodhan_ocr"
  ],
  "requires_review": false
}
```

### Reconciliation statuses

- `MATCHED`
- `NATIVE_ONLY`
- `OCR_ONLY`
- `CONFLICT`
- `DUPLICATE_REGION`
- `REVIEW_REQUIRED`

A conflict must not be resolved by blindly selecting whichever extraction result contains more text.

## 4.4 Extraction quality checks

Add checks for:

- Empty page extraction.
- Unexpectedly low text density.
- Duplicate text regions.
- Text outside page bounds.
- Overlapping text regions.
- Suspicious reading order.
- Missing expected document regions.
- Invalid Unicode.
- Replacement characters.
- Unexpected control characters.
- Extraction placeholders.
- Unresolved content markers.

Any unresolved placeholder must be treated as a validation failure.

---

# 5. Source Semantic Document IR Improvements

The source IR must represent the document semantically rather than as a flat sequence of extracted strings.

## 5.1 Supported node types

At minimum, support:

```text
DOCUMENT
PAGE
TITLE
SUBTITLE
SECTION_HEADING
SUBSECTION_HEADING
PARAGRAPH
ORDERED_LIST
ORDERED_LIST_ITEM
UNORDERED_LIST
UNORDERED_LIST_ITEM
TABLE
TABLE_ROW
TABLE_CELL
CODE_BLOCK
INLINE_CODE
CONFIGURATION_BLOCK
EQUATION
FIGURE
IMAGE
CAPTION
FOOTNOTE
HEADER
FOOTER
CONTACT_INFORMATION
URL
EMAIL
FILE_PATH
PLACEHOLDER
UNKNOWN_REGION
```

The model must allow additional node types without breaking older documents.

## 5.2 Required IR properties

Each semantic node should contain:

```json
{
  "id": "stable-node-id",
  "type": "PARAGRAPH",
  "parent_id": "parent-node-id",
  "children": [],
  "source_page": 1,
  "reading_order": 10,
  "source_text": "Source text",
  "normalized_text": "Normalized source text",
  "bbox": [10, 20, 300, 80],
  "style_id": "style-001",
  "translation_eligible": true,
  "protected": false,
  "provenance": {
    "native_extraction": true,
    "ocr": true
  },
  "confidence": 0.99,
  "validation_status": "PENDING"
}
```

Requirements:

- Node IDs must remain stable throughout the translation job.
- Parent-child relationships must be explicit.
- Reading order must be explicit.
- Page references must be preserved.
- Style references must be preserved.
- Source text must remain available and immutable.
- Translation eligibility must be explicit.
- Protected status must be explicit.
- Provenance must be retained.

## 5.3 Paragraph reconstruction

This is a critical improvement.

The source PDF may represent a paragraph using multiple visual text lines or separate PDF spans.

The IR builder must reconstruct these into one logical paragraph where appropriate.

It must not assume:

- One PDF line equals one paragraph.
- One OCR box equals one paragraph.
- One extraction span equals one sentence.
- Every visual line break represents a semantic break.

Use:

- Bounding-box proximity.
- Font and style similarity.
- Indentation.
- Paragraph spacing.
- Punctuation and sentence continuity.
- Section boundaries.
- List markers.
- Page continuation indicators.
- Reading-order evidence.

Paragraph reconstruction must retain source-region provenance so the original page locations remain available for layout and review.

## 5.4 Heading and section hierarchy

Implement heading classification and parent-child assignment.

A heading must remain attached to the content belonging to its section.

Validate:

- Heading sequence.
- Heading hierarchy.
- Section boundaries.
- Subsection relationships.
- Orphan headings.
- Content assigned to the wrong section.

A heading must not appear after its own paragraph or list in the reconstructed reading order unless the original document explicitly uses that arrangement.

## 5.5 List reconstruction

Support:

- Ordered lists.
- Unordered lists.
- Nested lists.
- Mixed nested lists.
- Multi-line list items.
- Lists continuing across pages.
- Numbering restarts.
- List indentation.
- Bullet style preservation.

Each list item must have a stable identity and parent list reference.

Do not translate or reconstruct numbered items as unrelated paragraphs.

## 5.6 Code and configuration reconstruction

Code and configuration blocks must be modeled separately from ordinary prose.

Preserve:

- Line order.
- Indentation.
- Newlines.
- Whitespace where semantically relevant.
- Symbols.
- Operators.
- Comments.
- Key-value relationships.
- List markers.
- Delimiters.

A YAML block, for example, must remain one structured configuration node, not a sequence of independently translated strings.

---

# 6. Source IR Validation

Introduce a mandatory source IR validation gate.

## 6.1 Required validations

Validate:

1. Every source page is represented.
2. Every detected meaningful text region is accounted for.
3. No unresolved placeholder remains.
4. Reading order is coherent.
5. Heading hierarchy is valid.
6. Paragraphs are not fragmented unnecessarily.
7. Lists preserve numbering and nesting.
8. Code/configuration blocks are complete.
9. Parent-child relationships are valid.
10. Duplicate extraction has been reconciled.
11. No node is outside the source page bounds.
12. Material OCR/native conflicts are resolved or flagged.

## 6.2 Source IR status

Use:

- `PASS`
- `RETRY`
- `REVIEW_REQUIRED`
- `FAIL`

A failed source IR must not proceed to primary translation.

A review-required source IR may proceed only if the application has an explicit policy for low-risk ambiguity. Critical content conflicts must block translation.

---

# 7. Protected Span Detection

Protected-span handling must be improved throughout the application.

## 7.1 Protected content categories

Identify and preserve:

- Shell commands.
- Command-line flags.
- Programming code.
- Configuration syntax.
- YAML keys and values.
- JSON keys and values.
- XML tags and attributes.
- URLs.
- Email addresses.
- File names.
- Directory paths.
- Package names.
- Software product names.
- Environment names.
- Version numbers.
- API identifiers.
- Environment variables.
- Keyboard shortcuts.
- Mathematical expressions.
- Numbers and units.
- Equations and operators.
- Placeholders.
- Inline code.
- Technical identifiers.
- Structured labels.

## 7.2 Protected span representation

```json
{
  "span_id": "protected-span-001",
  "node_id": "source-node-001",
  "span_type": "COMMAND",
  "source_value": "exact-source-value",
  "start_offset": 0,
  "end_offset": 20,
  "immutable": true,
  "preservation_policy": "EXACT"
}
```

Use offsets appropriate to the application's canonical text representation.

## 7.3 Span preservation

Each protected span must:

1. Have a stable span ID.
2. Be associated with its source node.
3. Have an explicit preservation policy.
4. Be carried through translation.
5. Be validated after translation.
6. Be validated after translated IR reconstruction.
7. Be validated after PDF rendering.

Where a protected span must appear inline, preserve its association and relative position with the translated surrounding text.

Do not use simple string replacement without verifying that the protected span is being restored to the correct semantic location.

## 7.4 Protection failure handling

If a protected span is altered, missing, duplicated, or moved to an incorrect context:

- Mark the node `PROTECTED_SPAN_CHANGED` or `PROTECTED_SPAN_MISSING`.
- Attempt a bounded repair if the association is unambiguous.
- Otherwise retry translation using the protected-span manifest.
- If the issue remains unresolved, require review.

---

# 8. Technical Translation Profiles

Introduce a reusable translation profile system.

## 8.1 Profile contents

A profile must support:

```json
{
  "profile_id": "technical-document-hi",
  "source_language": "auto",
  "target_language": "hi",
  "locale": "hi-IN",
  "domain": "technical_documentation",
  "tone": "clear_instructional",
  "glossary_id": "technical-glossary",
  "terminology_policy": "CONSISTENT",
  "transliteration_policy": "CONFIGURABLE",
  "protected_span_policy": "STRICT",
  "number_preservation": true,
  "unit_preservation": true,
  "structure_preservation": true,
  "allow_content_additions": false,
  "allow_content_omissions": false
}
```

## 8.2 Glossary requirements

Support:

- Preferred translation.
- Preferred transliteration.
- Terms that must remain unchanged.
- Product names.
- UI labels.
- Domain-specific vocabulary.
- Disallowed translations.
- Context-specific terminology.
- Approved alternate terms.

The glossary must be versioned.

The same term should be translated consistently across the document unless an explicit context-specific rule applies.

## 8.3 Translation policy

Use separate policies for:

- Titles.
- Section headings.
- Ordinary paragraphs.
- Warnings.
- Instructions.
- UI labels.
- Code comments.
- Captions.
- Footnotes.

The system must not blindly translate product names, identifiers, commands, or configuration syntax.

For UI labels, allow a configurable approach:

- Target-language translation only.
- English label only.
- Target-language label with English in parentheses.

---

# 9. Bodhan and OpenRouter Provider Orchestration

Introduce a provider-independent translation orchestration layer.

## 9.1 Provider architecture

All translation providers must implement a common interface.

```python
class TranslationProvider:
    async def translate(
        self,
        source_nodes,
        target_language,
        translation_profile,
        protected_spans,
        context
    ):
        raise NotImplementedError
```

The interface must support:

- Provider identification.
- Model identification where applicable.
- Request IDs.
- Timeouts.
- Retries.
- Error classification.
- Usage information.
- Structured response parsing.
- Provider-specific metadata.
- Correlation IDs.

## 9.2 Provider responsibilities

### Bodhan

Use Bodhan as the primary translation provider initially.

Responsibilities:

- Translate eligible semantic nodes.
- Preserve supplied structure.
- Follow translation profile.
- Preserve protected spans.
- Return structured translation output.
- Provide request metadata where available.

### OpenRouter

Use OpenRouter for:

1. Independent translation review.
2. Targeted alternative translation.
3. Targeted correction of failed nodes.
4. Optional adjudication of disagreements.

Do not use OpenRouter as a mandatory second full-document translator.

The application should call it selectively according to validation results and configuration.

## 9.3 Independent reviewer interface

```python
class TranslationReviewer:
    async def review(
        self,
        source_nodes,
        translated_nodes,
        expected_facts,
        translation_profile,
        protected_spans
    ):
        raise NotImplementedError
```

The reviewer should return structured findings.

Example:

```json
{
  "node_id": "node-001",
  "status": "REVIEW_REQUIRED",
  "issues": [
    {
      "code": "SEMANTIC_RELATIONSHIP_CHANGED",
      "severity": "CRITICAL",
      "source_evidence": "Source evidence",
      "target_evidence": "Target evidence",
      "explanation": "The translated relationship is ambiguous.",
      "suggested_action": "TARGETED_CORRECTION"
    }
  ],
  "suggested_correction": null,
  "confidence": 0.91
}
```

The example is a schema illustration, not a requirement that a model provide calibrated confidence.

Do not treat model-generated confidence as a deterministic quality guarantee.

## 9.4 Primary translation strategy

Recommended default:

```text
Source IR
    |
    v
Protected-span preparation
    |
    v
Bodhan Translate
    |
    v
Independent verification through OpenRouter
    |
    v
Validation decision
    |
    +---- PASS --------------------+
    |                              |
    +---- TARGETED FAILURE         |
    |             |                |
    |             v                |
    |      Targeted correction     |
    |             |                |
    |             v                |
    |      Re-verification         |
    |             |                |
    +-------------+----------------+
                  |
                  v
          Validated translated IR
```

## 9.5 OpenRouter targeted correction

When a translation node fails:

Send only:

- Original source node.
- Relevant neighboring context.
- Current translation.
- Translation profile.
- Glossary.
- Protected-span manifest.
- Exact validation findings.
- Expected-facts information where relevant.

Request a corrected translation of the affected node.

Do not send the entire document unless the failure is demonstrably document-wide.

## 9.6 Provider selection policy

Implement configurable routing rules.

| Condition | Required action |
|---|---|
| Bodhan output passes validation | Accept |
| Grammar or fluency issue | Targeted correction |
| Missing protected span | Reject or repair with exact protection |
| Altered technical fact | Critical failure |
| Missing source statement | Critical failure |
| Duplicate translated block | Repair translated node mapping |
| Reviewer disagreement | Adjudication or human review |
| Provider timeout | Configured retry/fallback |
| Provider unavailable | Use permitted fallback or pause |
| Repeated validation failure | Stop retries and require review |

## 9.7 Provider retry limits

Retries must be bounded.

Example configuration:

```yaml
translation:
  primary_provider: bodhan
  review_provider: openrouter
  targeted_correction_provider: openrouter
  max_translation_attempts: 2
  max_review_attempts: 2
  max_correction_attempts: 2
  retry_only_failed_nodes: true
  require_independent_review: true
  review_critical_nodes: true
```

These values are configurable defaults and should be adjusted based on observed provider quality, cost, and latency.

Avoid infinite retries or repeated full-document translation.

## 9.8 Provider disagreement policy

If Bodhan and OpenRouter disagree:

1. Compare both candidates against the original source.
2. Compare both against expected facts.
3. Verify protected spans.
4. Evaluate translation grammar and meaning.
5. Record the competing outputs.
6. Accept only when deterministic checks and independent evidence support a clear decision.
7. Otherwise mark `REVIEW_REQUIRED`.

Do not use majority voting as the final correctness mechanism.

---

# 10. Independent Translation Verification

A successful API response is not proof of a correct translation.

Create a dedicated translation verification stage.

## 10.1 Required checks

### Completeness

Detect:

- Missing sentences.
- Missing paragraphs.
- Missing instructions.
- Missing conditions.
- Missing warnings.
- Missing qualifiers.
- Missing list items.

### Duplication

Detect:

- Repeated words.
- Repeated phrases.
- Repeated sentences.
- Repeated paragraphs.
- Duplicate list items.
- Duplicate section content.

### Semantic fidelity

Detect:

- Changed meaning.
- Reversed conditions.
- Incorrect cause-effect relationships.
- Incorrect entity relationships.
- Incorrect instruction sequence.
- Changed restrictions.
- Changed requirements.

### Technical consistency

Detect:

- Changed numbers.
- Changed units.
- Changed versions.
- Changed filenames.
- Changed commands.
- Changed values.
- Incorrect value-to-entity associations.
- Incorrect labels.
- Missing technical qualifiers.
- Incorrect mathematical expressions.

### Grammar and readability

Detect:

- Ungrammatical sentences.
- Awkward target-language phrasing.
- Fragmented sentences.
- Unnatural word order.
- Inconsistent terminology.
- Confusing instructions.

### Character integrity

Detect:

- Replacement characters.
- Unexpected symbols.
- Malformed punctuation.
- Invalid Unicode.
- Script corruption.
- Unexpected markup.
- Unintended transliteration.

### Unsupported additions

Detect content introduced by the translation that has no support in the source.

## 10.2 Verification output

Every finding must include:

- Issue code.
- Severity.
- Source node ID.
- Source evidence.
- Target evidence.
- Explanation.
- Recommended repair.
- Provider and model.
- Verification timestamp.
- Review status.

## 10.3 Verification must be source-grounded

The reviewer must receive the original source text.

Reviewing the Hindi text alone is insufficient to determine whether the translation preserves the source meaning.

The reviewer must not invent missing source information or replace source facts with general domain assumptions.

---

# 11. Expected-Facts Extraction and Validation

This is a new critical component for technical documents.

## 11.1 Objective

A translated paragraph can contain all the correct numbers but still attach them to the wrong entities or conditions.

Introduce an expected-facts representation that records technical meaning independently of the translated wording.

## 11.2 Expected-facts schema

```json
{
  "fact_id": "fact-001",
  "source_node_id": "node-001",
  "entity": "entity-name",
  "attribute": "attribute-name",
  "value": "source-value",
  "unit": "source-unit",
  "relationship": "relationship-description",
  "condition": "applicable-condition",
  "source_evidence": "Original source evidence",
  "criticality": "HIGH"
}
```

Fields may be null when the source does not provide the information.

Do not infer facts that are absent from the source.

## 11.3 Fact categories

Support:

- Entities.
- Attributes.
- Values.
- Units.
- Labels.
- Relationships.
- Conditions.
- Constraints.
- Instructions.
- Sequences.
- Thresholds.
- Quantities.
- Mathematical expressions.
- Version identifiers.

## 11.4 Validation

Compare translated content with expected facts.

Validate:

- Value preservation.
- Unit preservation.
- Entity association.
- Attribute association.
- Relationship preservation.
- Condition preservation.
- Constraint preservation.
- Instruction sequence.
- Negation.
- Comparison direction.
- Mathematical operators.

An incorrect relationship must be treated as a semantic error even if all individual values are present.

## 11.5 Fact extraction safeguards

Expected-facts extraction may use an external model, but:

- Source IR remains authoritative.
- Model-extracted facts must retain source evidence.
- Ambiguous facts must be flagged.
- Critical facts must be independently validated.
- Missing evidence must not be replaced with guesses.

---

# 12. Source-Target Document IR Alignment

The source and translated IR must maintain explicit mapping.

## 12.1 Stable identity

Each translated node must retain the source node ID.

Example:

```json
{
  "source_node_id": "source-node-001",
  "target_node_id": "target-node-001",
  "mapping_type": "ONE_TO_ONE",
  "target_language": "hi",
  "translation_status": "VALIDATED"
}
```

## 12.2 Supported mapping types

- `ONE_TO_ONE`
- `ONE_TO_MANY`
- `MANY_TO_ONE`
- `PRESERVED_UNTRANSLATED`
- `NOT_TRANSLATION_ELIGIBLE`

Many-to-one and one-to-many mappings require explicit reasons and source references.

## 12.3 Alignment validation

Check:

1. Every source node has a mapping.
2. Every translated node has a valid source reference.
3. No source node is unintentionally omitted.
4. No target node is duplicated.
5. Parent-child relationships are preserved.
6. Reading order remains valid.
7. List membership is preserved.
8. Code/configuration blocks remain intact.
9. Protected spans remain associated with the correct node.
10. Section relationships remain correct.

## 12.4 No flat-string reconstruction

Do not construct translated IR by concatenating a list of translated strings.

Translation output must be mapped back to the original semantic nodes.

If the provider returns content in a different order or changes node IDs, the application must reconcile it against the submitted request. If the mapping is ambiguous, fail validation.

---

# 13. Unicode and Indic-Script Typography

The application must treat Indic typography as a script-shaping problem, not a simple font-selection problem.

## 13.1 Font requirements

Implement a font management component that:

- Selects fonts with the required target-script coverage.
- Verifies font availability.
- Verifies required glyph coverage.
- Supports embedded fonts.
- Supports font fallback.
- Logs fallback decisions.
- Prevents unsupported glyph substitution.
- Validates final PDF font embedding.

Use properly licensed fonts suitable for the application's distribution model.

## 13.2 Shaping requirements

Use a shaping engine that supports OpenType features, such as HarfBuzz.

Support:

- Glyph substitution.
- Glyph positioning.
- Combining marks.
- Matras.
- Conjuncts.
- Virama.
- Reph.
- Script-specific ligatures.
- Mixed-script text.
- Grapheme clusters.

Do not measure each Unicode code point as an independent printable character.

## 13.3 Grapheme-safe operations

Text segmentation and line wrapping must not split:

- Combining sequences.
- Grapheme clusters.
- Conjunct sequences.
- Script-dependent shaping sequences.

Use Unicode-aware segmentation and shaping output.

## 13.4 Measurement

The renderer must measure shaped glyph runs rather than raw character counts.

Required sequence:

```text
Target Text
    |
    v
Unicode Validation
    |
    v
Script Detection
    |
    v
Font Selection
    |
    v
Text Shaping
    |
    v
Glyph Run Measurement
    |
    v
Line Breaking
    |
    v
Layout Placement
```

## 13.5 Mixed-language text

Support paragraphs containing:

- Target-language script.
- English product names.
- Commands.
- URLs.
- Numbers.
- Mathematical expressions.
- Technical abbreviations.

Apply appropriate font and directionality rules to each span.

Do not allow mixed-script content to break command strings or technical identifiers.

## 13.6 Rendering validation

Detect:

- Missing glyphs.
- Invalid glyph substitution.
- Broken conjuncts.
- Misplaced combining marks.
- Clipped glyphs.
- Overlapping lines.
- Incorrect line height.
- Incorrect baseline.
- Unsupported font fallback.
- Invalid extracted Unicode.

A PDF that contains the right Unicode code points but visually renders incorrect shaping must fail typography validation.

---

# 14. Translation Layout and Page Reconstruction

The translated document must preserve the original design intent while allowing natural target-language reflow.

## 14.1 Source style profile

Extract a style profile containing:

- Page dimensions.
- Margins.
- Header/footer regions.
- Font families.
- Font sizes.
- Font weights.
- Text colors.
- Heading colors.
- Alignment.
- Paragraph spacing.
- Line spacing.
- Indentation.
- Bullet styles.
- Numbering styles.
- Borders.
- Backgrounds.
- Code-block styles.
- Table styles.

Represent styles using reusable style IDs.

## 14.2 Target layout

The renderer must:

1. Load validated translated IR.
2. Resolve style references.
3. Shape text.
4. Measure target-language glyph runs.
5. Calculate line breaks.
6. Calculate block heights.
7. Place blocks in reading order.
8. Reflow sections.
9. Recalculate pagination.
10. Render final PDF.

## 14.3 Layout constraints

Implement checks for:

- Text outside page bounds.
- Text overlapping another block.
- Clipped text.
- Orphan headings.
- Isolated list markers.
- Broken paragraphs.
- Unintended blank regions.
- Code blocks split incorrectly.
- Incorrect indentation.
- Inconsistent heading spacing.
- Incorrect page margins.
- Footer collisions.
- Header collisions.

## 14.4 Page-count policy

Do not require the translated document to have the same page count as the source.

The renderer may:

- Add pages.
- Remove pages.
- Move complete sections.
- Rebalance whitespace.
- Adjust block spacing within style constraints.

Do not shrink all text simply to force the original page count.

## 14.5 Rendering strategies

Retain support for appropriate rendering strategies:

- `DIGITAL_OVERLAY`
- `DIGITAL_RECONSTRUCTION`
- `SCANNED_OVERLAY`
- `SCANNED_RECONSTRUCTION`

Where a page contains mixed content, allow region-level rendering strategies.

Preserve non-text visual content such as:

- Images.
- Logos.
- Signatures.
- Stamps.
- Diagrams.
- Borders.
- Backgrounds.
- Decorative elements.

Do not erase an entire scanned page simply to remove text.

---

# 15. PDF Text Round-Trip Validation

Introduce a mandatory post-render validation stage.

A successfully generated PDF is not automatically a valid translated document.

## 15.1 Round-trip process

```text
Validated Translated IR
        |
        v
     PDF Render
        |
        v
  Generated PDF
        |
        v
 PyMuPDF Text Extraction
        |
        v
 Reconstructed PDF Text
        |
        v
 Compare Against Translated IR
        |
        v
 Round-Trip Validation
```

## 15.2 Required checks

Validate:

1. Every expected target node is represented.
2. No unexpected duplicate node appears.
3. Protected spans remain unchanged.
4. Reading order is preserved.
5. Text is not missing.
6. Text is not unintentionally duplicated.
7. Unicode remains valid.
8. Text is not clipped.
9. No placeholders appear.
10. The extracted content remains semantically consistent with translated IR.

## 15.3 Text comparison

Use a normalization policy that accounts for harmless differences such as:

- PDF extraction whitespace.
- Equivalent line-break representations.
- Normalization forms where explicitly permitted.
- Layout-induced line wrapping.

Do not normalize away meaningful differences in:

- Numbers.
- Commands.
- Identifiers.
- Units.
- Mathematical expressions.
- Punctuation that changes meaning.
- Protected spans.

## 15.4 Round-trip result

```json
{
  "document_id": "document-001",
  "validation_stage": "PDF_ROUNDTRIP",
  "status": "PASS",
  "expected_nodes": 100,
  "matched_nodes": 100,
  "missing_nodes": 0,
  "duplicate_nodes": 0,
  "protected_span_failures": 0,
  "unicode_failures": 0,
  "placeholder_failures": 0,
  "issues": []
}
```

The counts are illustrative.

---

# 16. Visual Regression and Document Comparison

Introduce a visual regression engine that compares the source PDF and translated PDF.

## 16.1 Comparison objectives

Compare:

- Overall page composition.
- Heading hierarchy.
- Section placement.
- Paragraph positioning.
- List structure.
- Code-block placement.
- Margins.
- Spacing.
- Typography.
- Images and non-text elements.
- Headers and footers.
- Text clipping.
- Text overlap.
- Unexpected whitespace.

## 16.2 Region-based comparison

Do not compare only full-page screenshots.

Use semantic regions:

- Title region.
- Heading regions.
- Paragraph regions.
- List regions.
- Table regions.
- Code regions.
- Figure regions.
- Header/footer regions.

Compare corresponding regions using source-target node mapping.

## 16.3 Visual comparison methods

Support:

- Page rendering.
- Region cropping.
- Structural similarity.
- Bounding-box comparison.
- Text-region occupancy.
- OCR-assisted visual verification.
- Layout deviation detection.

Raw pixel difference should be treated as supporting evidence only.

A translated paragraph naturally differs visually from its source-language counterpart.

## 16.4 Visual issue categories

- `TEXT_OVERLAP`
- `TEXT_CLIPPED`
- `BLOCK_MISPLACED`
- `HEADING_ORPHANED`
- `LIST_STRUCTURE_BROKEN`
- `CODE_BLOCK_BROKEN`
- `FONT_MISMATCH`
- `MISSING_GLYPH`
- `UNEXPECTED_WHITESPACE`
- `MARGIN_DEVIATION`
- `IMAGE_MISSING`
- `BACKGROUND_MISSING`
- `VISUAL_LAYOUT_DEVIATION`

## 16.5 Visual acceptance

A page must not pass visual validation if it contains critical overlap, clipping, missing regions, or unreadable text.

Medium-severity layout deviations may be accepted only within configurable thresholds and documented policy.

---

# 17. Validation Framework and Quality Gates

All validation components must use a consistent result structure.

## 17.1 Standard result

```json
{
  "validation_id": "validation-001",
  "document_id": "document-001",
  "node_id": "node-001",
  "stage": "TRANSLATION",
  "status": "PASS",
  "issues": [],
  "checked_at": "timestamp",
  "provider": null,
  "model": null
}
```

## 17.2 Status values

Use:

- `PASS`
- `RETRY`
- `REVIEW_REQUIRED`
- `FAIL`

## 17.3 Gate behavior

### Source extraction gate

Blocks translation when source extraction is incomplete or ambiguous in critical regions.

### Source IR gate

Blocks translation when document structure or content is invalid.

### Protected-span gate

Blocks acceptance when protected content is missing or modified.

### Translation gate

Blocks acceptance when meaning, completeness, or technical fidelity is incorrect.

### Alignment gate

Blocks rendering when source-target mapping is incomplete or invalid.

### Typography gate

Blocks release when script shaping or glyph rendering is defective.

### PDF round-trip gate

Blocks release when final PDF text differs materially from translated IR.

### Visual QA gate

Blocks release when critical visual defects exist.

## 17.4 Severity levels

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `INFO`

## 17.5 Release policy

The release policy must be configurable but conservative.

Default:

| Finding | Release decision |
|---|---|
| Critical failure | Block |
| Unresolved high-severity issue | Block or require authorized review |
| Medium issue | Review according to configured threshold |
| Low issue | Record and allow according to policy |
| All required gates pass | Release permitted |

No critical issue may be hidden by a high overall quality score.

---

# 18. Error Catalogue

Implement a central error-code catalogue.

| Code | Description | Default severity |
|---|---|---|
| `PDF_PREFLIGHT_FAILED` | Source PDF preflight failed | CRITICAL |
| `PAGE_EXTRACTION_EMPTY` | Expected page extraction is empty | HIGH |
| `OCR_NATIVE_CONFLICT` | Material disagreement between extraction sources | HIGH |
| `SOURCE_NODE_MISSING` | Meaningful source node is missing | CRITICAL |
| `SOURCE_ORDER_INVALID` | Source reading order is incorrect | CRITICAL |
| `SOURCE_DUPLICATE_NODE` | Duplicate source node | HIGH |
| `SOURCE_PARENT_MISMATCH` | Source hierarchy is incorrect | HIGH |
| `PARAGRAPH_FRAGMENTED` | Logical paragraph has been incorrectly split | HIGH |
| `LIST_STRUCTURE_BROKEN` | List hierarchy or numbering is incorrect | HIGH |
| `PLACEHOLDER_LEAKED` | Internal placeholder is present | CRITICAL |
| `PROTECTED_SPAN_MISSING` | Required protected span is missing | CRITICAL |
| `PROTECTED_SPAN_CHANGED` | Protected content was modified | CRITICAL |
| `TRANSLATION_OMISSION` | Source meaning was omitted | CRITICAL |
| `TRANSLATION_ADDITION` | Unsupported content was added | HIGH |
| `TRANSLATION_DUPLICATION` | Content was duplicated | HIGH |
| `TRANSLATION_GRAMMAR` | Target-language grammar is defective | MEDIUM |
| `TRANSLATION_UNNATURAL` | Translation is unnatural or confusing | MEDIUM |
| `SEMANTIC_RELATIONSHIP_CHANGED` | Relationship between facts changed | CRITICAL |
| `TECHNICAL_VALUE_CHANGED` | Technical value changed | CRITICAL |
| `TECHNICAL_UNIT_CHANGED` | Technical unit changed | CRITICAL |
| `TRANSLATION_REVIEW_DISAGREEMENT` | Reviewers disagree on meaning | HIGH |
| `TARGET_IR_NODE_MISSING` | Translated IR node is missing | CRITICAL |
| `TARGET_IR_ORDER_INVALID` | Translated IR order is incorrect | CRITICAL |
| `TARGET_IR_PARENT_MISMATCH` | Target node has incorrect parent | HIGH |
| `UNICODE_INVALID` | Invalid Unicode or unexpected control characters | CRITICAL |
| `GLYPH_MISSING` | Required glyph is unavailable | CRITICAL |
| `SHAPING_INVALID` | Script shaping is defective | CRITICAL |
| `TEXT_OVERLAP` | Rendered text overlaps | HIGH |
| `TEXT_CLIPPED` | Rendered text is clipped | CRITICAL |
| `PDF_ROUNDTRIP_MISMATCH` | PDF text differs materially from translated IR | CRITICAL |
| `VISUAL_LAYOUT_DEVIATION` | Significant layout deviation | MEDIUM |
| `PDF_FONT_NOT_EMBEDDED` | Required font is not embedded | HIGH |
| `PDF_RENDER_FAILED` | PDF rendering failed | CRITICAL |

Issue codes must be stable and versioned.

---

# 19. Configuration Changes

Introduce configurable settings for all new behavior.

Example:

```yaml
document_processing:
  run_ocr_on_every_page: true
  run_native_extraction_on_every_page: true
  reconcile_extraction_sources: true
  require_source_ir_validation: true
  preserve_extraction_provenance: true
  reconstruct_paragraphs: true
  reconstruct_heading_hierarchy: true
  reconstruct_lists: true

protected_spans:
  enabled: true
  strict_mode: true
  preserve_commands: true
  preserve_urls: true
  preserve_emails: true
  preserve_file_paths: true
  preserve_versions: true
  preserve_configuration: true
  preserve_numbers_and_units: true
  preserve_identifiers: true

translation:
  primary_provider: bodhan
  review_provider: openrouter
  correction_provider: openrouter
  require_independent_review: true
  retry_only_failed_nodes: true
  max_translation_attempts: 2
  max_review_attempts: 2
  max_correction_attempts: 2
  allow_unverified_translation: false

translation_validation:
  check_completeness: true
  check_duplication: true
  check_semantic_fidelity: true
  check_technical_facts: true
  check_grammar: true
  check_terminology: true
  check_unicode: true
  check_protected_spans: true
  check_unsupported_additions: true

document_ir:
  preserve_stable_node_ids: true
  preserve_parent_child_relationships: true
  preserve_reading_order: true
  require_source_target_mapping: true
  allow_explicit_one_to_many_mapping: true
  allow_explicit_many_to_one_mapping: true

typography:
  use_script_shaping: true
  shaping_engine: harfbuzz
  grapheme_safe_wrapping: true
  measure_shaped_glyph_runs: true
  embed_fonts: true
  allow_font_fallback: true
  log_font_fallback: true

rendering:
  allow_page_reflow: true
  preserve_source_style_profile: true
  preserve_non_text_regions: true
  avoid_forced_page_count: true
  validate_text_bounds: true
  validate_block_overlap: true

pdf_validation:
  enabled: true
  roundtrip_text_extraction: true
  validate_unicode: true
  validate_protected_spans: true
  validate_node_completeness: true
  validate_duplicates: true
  validate_fonts: true
  validate_clipping: true
  validate_visual_regions: true

release:
  block_on_critical_failure: true
  require_all_mandatory_gates: true
  require_review_for_unresolved_high_severity: true
```

The exact configuration schema should follow the application's existing configuration conventions.

Do not introduce duplicate configuration sources for settings already managed centrally.

---

# 20. Module and Service Changes

Implement the following responsibilities as separate modules or services, adapting names to the current codebase.

| Component | Responsibility |
|---|---|
| `pdf_preflight` | Inspect source PDF and page characteristics |
| `source_reconciler` | Reconcile Bodhan OCR and PyMuPDF native extraction |
| `document_ir_builder` | Build semantic source IR |
| `document_ir_validator` | Validate source IR |
| `paragraph_reconstructor` | Reconstruct logical paragraphs |
| `reading_order_resolver` | Determine reading order |
| `structure_reconstructor` | Recover heading and list hierarchy |
| `protected_span_detector` | Identify protected text |
| `translation_profile_manager` | Manage language and terminology rules |
| `translation_provider_router` | Select translation provider |
| `bodhan_translation_provider` | Bodhan translation adapter |
| `openrouter_translation_provider` | OpenRouter translation adapter |
| `translation_orchestrator` | Execute primary and correction translation |
| `translation_reviewer` | Independent translation review |
| `translation_retry_manager` | Bounded node-specific retries |
| `expected_facts_extractor` | Build source-grounded technical facts |
| `expected_facts_validator` | Validate target facts |
| `translation_alignment_validator` | Validate source-target node mapping |
| `unicode_validator` | Validate text integrity |
| `indic_text_shaper` | Shape Indic text |
| `font_manager` | Manage font selection and embedding |
| `layout_reflow_engine` | Recalculate block placement and pagination |
| `pdf_renderer` | Render translated IR |
| `pdf_roundtrip_validator` | Validate final PDF text |
| `visual_regression_engine` | Compare source and target layout |
| `quality_gate_manager` | Coordinate validation decisions |
| `translation_quality_reporter` | Produce quality reports |

Where the existing application already has equivalent components, extend them rather than creating duplicate services.

---

# 21. Data Model and Persistence Changes

Persist enough information to reproduce and audit each translation job.

## 21.1 Translation job

Store:

- Job ID.
- Source document ID.
- Target language.
- Translation profile ID and version.
- Job status.
- Current pipeline stage.
- Start and completion timestamps.
- Provider configuration.
- Validation summary.
- Release status.

## 21.2 Source IR

Store:

- Stable node IDs.
- Node types.
- Source text.
- Page and bounding-box information.
- Reading order.
- Parent-child relationships.
- Style references.
- Extraction provenance.
- Confidence.
- Validation findings.

## 21.3 Translation records

Store:

- Source node ID.
- Target node ID.
- Source text.
- Translation output.
- Provider.
- Model.
- Provider request ID.
- Prompt/profile version.
- Retry count.
- Review result.
- Correction history.
- Final accepted translation.

## 21.4 Protected spans

Store:

- Span ID.
- Source node ID.
- Span type.
- Exact source value.
- Target association.
- Preservation policy.
- Validation status.

## 21.5 Validation records

Store:

- Validation ID.
- Job ID.
- Node ID where relevant.
- Validation stage.
- Issue codes.
- Severity.
- Evidence.
- Resolution.
- Provider/model where applicable.
- Timestamp.

## 21.6 Generated PDF

Store:

- Final PDF location.
- PDF hash.
- Page count.
- Font information.
- Rendering configuration.
- Round-trip result.
- Visual QA result.
- Release status.

Avoid storing unnecessary sensitive source content in external provider logs.

---

# 22. Job State Management

Extend job states to represent the new pipeline.

Suggested states:

```text
QUEUED
PREFLIGHT
OCR_EXTRACTION
NATIVE_EXTRACTION
SOURCE_RECONCILIATION
SOURCE_IR_BUILD
SOURCE_IR_VALIDATION
PROTECTED_SPAN_DETECTION
TRANSLATING
TRANSLATION_REVIEW
TRANSLATION_CORRECTION
FACT_VALIDATION
TARGET_IR_ALIGNMENT
TARGET_IR_VALIDATION
TEXT_SHAPING
LAYOUT_REFLOW
PDF_RENDERING
PDF_ROUNDTRIP_VALIDATION
VISUAL_QA
RELEASE_VALIDATION
COMPLETED
REVIEW_REQUIRED
FAILED
CANCELLED
```

Every transition must be recorded.

Do not allow a job to transition to `COMPLETED` if any mandatory gate remains unresolved.

---

# 23. API and Internal Interface Requirements

Expose consistent internal interfaces for the new validation stages.

Example:

```python
async def validate_source_ir(
    source_ir,
    extraction_results,
    document_profile
):
    ...
```

```python
async def translate_nodes(
    source_nodes,
    provider,
    translation_profile,
    protected_spans
):
    ...
```

```python
async def review_translation(
    source_nodes,
    translated_nodes,
    expected_facts,
    reviewer
):
    ...
```

```python
async def validate_alignment(
    source_ir,
    translated_ir,
    node_mappings
):
    ...
```

```python
async def validate_pdf_roundtrip(
    translated_ir,
    generated_pdf
):
    ...
```

```python
async def validate_visual_fidelity(
    source_pdf,
    translated_pdf,
    node_mappings
):
    ...
```

These are interface examples. Adapt signatures to the existing application architecture and asynchronous conventions.

## 23.1 Structured provider responses

All provider responses must be validated against application-owned schemas.

Handle:

- Invalid JSON.
- Missing required fields.
- Unknown node IDs.
- Duplicate node IDs.
- Unexpected extra content.
- Truncated responses.
- Provider errors.
- Timeouts.
- Rate limits.

Do not pass malformed model output directly into the rendering pipeline.

---

# 24. Observability and Cost Management

The new architecture adds external model calls, so provider usage must be measurable.

## 24.1 Metrics

Track:

### Extraction

- OCR pages processed.
- Native extraction pages processed.
- OCR/native agreement rate.
- Reconciliation conflict rate.
- Source IR validation failure rate.
- Paragraph reconstruction failure rate.

### Translation

- Nodes translated.
- Bodhan success rate.
- OpenRouter review success rate.
- Translation issue rate.
- Correction rate.
- Provider disagreement rate.
- Average translation latency.
- Average review latency.

### Technical fidelity

- Protected-span failure rate.
- Missing-node rate.
- Duplicate-node rate.
- Expected-facts mismatch rate.
- Source-target alignment failure rate.

### Rendering

- Unicode failure rate.
- Missing-glyph rate.
- Shaping failure rate.
- Overlap rate.
- Clipping rate.
- Round-trip mismatch rate.
- Visual QA failure rate.

### Cost

- Provider request count.
- Input/output tokens where available.
- Cost per document.
- Cost per page.
- Cost per translated node.
- Cost of retries.
- Cost of independent review.

## 24.2 Cost optimization

Use selective verification where appropriate.

Recommended policy:

- Independently review critical nodes.
- Review all nodes where required by the configured quality policy.
- Batch compatible nodes where provider limits permit.
- Retry only failed nodes.
- Cache reusable glossary and profile information where appropriate.
- Avoid translating protected spans.
- Avoid repeated full-document translation.
- Keep provider prompts versioned and compact.

Cost optimization must not disable mandatory quality gates.

---

# 25. Security and Reliability

## 25.1 Provider security

- Keep provider API keys in secure secret storage.
- Never expose keys in frontend code.
- Never write credentials into validation reports.
- Redact sensitive content from operational logs where required.
- Use HTTPS for provider communication.
- Apply request timeouts.
- Handle provider rate limits.
- Apply bounded retries.
- Record provider request IDs.

## 25.2 Document security

- Validate uploaded PDFs.
- Apply file-size and page-count limits.
- Isolate document processing.
- Sanitize temporary files.
- Use the existing sandboxing approach.
- Prevent unsafe PDF content from affecting other jobs.
- Clean temporary files according to retention policy.

## 25.3 External model output

Treat OCR and model output as untrusted data.

Do not allow document content or model-generated content to:

- Change system configuration.
- Execute commands.
- Modify provider credentials.
- Alter application instructions.
- Bypass validation.
- Change release policy.

---

# 26. Regression Test Requirements

Create a versioned, reusable regression test suite.

The test suite must cover the classes of failures this modification is intended to prevent.

## 26.1 Source extraction tests

Test:

- Digital PDF extraction.
- Scanned PDF OCR.
- Mixed-content pages.
- Multi-column reading order.
- Multi-line paragraphs.
- Repeated OCR/native regions.
- OCR/native conflicts.
- Missing text regions.
- Invalid Unicode.
- Page-boundary continuation.
- Overlapping text blocks.

## 26.2 Document IR tests

Test:

- Heading hierarchy.
- Paragraph reconstruction.
- Ordered lists.
- Nested bullets.
- Multi-line list items.
- Page-continuing lists.
- Code blocks.
- Configuration blocks.
- Tables.
- Headers and footers.
- Parent-child consistency.
- Stable node IDs.

## 26.3 Protected-span tests

Test:

- Shell commands.
- URLs.
- Emails.
- File paths.
- Filenames.
- Versions.
- Package names.
- Environment identifiers.
- Keyboard shortcuts.
- YAML.
- JSON.
- XML.
- Numbers and units.
- Inline code.
- Mathematical expressions.
- Placeholders.

## 26.4 Translation tests

Test:

- Duplicate phrases.
- Duplicate sentences.
- Missing sentences.
- Missing instructions.
- Unsupported additions.
- Awkward grammar.
- Incorrect meaning.
- Changed negation.
- Changed conditions.
- Incorrect entity-value relationships.
- Changed units.
- Inconsistent terminology.
- Fragmented sentence continuity.
- Incorrect punctuation.
- Unexpected symbols.
- Mixed-script corruption.

## 26.5 Alignment tests

Test:

- Missing target node.
- Duplicate target node.
- Wrong parent.
- Wrong reading order.
- Incorrect list membership.
- One-to-many mapping.
- Many-to-one mapping.
- Unmapped protected span.
- Unexpected translated node.

## 26.6 Typography tests

Test:

- Devanagari shaping.
- Combining marks.
- Conjuncts.
- Matras.
- Reph.
- Mixed English and Hindi.
- Font fallback.
- Missing glyph.
- Grapheme-safe wrapping.
- Line-height calculations.
- Shaped-glyph measurement.
- Embedded fonts.

Also include regression fixtures for any additional target scripts supported by the application.

## 26.7 PDF rendering tests

Test:

- Text overlap.
- Text clipping.
- Missing text.
- Duplicated text.
- Orphan headings.
- Broken lists.
- Broken code blocks.
- Unexpected page breaks.
- Large whitespace regions.
- Header/footer collision.
- Page count changes.
- Text outside page bounds.

## 26.8 Provider orchestration tests

Test:

- Bodhan success.
- Bodhan timeout.
- Bodhan invalid response.
- OpenRouter review success.
- OpenRouter timeout.
- OpenRouter invalid response.
- Targeted correction.
- Reviewer disagreement.
- Provider fallback.
- Retry exhaustion.
- Provider rate limiting.
- Cost and usage recording.

## 26.9 End-to-end tests

For each regression fixture:

1. Process the source PDF.
2. Run OCR and native extraction.
3. Build source IR.
4. Validate source IR.
5. Detect protected spans.
6. Translate.
7. Review translation.
8. Correct failed nodes where allowed.
9. Validate expected facts.
10. Validate source-target alignment.
11. Render target PDF.
12. Extract target PDF text.
13. Run round-trip validation.
14. Run visual QA.
15. Verify release decision.

The expected result must include issue codes and gate outcomes, not merely whether a PDF file exists.

---

# 27. Regression Fixture Format

Fixtures must be document-neutral and reusable.

Suggested structure:

```text
tests/
  fixtures/
    document_integrity/
      fixture_001/
        source.pdf
        expected_source_ir.json
        protected_spans.json
        expected_facts.json
        candidate_translation.json
        expected_issues.json
        expected_pdf_assertions.json
```

The fixture should contain:

- Original source PDF or source representation.
- Expected source IR.
- Expected node hierarchy.
- Expected reading order.
- Protected-span manifest.
- Expected facts where applicable.
- Candidate translation.
- Expected issue codes.
- Expected validation decisions.
- Final PDF assertions.

Do not hardcode language-specific phrases as universal failure rules.

Use semantic issue categories and evidence-based validation.

Fixtures must be version-controlled.

---

# 28. Acceptance Criteria

Modification V2 is complete only when the following requirements are satisfied.

## 28.1 Extraction and source IR

- OCR runs on every page.
- Native extraction runs on every page.
- Extraction reconciliation is implemented.
- Provenance is retained.
- Paragraphs are reconstructed logically.
- Heading hierarchy is preserved.
- Lists and numbering are preserved.
- Code/configuration blocks are identified.
- Source IR validation blocks critical failures.

## 28.2 Protected content

- Required protected-span categories are implemented.
- Span IDs remain stable.
- Commands and structured blocks are preserved.
- Protected spans are checked after translation.
- Protected spans are checked after rendering.

## 28.3 Translation

- Bodhan is supported as primary provider.
- OpenRouter is supported as an independent reviewer.
- OpenRouter can provide targeted alternative translations.
- Provider routing is configurable.
- Retries are bounded.
- Failed nodes are retried selectively.
- Translation findings are evidence-based.
- Reviewer disagreements are recorded.

## 28.4 Technical correctness

- Expected facts are extracted with source evidence.
- Values are checked.
- Units are checked.
- Entity-value relationships are checked.
- Conditions and constraints are checked.
- Instructions and their sequence are checked.

## 28.5 Document alignment

- Source node IDs are retained.
- Source-target mapping is explicit.
- Missing nodes are detected.
- Duplicate nodes are detected.
- Parent-child relationships are validated.
- Reading order is validated.

## 28.6 Typography and rendering

- Target-script font support is verified.
- Script shaping is implemented.
- Grapheme-safe wrapping is implemented.
- Shaped glyph runs are measured.
- Font embedding is validated.
- Layout reflow is supported.
- Critical clipping and overlap are detected.

## 28.7 PDF validation

- Final PDF text is extracted again.
- Extracted PDF text is compared with translated IR.
- Protected spans are checked.
- Missing and duplicate content is checked.
- Unicode is checked.
- Fonts are checked.
- Visual regression is performed.
- Critical failures block release.

## 28.8 Operational requirements

- Provider usage is recorded.
- Provider errors are handled.
- Job stages are observable.
- Retry counts are visible.
- Validation reports are generated.
- Configuration is centralized.
- Existing application workflows remain compatible.

---

# 29. Implementation Milestones

Implement the changes incrementally.

## Milestone 1 — Source extraction and IR

Deliver:

- PDF preflight.
- OCR/native extraction reconciliation.
- Provenance tracking.
- Paragraph reconstruction.
- Reading-order resolution.
- Heading and list hierarchy.
- Source IR validator.

Exit criteria:

All source extraction and source IR regression tests pass.

## Milestone 2 — Protected spans and translation profiles

Deliver:

- Protected-span detector.
- Immutable source spans.
- Translation profile manager.
- Glossary support.
- Technical terminology validation.

Exit criteria:

All protected-content tests pass.

## Milestone 3 — Translation orchestration

Deliver:

- Provider interface.
- Bodhan adapter.
- OpenRouter adapter.
- Independent reviewer.
- Targeted correction.
- Bounded retry manager.
- Provider routing configuration.

Exit criteria:

Provider orchestration tests pass and invalid provider output cannot bypass validation.

## Milestone 4 — Translation and expected-facts validation

Deliver:

- Completeness checks.
- Duplication checks.
- Semantic review.
- Technical facts.
- Source-target alignment.
- Translation quality report.

Exit criteria:

All translation, technical fidelity, and alignment tests pass.

## Milestone 5 — Indic typography and layout

Deliver:

- Font manager.
- Script shaping.
- Grapheme-safe wrapping.
- Shaped glyph measurement.
- Layout reflow.
- Page reconstruction improvements.

Exit criteria:

All supported-script typography tests pass.

## Milestone 6 — PDF round-trip and visual QA

Deliver:

- PDF text extraction after rendering.
- Round-trip validator.
- Font and Unicode checks.
- Bounding-box validation.
- Region-based visual comparison.
- Final release gate.

Exit criteria:

All rendering, round-trip, and visual regression tests pass.

## Milestone 7 — Production hardening

Deliver:

- Metrics.
- Structured logs.
- Cost tracking.
- Failure recovery.
- Security review.
- Configuration validation.
- Deployment integration.

Exit criteria:

Production workflows are observable, recoverable, and protected by release gates.

---

# 30. Backward Compatibility and Migration

Modification V2 must be integrated into the existing application without unnecessarily breaking working features.

Before modifying existing components:

1. Inspect the current application structure.
2. Identify the existing V1 implementations.
3. Identify existing data models and service interfaces.
4. Reuse working extraction and translation integrations.
5. Identify gaps against this specification.
6. Extend existing interfaces where possible.
7. Avoid creating duplicate provider clients.
8. Avoid introducing competing configuration systems.
9. Preserve existing job records where migration permits.
10. Add migration scripts for schema changes.

Where older jobs do not contain the new metadata:

- Mark unavailable provenance as unknown.
- Do not invent historical validation results.
- Do not retroactively claim that an older PDF passed new validation gates.

Use feature flags to introduce the new workflow gradually.

Suggested flags:

```yaml
features:
  source_ir_validation_v2: true
  protected_span_validation_v2: true
  openrouter_independent_review: true
  expected_facts_validation: true
  indic_shaping_v2: true
  pdf_roundtrip_validation: true
  visual_regression_v2: true
```

Use the application's existing feature-flag system if one already exists.

---

# 31. Final Engineering Instructions

The implementation team must follow these instructions while applying Modification V2.

1. Inspect the existing application before changing code.
2. Treat Modification V1 as the baseline.
3. Do not discard working V1 features.
4. Map every requirement in this document to an existing or new component.
5. Identify the exact files and services requiring modification.
6. Prefer incremental changes over a complete rewrite.
7. Keep provider integrations independent from document processing.
8. Keep source IR authoritative.
9. Do not let translation providers modify structural metadata.
10. Do not let an LLM bypass deterministic validation.
11. Do not automatically accept unresolved provider disagreements.
12. Do not retry an entire document for a single-node failure.
13. Do not treat PDF generation success as translation success.
14. Do not force the translated PDF to retain the source page count.
15. Do not use simplistic Unicode character-range checks for glyph support.
16. Do not use raw pixel similarity as the sole visual-quality metric.
17. Do not remove non-text page elements when cleaning scanned PDFs.
18. Do not release a document with unresolved critical validation failures.
19. Add tests for every newly introduced issue code.
20. Record all provider, model, profile, and validation decisions.

For every implemented requirement, provide:

- Implementation location.
- Files changed.
- Interface or schema changes.
- Configuration changes.
- Tests added.
- Test results.
- Known limitations.

---

# 32. Expected Final Outcome

After implementing Modification V2, Translation Studio should operate as a validated document transformation system rather than a simple OCR-and-translation utility.

The application should be able to:

- Recover document content and structure reliably.
- Identify ambiguous extraction regions.
- Protect technical and structured content.
- Translate only eligible content.
- Use Bodhan as the primary translation provider.
- Use OpenRouter for independent verification and targeted corrections.
- Validate semantic completeness and technical correctness.
- Maintain source-target node alignment.
- Render Indic scripts correctly.
- Reflow pages naturally.
- Verify the generated PDF independently.
- Detect visual defects.
- Produce an auditable quality report.
- Block release when mandatory quality requirements are not satisfied.

The final release decision must be based on the combined results of source extraction, semantic translation, technical validation, structural alignment, typography, PDF round-trip, and visual QA.

**The governing principle of Modification V2 is that every translated PDF must be demonstrably faithful to its source, structurally valid, technically correct, readable in its target language, and visually coherent before it is delivered.**