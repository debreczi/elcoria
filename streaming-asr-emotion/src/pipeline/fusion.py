import asyncio
import json
import logging
from typing import Dict, Any, AsyncIterator
from pathlib import Path
from .base import BaseFusion
from ..schemas import EmotionResult, FusionResult

logger = logging.getLogger(__name__)


class OllamaFusion(BaseFusion):
    """Question generation using local Ollama LLM."""

    def __init__(self):
        self.ollama_url = "http://localhost:11434"
        self.model = "qwen2.5:7b"
        self.temperature = 0.3
        self.max_tokens = 256
        self.system_prompt = ""
        self.http_client = None

    def load(self, config: Dict[str, Any]) -> None:
        try:
            import httpx

            self.ollama_url = config.get("ollama_url", "http://localhost:11434")
            self.model = config.get("model", "qwen2.5:7b")
            self.temperature = config.get("temperature", 0.3)
            self.max_tokens = config.get("max_tokens", 256)

            # Load system prompt
            prompt_file = config.get("system_prompt_file", "prompts/doctor_questions_hu.txt")
            if Path(prompt_file).exists():
                with open(prompt_file, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read().strip()
            else:
                self.system_prompt = "Te egy orvosi asszisztens vagy. Generálj 3-5 tisztázó kérdést az orvos számára."

            self.http_client = httpx.AsyncClient(timeout=120.0)
            logger.info(f"OllamaFusion loaded: {self.model} at {self.ollama_url}")

            # Pre-warm: tell Ollama to load the model into VRAM now and keep it.
            try:
                import requests
                requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self.model, "prompt": " ", "keep_alive": -1, "stream": False},
                    timeout=180,
                )
                logger.info(f"OllamaFusion pre-warmed: {self.model} resident in VRAM")
            except Exception as warm_err:
                logger.warning(f"Ollama pre-warm failed (will warm lazily): {warm_err}")
        except Exception as e:
            logger.error(f"Failed to load OllamaFusion: {e}")
            raise

    async def generate(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> FusionResult:
        """Generate questions (collect full response)."""
        questions = ""
        async for chunk in self.generate_stream(transcript, emotion, session_ctx):
            questions += chunk

        return FusionResult(questions=questions, utterance_id="")

    async def generate_stream(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> AsyncIterator[str]:
        """Stream question generation token by token."""
        if not self.http_client:
            return

        try:
            # Build context
            context = "\n".join(session_ctx[-3:]) if session_ctx else ""

            # Build prompt
            user_prompt = f"""
Páciens mondta: "{transcript}"
Hangja: {emotion.label} ({', '.join([f'{k}: {v:.0%}' for k, v in sorted(emotion.scores.items(), key=lambda x: x[1], reverse=True)[:3]])})

{f'Kontextus: {context}' if context else ''}

Generálj 3-5 tisztázó kérdést, amelyet az orvosnak fel kell tennie:
"""

            payload = {
                "model": self.model,
                "prompt": user_prompt,
                "system": self.system_prompt,
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "stream": True,
                "keep_alive": -1,  # keep model resident in VRAM
            }

            # Stream response
            async with self.http_client.stream(
                "POST",
                f"{self.ollama_url}/api/generate",
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                        except json.JSONDecodeError:
                            pass

        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            yield "Nem sikerült a kérdések generálása."

    async def shutdown(self) -> None:
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None


class TemplateFusion(BaseFusion):
    """Rule-based question generation (fast fallback, no LLM required)."""

    QUESTION_TEMPLATES = {
        "anxious": [
            "Mióta érzi magát így?",
            "Van-e konkrét okot, ami aggódásra ad okot?",
            "Szokott-e ilyen esetben nyugódva beszélgetni?",
        ],
        "angry": [
            "Mi az oka a felháborodottságnak?",
            "Meddig tartott már ez az állapot?",
            "Van-e olyan dolog, ami megnyugtatná?",
        ],
        "sad": [
            "Mióta érzi magát szomorúnak?",
            "Van-e okafor ezt az érzelmet?",
            "Van-e valakit aki támogatná?",
        ],
        "neutral": [
            "Milyen tünetei vannak?",
            "Meddig tartanak a tünetek?",
            "Van-e egyéb problémája?",
        ],
        "happy": [
            "Örül-e az aktuális kezelésnek?",
            "Van-e mellékhatása a kezelésnek?",
            "Hogyan érzi magát általánosan?",
        ],
        "fearful": [
            "Mit fél a legjobban?",
            "Mióta érzi ezt az érzést?",
            "Van-e módja a félelmei kezelésére?",
        ],
    }

    def __init__(self):
        pass

    def load(self, config: Dict[str, Any]) -> None:
        logger.info("TemplateFusion loaded (no model needed)")

    async def generate(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> FusionResult:
        """Generate questions from templates."""
        questions_text = ""
        async for chunk in self.generate_stream(transcript, emotion, session_ctx):
            questions_text += chunk

        return FusionResult(questions=questions_text, utterance_id="")

    async def generate_stream(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> AsyncIterator[str]:
        """Stream template-based questions."""
        emotion_label = emotion.label
        questions = self.QUESTION_TEMPLATES.get(emotion_label, self.QUESTION_TEMPLATES["neutral"])

        # Yield questions one at a time with small delays
        for i, question in enumerate(questions):
            # Simulate streaming
            for char in question:
                yield char
                await asyncio.sleep(0.01)  # 10ms delay per char

            if i < len(questions) - 1:
                yield "\n"
                await asyncio.sleep(0.1)

    async def shutdown(self) -> None:
        pass
