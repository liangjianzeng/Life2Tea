# RFC 002: MoE Dual-Mapping Design

**Status:** Draft  
**Author:** liangjianzeng  
**Date:** 2026-06-24  
**Version:** 0.1.0  

---

## 1. Motivation

### 1.1 Problem Statement

Local LLM deployment faces a **resource constraint problem**:

- **Large models** (e.g., Qwen3.6-35B) provide high-quality responses but require significant GPU memory (21GB+)
- **Small models** (e.g., VibeThinker-3B) are fast and lightweight but have limited capabilities
- **Specialized models** (e.g., Qwen3VL-8B for vision, GLM-OCR for OCR) excel at specific tasks but are wasteful for general chat

**Key insight:** Different tasks require different models. A **Mixture-of-Experts (MoE)** approach at the **system level** can dynamically route requests to the most suitable model, optimizing for both quality and resource usage.

### 1.2 Why Dual-Mapping?

There are **two levels of MoE** in modern LLM systems:

| Level | Description | Example |
|-------|-------------|---------|
| **Intra-Model MoE** | Multiple "expert" layers inside a single model | Mixtral 8x7B (8 experts per layer, activate 2 per token) |
| **Inter-Model MoE** | Multiple model instances, router dispatches requests | Route math questions to Qwen3-Coder, vision to Qwen3VL |

**Life2Tea's innovation:** Unify these two levels into a **dual-mapping architecture**, where:
- The **system router** is aware of **intra-model MoE** characteristics
- Routing decisions consider both **task suitability** and **resource availability**

---

## 2. Intra-Model MoE (Model-Level)

### 2.1 How It Works

Intra-Model MoE is a **model architecture** where:
- Each transformer layer has **N expert sub-layers** (e.g., 8 in Mixtral)
- A **gating network** selects **top-K experts** (e.g., 2) per token
- Only selected experts are activated → **computational savings**

```
Input Token
    ↓
Gating Network (learned during training)
    ↓
Select Top-2 Experts
    ↓
Expert 1 (feed-forward)  Expert 2 (feed-forward)
    ↓
Combine outputs
    ↓
Next Layer
```

### 2.2 Implications for Life2Tea

**What we can't control:**  
Intra-model MoE is fixed after training. We cannot change which experts are activated.

**What we can leverage:**  
1. **Expert specialization**: Different experts may specialize in different tasks (though this is not guaranteed)
2. **Resource efficiency**: MoE models activate only a subset of parameters → **faster inference** than dense models of equivalent quality

**Example:**  
Mixtral 8x7B has 47B total parameters but activates only 13B per token → **2.5x faster** than a dense 47B model.

---

## 3. Inter-Model MoE (System-Level)

### 3.1 Architecture

```
User Request
    ↓
┌─────────────────────────────────────┐
│   Intent Classifier (Router)        │
│   - Task type (chat, code, vision) │
│   - Complexity (simple, complex)    │
│   - Language (EN, ZH, code)       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│   Resource-Aware Selector           │
│   - GPU memory availability         │
│   - Model load status               │
│   - Inference queue length          │
└─────────────────────────────────────┘
    ↓
Selected Model Plugin
    ↓
Inference (possibly with Intra-Model MoE)
    ↓
Response
```

### 3.2 Routing Strategies

#### Strategy 1: Rule-Based Routing (Phase 1)

```python
ROUTING_RULES = {
    "code": ["qwen3coder", "lfm2"],
    "vision": ["qwen3vl_8b"],
    "ocr": ["glm_ocr"],
    "chat": ["lfm2", "qwen3.6"],
    "fast": ["vibethinker_3b", "gemma4"],
}
```

**Pros:** Simple, interpretable, fast  
**Cons:** Requires manual tuning, doesn't adapt to resource changes

#### Strategy 2: Learned Router (Phase 2)

Train a **small router model** (e.g., 1B parameters) that:
- Takes request features (task type, language, estimated complexity)
- Predicts which model will give the **best quality/cost trade-off**

**Training data:**  
Collect logs from Rule-Based Routing, then use **quality scores** (human feedback or LLM-as-judge) as labels.

#### Strategy 3: Hybrid (Phase 3)

Combine Rule-Based (for clear-cut cases) + Learned Router (for ambiguous cases).

---

## 4. Dual-Mapping: Connecting the Two Levels

### 4.1 Hierarchical Routing

```
Level 0: System Router (Inter-Model)
    ↓
Level 1: Model Plugin (Intra-Model MoE)
    ↓
Level 2: Expert Selection (inside model)
    ↓
Inference
```

**Example flow:**

1. User asks: "Write a Python function to sort a list"
2. System Router: Task = "code" → Route to `qwen3coder` (which is an MoE model)
3. `qwen3coder` internally: Gating network selects top-2 experts per token
4. Inference completes

### 4.2 Resource-Aware Routing with Intra-Model MoE

**Challenge:**  
MoE models have **lower memory footprint during inference** (only activate subset of parameters), but **higher memory requirement for loading** (all experts must be in GPU memory).

**Solution:**  
When selecting models, consider:
- **Loading memory**: Full model size (all experts)
- **Inference memory**: Active parameters only (can be lower if using techniques like **expert offloading**)

**Example:**  
Mixtral 8x7B:
- Loading memory: ~47GB (all experts)
- Inference memory: ~13GB active + KV cache

If GPU has 24GB, we can load Mixtral but cannot run it simultaneously with another 13GB model.

### 4.3 Feedback Loop

```
User Request → System Router → Model Plugin → Response
                                  ↓
                          Quality Score (human or LLM-as-judge)
                                  ↓
                          Update Router Policy
```

**Key idea:**  
If a model's **intra-model MoE** has experts that specialize in certain tasks, the **system router** should learn to prefer that model for those tasks.

---

## 5. Implementation Plan

### Phase 1: Rule-Based Router (Week 1-2)

**Deliverables:**
- [ ] Implement `SystemRouter` class (in `backend/app/core/router.py`)
- [ ] Define routing rules (JSON config)
- [ ] Add `/api/router/rules` endpoint (CRUD for routing rules)
- [ ] Integrate with `ChatHandler` (use router to select model)

**Files to create/modify:**
- `backend/app/core/router.py` (new)
- `backend/app/routers/router_router.py` (new)
- `backend/app/experts/chat_handler.py` (modify to use router)

### Phase 2: Resource-Aware Routing (Week 3-4)

**Deliverables:**
- [ ] Implement `ResourceMonitor` (in `backend/app/core/resource.py`)
- [ ] Add GPU memory monitoring (via `nvidia-smi` or `pynvml`)
- [ ] Modify router to consider resource availability
- [ ] Add **preemptive scheduling** (unload low-priority model if high-priority request comes in)

**Files to create/modify:**
- `backend/app/core/resource.py` (new)
- `backend/app/plugins/lifecycle.py` (modify to track resource usage)

### Phase 3: Learned Router (Week 5-8)

**Deliverables:**
- [ ] Collect training data (from Phase 1 & 2 logs)
- [ ] Train router model (small Transformer or MLP)
- [ ] Implement online learning (update router based on feedback)
- [ ] A/B test against rule-based router

**Files to create/modify:**
- `backend/app/core/learned_router.py` (new)
- `backend/app/core/feedback.py` (new, for collecting quality scores)

---

## 6. API Changes

### 6.1 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/router/rules` | GET/POST | Get/update routing rules |
| `/api/router/predict` | POST | Predict which model for a request |
| `/api/router/feedback` | POST | Submit quality feedback |
| `/api/resource/status` | GET | Get current resource usage |

### 6.2 Modified Endpoints

`POST /api/chat/completions`:
- Add optional `model_preference` field (hint to router)
- Add `X-Selected-Model` header (so client knows which model was used)

---

## 7. Configuration Example

```json
{
  "router": {
    "strategy": "rule-based",
    "rules": {
      "code": ["qwen3coder", "lfm2"],
      "vision": ["qwen3vl_8b"],
      "ocr": ["glm_ocr"],
      "default": ["lfm2"]
    },
    "resource_aware": true,
    "max_gpu_memory": 22900,
    "preempt_low_priority": true
  }
}
```

---

## 8. Open Questions

1. **How to measure "quality" for learned router?**  
   Options: Human feedback, LLM-as-judge, task-specific metrics (e.g., code execution success rate for coding tasks)

2. **Should router be a separate plugin?**  
   Pros: Modular, can swap routers  
   Cons: Added latency (router inference time)

3. **How to handle multi-turn conversations?**  
   Should router re-evaluate every turn, or stay with the same model for the whole conversation?

4. **How to handle model failures?**  
   If selected model crashes, should router retry with next-best model?

---

## 9. References

- [Mixtral of Experts paper](https://arxiv.org/abs/2401.04088)
- [OLMoE: Open Mixture-of-Experts Language Models](https://arxiv.org/abs/2409.03447)
- [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665)

---

**Previous RFC:** [RFC 001: PIP Protocol](./001-pip-protocol.md)  
**Next RFC:** [RFC 003: Plugin Marketplace Design](./003-plugin-marketplace.md) (TBD)
