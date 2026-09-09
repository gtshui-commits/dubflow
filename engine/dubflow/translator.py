from __future__ import annotations

import re
from typing import Callable, List, Optional

import httpx
from urllib.parse import urlencode

from .asr.base import Transcript
from .config import settings

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


_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


class GoogleTranslator:
    """Free Google endpoint (translate.googleapis.com), no key.
    Note: unreachable from mainland China; use microsoft there."""

    def __init__(self, target_lang: str, source_lang: Optional[str] = None) -> None:
        codes = {"zh": "zh-CN"}
        self.target = codes.get(target_lang, target_lang)
        self.source = codes.get(source_lang or "", source_lang) if source_lang else "auto"
        self._client = httpx.Client(timeout=60, headers=_UA, follow_redirects=True)

    def translate_transcript(self, transcript: Transcript, progress: ProgressFn = None) -> List[str]:
        texts = [s.text for s in transcript.segments]
        out: List[str] = []
        total = len(texts)
        for i in range(0, total, 40):
            batch = texts[i:i + 40]
            try:
                out.extend(self._translate_batch(batch))
            except Exception:
                out.extend([self._translate_one(t) for t in batch])
            if progress:
                progress(min(len(out) / max(total, 1), 1.0), f"{len(out)}/{total} lines")
        return out

    def _translate_batch(self, batch: List[str]) -> List[str]:
        # NOTE: content= with manual urlencode - httpx mangles data= lists via proxies
        body = urlencode([("q", t) for t in batch])
        resp = self._client.post(
            "https://translate.googleapis.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": self.source, "tl": self.target},
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        arr = resp.json()
        if isinstance(arr, list) and len(arr) == len(batch) \
                and all(isinstance(x, str) for x in arr):
            return arr
        raise TranslationError("unexpected google response shape")

    def _translate_one(self, text: str) -> str:
        resp = self._client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": self.source, "tl": self.target, "dt": "t", "q": text},
        )
        resp.raise_for_status()
        return "".join(part[0] for part in resp.json()[0] if part and part[0])


class MicrosoftTranslator:
    """Microsoft Translator via the official Azure Translator API.
    Requires a (free-tier OK) subscription key:
      env DUBFLOW_MSFT_TRANSLATOR_KEY / DUBFLOW_MSFT_TRANSLATOR_REGION
      or per-request translation_options api_key / region.
    Region: e.g. "global" or the resource's region (eastasia ...)."""

    HOST = "https://api.cognitive.microsofttranslator.com"

    def __init__(self, target_lang: str, source_lang: Optional[str] = None,
                 api_key: str = "", region: str = "") -> None:
        codes = {"zh": "zh-Hans"}
        self.target = codes.get(target_lang, target_lang)
        self.source = codes.get(source_lang or "", source_lang) if source_lang else None
        self.api_key = api_key or settings.msft_translator_key
        self.region = region or settings.msft_translator_region
        self._client = httpx.Client(timeout=60, trust_env=True)
        if not self.api_key:
            raise TranslationError(
                "Microsoft translation needs an Azure Translator key "
                "(free F0 tier works). Set DUBFLOW_MSFT_TRANSLATOR_KEY "
                "or fill the key field in the GUI."
            )

    def translate_transcript(self, transcript: Transcript, progress: ProgressFn = None) -> List[str]:
        texts = [s.text for s in transcript.segments]
        out: List[str] = []
        total = len(texts)
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.region and self.region.lower() != "global":
            headers["Ocp-Apim-Subscription-Region"] = self.region
        for i in range(0, total, 100):   # Azure allows up to 100 texts / request
            batch = texts[i:i + 100]
            params = {"api-version": "3.0", "to": [self.target]}
            if self.source:
                params["from"] = self.source
            resp = self._client.post(f"{self.HOST}/translate", params=params,
                                     headers=headers,
                                     json=[{"Text": t} for t in batch])
            if resp.status_code != 200:
                raise TranslationError(f"Azure translator {resp.status_code}: {resp.text[:300]}")
            for item in resp.json():
                tr = item.get("translations") or [{}]
                out.append(str(tr[0].get("text", "")))
            if progress:
                progress(min(len(out) / max(total, 1), 1.0), f"{len(out)}/{total} lines")
        return out


def build_translator(t_opts: dict, target_lang: str, source_lang: Optional[str] = None):
    """Factory: llm | google | microsoft -> object with translate_transcript()."""
    provider = (t_opts.get("provider") or "llm").lower()
    if provider == "google":
        return GoogleTranslator(target_lang, source_lang)
    if provider == "microsoft":
        return MicrosoftTranslator(target_lang, source_lang,
                                   api_key=t_opts.get("api_key") or "",
                                   region=t_opts.get("region") or "")
    return LLMTranslator(
        base_url=t_opts.get("base_url") or settings.translate_base_url,
        api_key=t_opts.get("api_key") or settings.translate_api_key,
        model=t_opts.get("model") or settings.translate_model,
        target_lang=target_lang,
        source_lang=source_lang,
    )
