# HS10 Data Center Relevance Classifier (v2 — NAICS-Enhanced)

## Documentation for LLM-Based Commodity Classification System

This document describes the methodology, technology stack, and operational considerations for classifying HS10 commodity codes by their relevance to AI data center construction and operations. **Version 2** of the classifier augments each HS10 description with the associated NAICS (North American Industry Classification System) code and industry description, providing the LLM with richer context for edge-case disambiguation.

---

## Table of Contents

1. [Methodology](#1-methodology)
2. [Technology Stack](#2-technology-stack)
3. [Cost and Time Estimates](#3-cost-and-time-estimates)
4. [Caveats and Limitations](#4-caveats-and-limitations)
5. [Future Refinements](#5-future-refinements)

---

## 1. Methodology

### 1.1 Overview

The classifier uses Claude AI (Anthropic) to evaluate each HS10 commodity code and determine its relevance to hyperscale AI data center construction and operations. The system uses **structured tool calling** to enforce consistent, validated output, and enriches each classification request with **NAICS industry context** to improve accuracy on ambiguous products.

The key motivation for NAICS enrichment: many HS10 descriptions are ambiguous in isolation. For example, "diesel engines exceeding 373 kW" could be for backup generators (highly relevant) or marine/industrial propulsion (not relevant). The NAICS code indicating the *producing* industry — e.g., "Engine Equipment Manufacturing" vs. "Ship and Boat Building" — resolves such ambiguity without requiring the LLM to guess.

### 1.2 Inputs to the LLM

Each classification request provides two pieces of structured information:

1. **HS10 Code and Description** — The 10-digit Harmonized System code used by U.S. Customs, with the long-form Census commodity description (e.g., `8542310040: PROCESSORS (INCLUDING MICROPROCESSORS): GRAPHICS PROCESSING UNITS (GPUS)`).

2. **NAICS Code and Description** — The North American Industry Classification System code(s) and description(s) associated with the HS10 code via the Census Bureau HS10-to-NAICS concordance. Where multiple NAICS codes map to a single HS10, all are provided. This production-oriented classification adds context about how the product is typically manufactured and used.

### 1.3 Classification Schema

Each HS10 code is classified along the following dimensions:

| Field | Type | Description |
|-------|------|-------------|
| `relevance` | Enum: High, Medium, Low | Direct relevance to data center construction/operation |
| `confidence` | Integer (0–100) | Model's confidence in the assessment |
| `primary_category` | Enum (9 options) | Functional category for the product |
| `specific_use` | String | Specific application (e.g., "GPU accelerators", "cooling tower pumps") |
| `reasoning` | String | Brief explanation of the classification decision |

Output also retains the input fields for traceability:

| Field | Description |
|-------|-------------|
| `hs10_code` | The 10-digit HS code |
| `description` | The HS commodity description |
| `naics_code` | The associated NAICS code(s) |
| `naics_description` | The NAICS industry description(s) |

### 1.4 Primary Categories

Products are assigned to one of nine categories:

1. **Compute_Hardware** — GPUs, CPUs, memory, PCBs, servers, storage drives, semiconductors
2. **Networking_Telecom** — Fiber optics, switches, routers, transceivers, cables
3. **Cooling_HVAC** — Chillers, cooling towers, CRAH units, fans, pumps, refrigerants, glycol
4. **Electrical_Power** — Transformers, switchgear, UPS, batteries, generators, busbars
5. **Building_Structure** — Structural steel, concrete, rebar, insulation, raised floors
6. **Fire_Safety_Security** — Fire suppression, detection systems, security equipment
7. **Specialty_Materials** — Rare earths, copper, aluminum, tantalum, thermal interface materials
8. **Maintenance_Operations** — Maintenance supplies, lubricants, operational consumables
9. **Not_DC_Related** — Products not relevant to data center construction/operation

### 1.5 Relevance Definitions

- **High**: Directly used in data center construction or operation (e.g., GPUs, servers, cooling systems, backup generators)
- **Medium**: Sometimes used in data centers or serves as an indirect input (e.g., general-purpose copper wire, electric motors)
- **Low**: Not relevant to data center applications (e.g., food, textiles, consumer goods)

In the paper, the baseline analysis focuses on **High** relevance products. **Medium** products are used for robustness checks only.

### 1.6 System Prompt Design

The system prompt establishes the LLM as an expert in AI data center construction and operations, then:

1. Explains both input types (HS10 and NAICS) and how to use them together
2. Lists six explicit product categories with canonical examples
3. Provides edge-case guidance — e.g., using the NAICS description to distinguish diesel engines for generators vs. vehicles, or pumps for cooling vs. unrelated industrial use

The full prompt is reproduced in the paper appendix.

### 1.7 Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  Input: data-input/unique_hs10_naics_descriptions.csv           │
│  (HS10 code + long description + NAICS code + NAICS description) │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  For each (hs10, description, naics, naics_description):        │
│    1. Build user message with HS10 + NAICS context              │
│    2. Send to Claude API with forced tool call                  │
│    3. Extract structured JSON response                          │
│    4. Append to results (hs10, desc, naics, naics_desc +        │
│       relevance, confidence, category, specific_use, reasoning) │
│    5. Checkpoint every 10 items                                 │
│    6. Rate limit (0.5s delay)                                   │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Output: data-input/hs10_classification_final_v3.csv            │
│  (19,425 rows — all non-petroleum, non-precious-metal HS10s)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

### 2.1 Core Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **LLM** | `claude-sonnet-4-20250514` (Anthropic) | Classification intelligence |
| **API Client** | `anthropic` Python SDK | Structured tool-calling API |
| **Data Processing** | `pandas` | CSV I/O and data manipulation |
| **Environment** | Python 3.10+ | Runtime |
| **Notebook Interface** | Jupyter (VS Code) | Interactive development |

### 2.2 Key Python Dependencies

```
anthropic>=0.40.0
pandas>=2.0.0
python-dotenv  # optional, for .env support
```

### 2.3 API Configuration

| Parameter | Value |
|-----------|-------|
| Model | `claude-sonnet-4-20250514` |
| Max tokens | 400 per request |
| Tool choice | Forced: `{"type": "tool", "name": "classify_hs10_code"}` |
| Temperature | Default (not set — classification task) |
| Rate limiting | 0.5 seconds between requests |

### 2.4 File Structure

```
ai-trade-index/
├── code/
│   ├── hs10_llm_classifier_naics.py      # Main classifier module (v2, NAICS-enhanced)
│   ├── hs10_llm_classifier_demo.py       # Original classifier module (v1, no NAICS)
│   ├── 04-classify-imports.ipynb         # Production notebook — imports classification
│   └── 05-classify-exports.ipynb         # Production notebook — exports classification
├── data-input/
│   ├── unique_hs10_naics_descriptions.csv  # Input: HS10 codes + NAICS mappings (~18,701 rows)
│   ├── unique_hs10_commodities.csv         # Input: HS10 codes + long descriptions (~19,425 rows)
│   ├── unique_hs10_export_commodities.csv  # Input: export HS10 codes (~4,694 rows)
│   ├── hs10_classification_final_v3.csv    # Output: classified imports (19,425 rows, v3 current)
│   ├── hs10_classification_exports_final.csv # Output: classified exports (4,694 rows)
│   └── hs10_classification_imports_exports.csv # Output: combined (24,118 rows)
└── archive/
    ├── hs10_classification_final.csv       # v1 output (no NAICS)
    └── hs10_classification_final_v2.csv    # v2 output
```

### 2.5 Key Functions in `hs10_llm_classifier_naics.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `classify_single_code` | `(hs10_code, description, naics_code=None, naics_description=None)` | Classify one HS10 code via API, NAICS context optional |
| `classify_batch` | `(codes_df, delay, checkpoint_file, hs_col, desc_col, naics_col, naics_desc_col)` | Batch process with checkpointing |
| `resume_batch_classification` | `(all_codes_file, checkpoint_file, ..., output_file, delay)` | Resume from checkpoint, auto-retry errors |

The v2 classifier is backward-compatible: NAICS arguments are optional in `classify_single_code`. When omitted, the prompt contains only the HS10 description (same behavior as v1).

### 2.6 Error Handling & Resilience

- **Checkpointing**: Progress saved every 10 items
- **Resume capability**: Automatically skips successfully-classified codes on restart
- **Error retry**: Codes with `relevance='Error'` are retried on resume
- **Graceful degradation**: API errors logged with details in output

---

## 3. Cost and Time Estimates

### 3.1 Dataset Size

- **Imports**: ~19,425 unique HS10 codes (after excluding petroleum, precious metals, HS2 ch. 98–99)
- **Exports**: ~4,694 unique HS10 codes

### 3.2 Token Counts (v2 with NAICS context)

NAICS descriptions add approximately 50–100 tokens per request compared to v1.

| Metric | v1 (no NAICS) | v2 (with NAICS) |
|--------|--------------|-----------------|
| Input tokens per code | ~250 | ~350 |
| Output tokens per code | ~125 | ~125 |
| Total input tokens (19k codes) | ~4.9M | ~6.8M |
| Total output tokens | ~2.4M | ~2.4M |

### 3.3 Cost Breakdown (`claude-sonnet-4-20250514`)

| Item | Estimate |
|------|----------|
| Input cost ($3/M tokens) | ~$20 |
| Output cost ($15/M tokens) | ~$36 |
| **Total API cost** | **~$50–70** |

> Actual cost for the v3 classification run was approximately **$150**, reflecting longer descriptions and multiple retry passes.

### 3.4 Time Estimates

| Configuration | Time |
|--------------|------|
| Rate limit delay | 0.5 s/request |
| API response time | ~0.5–1.0 s/request |
| **Time per code** | ~1–1.5 s |
| **Total (19,425 codes)** | **~6–8 hours** |

---

## 4. Caveats and Limitations

### 4.1 Classification Accuracy

- **NAICS helps but is not definitive**: NAICS codes reflect the *producing* industry, not necessarily the end use
- **Edge cases remain**: Products like general-purpose transformers are used in data centers and elsewhere; the model must judge by description quality
- **No ground truth validation**: Results have not been benchmarked against a labeled expert dataset

### 4.2 Data Limitations

- **NAICS concordance coverage**: Not all HS10 codes have a NAICS mapping; ~700 codes in the full dataset lack NAICS context and are classified on HS description alone
- **Multiple NAICS per HS10**: Where multiple NAICS codes map to one HS10, all are provided; the model must synthesize across them
- **Description quality**: Short or abbreviated HS descriptions reduce classification confidence

### 4.3 Technical Limitations

- **Sequential processing**: Current implementation is single-threaded; parallelism could reduce runtime but requires careful rate-limit management
- **API availability**: Interruptions require resume from checkpoint
- **Model version lock**: Classifications from `claude-sonnet-4-20250514` may differ from future model versions

### 4.4 Reproducibility

- **Checkpoint files are archived** in `archive/` for the v3 run
- **Temperature not set**: LLM outputs may vary slightly between runs (tool-calling reduces but does not eliminate variance)
- The paper uses `hs10_classification_final_v3.csv` as the canonical classification

---

## 5. Future Refinements

### 5.1 Validation & Quality Assurance

- [ ] **Expert review**: Sample 100–200 codes for manual validation
- [ ] **Confusion analysis**: Identify systematic misclassification by HS2 chapter
- [ ] **Confidence calibration**: Verify confidence scores correlate with accuracy

### 5.2 Methodology Improvements

- [ ] **Few-shot examples**: Add 3–5 curated examples to the system prompt
- [ ] **Multi-model ensemble**: Compare across Claude, GPT-4, and Gemini
- [ ] **Hierarchical classification**: First classify by category, then by relevance level
- [ ] **Long-description enrichment**: Use Census long-form descriptions (already used in v3)

### 5.3 Performance Optimization

- [ ] **Batch API**: Use Anthropic's batch processing API for ~50% cost reduction
- [ ] **Async processing**: Parallel API calls with proper rate limiting
- [ ] **Incremental updates**: Only reclassify codes with changed descriptions when HS schedule updates

---

## Appendix: Quick Start

### Running the Import Classifier

```python
import os
os.environ['ANTHROPIC_API_KEY'] = 'your-api-key'

from hs10_llm_classifier_naics import resume_batch_classification

results = resume_batch_classification(
    all_codes_file='data-input/unique_hs10_naics_descriptions.csv',
    checkpoint_file='data-input/hs10_classification_progress_v3.csv',
    hs_col='HS10',
    desc_col='long_desc',
    naics_col='naics',
    naics_desc_col='naics_descriptions',
    output_file='data-input/hs10_classification_final_v3.csv',
    delay=0.5
)
```

### Testing a Single Code

```python
from hs10_llm_classifier_naics import classify_single_code

result = classify_single_code(
    hs10_code="8542310040",
    description="PROCESSORS (INCLUDING MICROPROCESSORS): GRAPHICS PROCESSING UNITS (GPUS)",
    naics_code="334413",
    naics_description="SEMICONDUCTOR AND RELATED DEVICE MANUFACTURING"
)
print(result)
# {'relevance': 'High', 'confidence': 99, 'primary_category': 'Compute_Hardware',
#  'specific_use': 'GPU accelerators for AI training and inference',
#  'reasoning': 'GPUs are the core compute component of AI data centers...', ...}
```

### Testing Without NAICS (v1-compatible mode)

```python
result = classify_single_code(
    hs10_code="8542310040",
    description="PROCESSORS (INCLUDING MICROPROCESSORS): GRAPHICS PROCESSING UNITS (GPUS)"
)
```

---

*Last updated: March 2026*
