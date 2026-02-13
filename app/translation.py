import os
from openai import OpenAI
from .config import BASE_DIR

SYSTEM_PROMPT = (
    "You are a translator for video game dialog text. "
    "The user provides English text extracted via OCR from game dialog boxes. "
    "The OCR may contain small errors. Your task:\n"
    "1. Fix any obvious OCR errors in the English text.\n"
    "2. Translate the corrected text to Brazilian Portuguese (pt-BR).\n"
    "3. Keep proper nouns (character names, location names, item names) in English.\n"
    "Reply with ONLY: first the corrected English on one line, then '---', "
    "then the pt-BR translation. No explanations."
)


class TranslationService:
    def __init__(self):
        self.client = None
        token = self._load_token()
        if token:
            self.client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=token,
            )

    @property
    def is_ready(self) -> bool:
        return self.client is not None

    def translate(self, text: str) -> tuple[str, str]:
        """Returns (corrected_english, pt_br_translation)."""
        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"[Game dialog OCR]: {text}"},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip()

        if "---" in raw:
            corrected, translation = raw.split("---", 1)
            return corrected.strip(), translation.strip()
        return text, raw

    @staticmethod
    def _load_token() -> str:
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GITHUB_TOKEN="):
                        return line.strip().split("=", 1)[1].strip()
        return os.environ.get("GITHUB_TOKEN", "")
