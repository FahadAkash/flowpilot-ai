"""Provider adapters for OpenAI, Gemini, Anthropic, Ollama, and deterministic Mock."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from flowpilot.config import get_settings
from flowpilot.documents.chunker import estimate_tokens


@dataclass(slots=True)
class ProviderResponse:
    content: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_confidence: float = 0.90
    simulated_latency_ms: float | None = None


class BaseLLMProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    async def generate(
        self,
        *,
        model_key: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        context_payload: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Invoke the backing model and return content, tokens, and confidence."""


def _extract_json_dict(content: str) -> dict[str, Any]:
    """Extract a JSON object from raw model text, handling markdown fences or surrounding prose."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    with contextlib.suppress(Exception):
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        with contextlib.suppress(Exception):
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
    return {"text": content}


class OpenAICompatibleProvider(BaseLLMProvider):
    """Works with OpenAI API, local LM Studio, and local Ollama OpenAI-compatible endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        provider_name: str = "openai",
        timeout_seconds: float = 45.0,
        supports_json_mode: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"
        self.api_key = api_key
        self.provider_name = provider_name
        self.timeout_seconds = timeout_seconds
        self.supports_json_mode = supports_json_mode

    async def generate(
        self,
        *,
        model_key: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        context_payload: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        max_tokens = (
            120
            if task_kind in {"classify_intent", "classify_document", "plan"}
            else (180 if tier <= 2 else (280 if task_kind == "frontier_reasoning" else 360))
        )

        sys_text = system_prompt
        if not self.supports_json_mode and task_kind in {
            "classify_intent",
            "classify_document",
            "extract_structured",
            "plan",
            "compare_documents",
            "frontier_reasoning",
        }:
            sys_text = (
                f"{system_prompt} Respond ONLY with a compact, valid JSON object. "
                "Do not output chain-of-thought or markdown prose outside the JSON."
            )

        payload: dict[str, Any] = {
            "model": model_key,
            "temperature": 0.0 if tier <= 2 else 0.1,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.supports_json_mode and task_kind in {
            "classify_intent",
            "classify_document",
            "extract_structured",
            "plan",
        }:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        msg = data["choices"][0]["message"]
        content = str(msg.get("content") or msg.get("reasoning_content") or "").strip()
        usage = data.get("usage", {})
        structured = _extract_json_dict(content)

        raw_conf = float(structured.get("confidence", 0.90 if tier == 3 else 0.86))
        return ProviderResponse(
            content=content,
            structured_data=structured,
            prompt_tokens=int(usage.get("prompt_tokens", estimate_tokens(sys_text + user_prompt))),
            completion_tokens=int(usage.get("completion_tokens", estimate_tokens(content))),
            raw_confidence=max(0.0, min(1.0, raw_conf)),
        )


class GeminiProvider(BaseLLMProvider):
    """Direct Google Gemini REST adapter."""

    provider_name = "gemini"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def generate(
        self,
        *,
        model_key: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        context_payload: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_key}:generateContent?key={self.api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0 if tier <= 2 else 0.1},
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        structured: dict[str, Any] = {}
        try:
            cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip())
            structured = json.loads(cleaned)
        except Exception:
            structured = {"text": content}
        raw_conf = float(structured.get("confidence", 0.89 if tier == 3 else 0.85))
        return ProviderResponse(
            content=content,
            structured_data=structured,
            prompt_tokens=int(
                usage.get("promptTokenCount", estimate_tokens(system_prompt + user_prompt))
            ),
            completion_tokens=int(usage.get("candidatesTokenCount", estimate_tokens(content))),
            raw_confidence=max(0.0, min(1.0, raw_conf)),
        )


class AnthropicProvider(BaseLLMProvider):
    """Direct Anthropic Messages REST adapter."""

    provider_name = "anthropic"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def generate(
        self,
        *,
        model_key: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        context_payload: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model_key,
            "max_tokens": 1400,
            "temperature": 0.0 if tier <= 2 else 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        structured: dict[str, Any] = {}
        try:
            cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip())
            structured = json.loads(cleaned)
        except Exception:
            structured = {"text": content}
        raw_conf = float(structured.get("confidence", 0.90 if tier == 3 else 0.85))
        return ProviderResponse(
            content=content,
            structured_data=structured,
            prompt_tokens=int(
                usage.get("input_tokens", estimate_tokens(system_prompt + user_prompt))
            ),
            completion_tokens=int(usage.get("output_tokens", estimate_tokens(content))),
            raw_confidence=max(0.0, min(1.0, raw_conf)),
        )


class DeterministicMockProvider(BaseLLMProvider):
    """Content-aware deterministic provider for reproducible offline dev, tests, and benchmarks.

    Models realistic prompt/completion token counts, tier latency profiles, and
    calibrated confidence differences across Tier 1, Tier 2, and Tier 3.
    """

    provider_name = "mock"

    async def generate(
        self,
        *,
        model_key: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        context_payload: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        ctx = context_payload or {}
        # Brief async yield so concurrency/cancellation tests behave realistically
        await asyncio.sleep(0.002 if tier == 1 else (0.004 if tier == 2 else 0.008))

        prompt_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
        structured: dict[str, Any]
        raw_conf = 0.88

        if task_kind == "classify_intent":
            query_low = str(ctx.get("query", user_prompt)).lower()
            doc_count = int(ctx.get("doc_count", 1))
            if any(
                k in query_low
                for k in (
                    "indemn",
                    "conflict",
                    "ambiguous",
                    "governing law",
                    "liability cap",
                    "legal",
                )
            ):
                intent = "legal_reasoning"
                rec_tier = 2
                raw_conf = 0.87
            elif doc_count >= 2 or any(
                k in query_low
                for k in ("compare", "discrepanc", "policy", "follows", "match", "audit")
            ):
                intent = "multi_doc_comparison"
                rec_tier = 2
                raw_conf = 0.91
            elif any(
                k in query_low
                for k in (
                    "classify",
                    "type of document",
                    "extract",
                    "vendor",
                    "line items",
                    "summarize",
                )
            ):
                intent = "document_extraction"
                rec_tier = 1
                raw_conf = 0.90
            else:
                intent = "simple_qa"
                rec_tier = 1
                raw_conf = 0.85
            structured = {
                "intent": intent,
                "recommended_tier": rec_tier,
                "rationale": f"Classified as '{intent}' based on query semantics and {doc_count} document(s).",
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            completion_tokens = max(48, estimate_tokens(content))
            sim_latency = 42.0

        elif task_kind == "classify_document":
            text = str(ctx.get("text", user_prompt)).lower()
            filename = str(ctx.get("filename", "")).lower()
            doc_type = _classify_doc_from_text(filename, text)
            raw_conf = 0.94 if doc_type != "general_document" else 0.72
            structured = {
                "doc_type": doc_type,
                "summary": _summarize_document_text(str(ctx.get("text", user_prompt))),
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            completion_tokens = max(65, estimate_tokens(content))
            sim_latency = 58.0

        elif task_kind == "plan":
            intent = str(ctx.get("intent", "multi_doc_comparison"))
            steps = ["retrieval", "extraction", "validation"]
            if intent in {"multi_doc_comparison", "legal_reasoning"}:
                steps = ["retrieval", "extraction", "comparison", "validation"]
            structured = {
                "steps": steps,
                "objective": f"Execute minimal specialist plan for intent={intent}.",
                "confidence": 0.92,
            }
            content = json.dumps(structured)
            completion_tokens = max(72, estimate_tokens(content))
            sim_latency = 65.0

        elif task_kind == "extract_structured":
            # Deterministic regex+heuristic extraction simulating structured JSON LLM output
            extracted = ctx.get("pre_extracted") or {}
            completeness = float(ctx.get("completeness_score", 0.90))
            raw_conf = round(min(0.96, max(0.68, completeness)), 3)
            structured = {
                "extracted": extracted,
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            completion_tokens = max(90, estimate_tokens(content))
            sim_latency = 65.0 if tier == 1 else 78.0

        elif task_kind == "compare_documents":
            discrepancies = ctx.get("detected_discrepancies") or []
            has_ambiguous = any(d.get("requires_frontier_reasoning") for d in discrepancies)
            raw_conf = 0.69 if has_ambiguous else 0.91
            structured = {
                "discrepancies": discrepancies,
                "requires_escalation": has_ambiguous,
                "summary": (
                    f"Identified {len(discrepancies)} potential discrepancy/concern item(s) across documents."
                    if discrepancies
                    else "No discrepancies or policy concerns identified across the evaluated documents."
                ),
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            completion_tokens = max(110, estimate_tokens(content))
            sim_latency = 85.0

        elif task_kind == "frontier_reasoning":
            discrepancies = ctx.get("discrepancies") or []
            query = str(ctx.get("query", ""))
            resolutions = []
            for d in discrepancies:
                resolutions.append(
                    {
                        "code": d.get("code", "CONFLICT"),
                        "analysis": (
                            f"Contextual synthesis for {d.get('field', 'clause')}: "
                            f"Expected ({d.get('expected')}) conflicts with actual ({d.get('actual')}). "
                            f"Evidence: {d.get('citation')}. Recommend legal/procurement review before approval."
                        ),
                        "recommended_action": "Flag for human sign-off / contract amendment before payment or execution.",
                    }
                )
            if not resolutions:
                resolutions.append(
                    {
                        "code": "CONTEXTUAL_SYNTHESIS",
                        "analysis": f"Completed deep contextual verification for query: '{query}'.",
                        "recommended_action": "Proceed with standard documented workflow.",
                    }
                )
            raw_conf = 0.95
            structured = {
                "resolutions": resolutions,
                "executive_reasoning": (
                    f"Tier 3 Frontier Analysis resolved {len(resolutions)} complex/ambiguous item(s) "
                    "with cross-document precedence and risk qualification."
                ),
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            completion_tokens = max(210, estimate_tokens(content))
            sim_latency = 260.0

        elif task_kind == "monolithic_baseline":
            # Baseline A sends full document context directly to Tier 3 frontier model
            answer_data = ctx.get("baseline_answer") or {}
            raw_conf = float(ctx.get("baseline_confidence", 0.94))
            structured = {
                "answer": answer_data,
                "confidence": raw_conf,
            }
            content = json.dumps(structured)
            # Monolithic frontier prompts include verbose system instructions + full docs + long CoT output
            prompt_tokens = max(prompt_tokens + 450, 1400)
            completion_tokens = max(480, estimate_tokens(content) + 280)
            sim_latency = 680.0

        else:
            text = str(ctx.get("text", user_prompt))
            summary = _summarize_document_text(text)
            raw_conf = 0.87
            structured = {"answer": summary, "confidence": raw_conf}
            content = json.dumps(structured)
            completion_tokens = max(110, estimate_tokens(content))
            sim_latency = 85.0

        return ProviderResponse(
            content=content,
            structured_data=structured,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_confidence=raw_conf,
            simulated_latency_ms=sim_latency,
        )


def _classify_doc_from_text(filename: str, text: str) -> str:
    hay = f"{filename}\n{text[:3000]}"
    checks = [
        ("invoice", ("invoice number", "inv-", "bill to", "amount due", "tax invoice")),
        ("purchase_order", ("purchase order", "po-", "authorized buyer", "ship to")),
        ("policy", ("company policy", "procurement policy", "approval threshold", "policy")),
        ("contract", ("agreement", "indemnif", "governing law", "liability cap", "termination")),
        (
            "financial_report",
            ("ebitda", "revenue", "operating margin", "fiscal quarter", "net income"),
        ),
        ("healthcare_report", ("patient", "diagnosis", "discharge", "clinical", "medication")),
    ]
    best = "general_document"
    best_hits = 0
    for label, kws in checks:
        hits = sum(1 for k in kws if k in hay)
        if hits > best_hits:
            best_hits = hits
            best = label
    return best


def _summarize_document_text(text: str) -> str:
    lines = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("[Page")
    ]
    if not lines:
        return "Document contains no extractable text."
    return " ".join(lines[:5])[:420]


def resolve_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """Resolve configured provider, automatically falling back to Mock if live key is missing."""
    settings = get_settings()
    chosen = (provider_name or settings.llm_provider).lower()
    if chosen == "lmstudio" and settings.lm_studio_base_url:
        return OpenAICompatibleProvider(
            base_url=settings.lm_studio_base_url,
            api_key="lm-studio",
            provider_name="lmstudio",
            timeout_seconds=120.0,
            supports_json_mode=False,
        )
    if chosen == "openai" and settings.openai_api_key:
        return OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key=settings.openai_api_key,
            provider_name="openai",
        )
    if chosen == "ollama":
        return OpenAICompatibleProvider(
            base_url=settings.ollama_base_url,
            api_key="ollama",
            provider_name="ollama",
            timeout_seconds=120.0,
            supports_json_mode=False,
        )
    if chosen == "gemini" and settings.gemini_api_key:
        return GeminiProvider(api_key=settings.gemini_api_key)
    if chosen == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    return DeterministicMockProvider()
