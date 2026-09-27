"""ИИ-ответ: аналог «AI Agent1» + «OpenAI Chat Model1» + «Simple Memory»."""
import logging
from collections import defaultdict, deque

from openai import AsyncOpenAI

from .texts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

FALLBACK_ANSWER = (
    "Печально, что я не смог помочь. Попробуй задать вопрос корректнее, "
    "возможно, мы сможем его решить!"
)


class AIResponder:
    def __init__(self, api_key: str, model: str, max_tokens: int, temperature: float, window: int):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        # Как Simple Memory в n8n: последние `window` пар вопрос-ответ на пользователя (в памяти процесса)
        self._memory: dict[int, deque] = defaultdict(lambda: deque(maxlen=window * 2))

    async def answer(self, user_id: int, text: str) -> str:
        history = self._memory[user_id]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": text}]
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            output = (resp.choices[0].message.content or "").strip() or FALLBACK_ANSWER
        except Exception:
            log.exception("Ошибка OpenAI")
            return FALLBACK_ANSWER
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": output})
        return output
