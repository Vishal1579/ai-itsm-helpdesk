"""Hugging Face LLM access.

Providers:
  * local        - runs an open-source instruct model on this machine via `transformers`
                   (default Qwen/Qwen2.5-0.5B-Instruct: Apache-2.0, ~1 GB, CPU friendly).
  * hf_inference - Hugging Face Inference Providers chat-completion API (needs HF_TOKEN),
                   default Qwen/Qwen2.5-7B-Instruct for higher quality answers.
  * extractive   - no generation; callers fall back to deterministic extractive answers.

Any provider error degrades gracefully to `None` so the platform keeps working.
"""
import asyncio
import logging
import threading
import time

from app.config import get_settings

log = logging.getLogger(__name__)


class LLM:
    def __init__(self) -> None:
        s = get_settings()
        self.provider = s.llm_provider
        self.model_name = {
            "local": s.llm_local_model,
            "hf_inference": s.llm_hf_model,
            "extractive": "extractive (no LLM)",
        }[self.provider]
        self._tokenizer = None
        self._model = None
        self._device = "cpu"
        self._lock = threading.Lock()
        self.last_error: str | None = None
        if self.provider == "hf_inference" and not s.hf_token:
            log.warning("LLM_PROVIDER=hf_inference but HF_TOKEN not set - using extractive mode")
            self.provider, self.model_name = "extractive", "extractive (no HF_TOKEN)"

    def info(self) -> dict:
        return {"provider": self.provider, "model": self.model_name, "last_error": self.last_error}

    # -- public -------------------------------------------------------------------------
    async def generate(self, system: str, user: str, max_new_tokens: int | None = None) -> str | None:
        if self.provider == "extractive":
            return None
        max_new_tokens = max_new_tokens or get_settings().llm_max_new_tokens
        try:
            started = time.perf_counter()
            if self.provider == "hf_inference":
                out = await asyncio.to_thread(self._hf_inference, system, user, max_new_tokens)
            else:
                out = await asyncio.to_thread(self._local, system, user, max_new_tokens)
            log.info("LLM %s generated %d chars in %.1fs", self.model_name, len(out), time.perf_counter() - started)
            self.last_error = None
            return out.strip()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.last_error = str(exc)[:300]
            log.exception("LLM generation failed; falling back to extractive answer")
            return None

    def warmup(self) -> None:
        if self.provider == "local":
            self._load_local()

    # -- providers -----------------------------------------------------------------------
    def _hf_inference(self, system: str, user: str, max_new_tokens: int) -> str:
        from huggingface_hub import InferenceClient

        client = InferenceClient(model=self.model_name, token=get_settings().hf_token, timeout=60)
        resp = client.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_new_tokens,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""

    def _load_local(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            pref = get_settings().llm_device
            if pref == "auto":
                pref = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
            self._device = pref
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForCausalLM.from_pretrained(self.model_name).to(self._device)
            self._model.eval()
            log.info("Loaded local LLM %s on %s", self.model_name, self._device)

    def _local(self, system: str, user: str, max_new_tokens: int) -> str:
        import torch

        self._load_local()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        with torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.1,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
