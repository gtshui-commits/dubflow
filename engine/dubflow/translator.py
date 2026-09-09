from __future__ import annotations

import re
from typing import Callable, List, Optional

import httpx

from .asr.base import Transcript

BATCH_SIZE = 20
ProgressFn = Optional[Callable[[float, str], None]]


class TranslationError(RuntimeError):
    pass


class LLMTranslator:
    """OpenAI-compatible chat completions translator with context-window batching.

    Works with OpenAI, DeepSeek, Ollama (/v1), or any compatible endpoint.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        temperature: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.target_lang = target_lang
        self.source_lang = source_lang or "the source language"
        self.temperature = temperature

    def _chat(self, messages: list) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = httpx.post(
            url,
            headers=headers,
            json={"model": self.model, "temperature": self.temperature, "messages": messages},
            timeout=180,
        )
        if resp.status_code != 200:
            raise TranslationError(f"LLM API {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    def translate_transcript(self, transcript: Transcript, progress: ProgressFn = None) -> List[str]:
        segments = transcript.segments
        results: List[str] = []
        total = len(segments)
        for i in range(0, total, BATCH_SIZE):
            batch = segments[i:i + BATCH_SIZE]
            results.extend(self._translate_batch(batch))
            if progress:
                progress(min(len(results) / max(total, 1), 1.0),
                         f"{len(results)}/{total} lines")
        return results

    def _translate_batch(self, batch) -> List[str]:
        numbered = "\n".join(f"{i + 1}. {s.text}" for i, s in enumerate(batch))
        system = (
            "You are a professional subtitle translator. "
            f"Translate each numbered line from {self.source_lang} into {self.target_lang}. "
            "Rules: keep the same numbering, one output line per input line, "
            "concise natural spoken style suitable for subtitles, no extra commentary."
        )
        content = self._chat([
            {"role": "system", "content": system},
            {"role": "user", "content": numbered},
        ])
        parsed = self._parse_numbered(content, len(batch))
        if parsed is not None:
            return parsed
        # count mismatch -> per-line fallback
        out = []
        for s in batch:
            out.append(self._chat([
                {"role": "system", "content": system},
                {"role": "user", "content": f"1. {s.text}"},
            ]).strip())
        return out

    @staticmethod
    def _parse_numbered(text: str, expected: int) -> Optional[List[str]]:
        found: dict = {}
        last = 0
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"^(\d+)\s*[.、):：]\s*(.*)$", line)
            if m:
                idx = int(m.group(1))
                found[idx] = m.group(2).strip()
                last = idx
            elif last:
                found[last] = (found[last] + " " + line).strip()
        if len(found) != expected:
            return None
        return [found[i] for i in range(1, expected + 1)]
