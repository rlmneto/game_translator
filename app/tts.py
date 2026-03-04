"""
Text-to-Speech engine — reads translated text aloud.

Supports: edge-tts (Microsoft neural voices, primary),
          pyttsx3 (offline fallback), and gTTS (Google, online).
Audio playback via pygame.mixer.
"""

import asyncio
import io
import logging
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

# -- optional imports ----------------------------------------------------

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    import pygame.mixer as _mixer
    _mixer.init()
    PYGAME_MIXER_AVAILABLE = True
except Exception:
    PYGAME_MIXER_AVAILABLE = False


# -- edge-tts voice map (natural neural voices) --------------------------
# Each entry: lang_code → (voice_name, friendly_label)

EDGE_VOICE_MAP: dict[str, str] = {
    "pt-br": "pt-BR-FranciscaNeural",
    "en":    "en-US-JennyNeural",
    "es":    "es-MX-DaliaNeural",
    "fr":    "fr-FR-DeniseNeural",
    "de":    "de-DE-KatjaNeural",
    "it":    "it-IT-ElsaNeural",
    "ja":    "ja-JP-NanamiNeural",
    "ko":    "ko-KR-SunHiNeural",
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "zh-tw": "zh-TW-HsiaoChenNeural",
    "ru":    "ru-RU-SvetlanaNeural",
    "pl":    "pl-PL-ZofiaNeural",
    "nl":    "nl-NL-ColetteNeural",
    "tr":    "tr-TR-EmelNeural",
}

PYTTSX3_LANG_MAP: dict[str, str] = {
    "pt-br": "portuguese_brazil",
    "en":    "english",
    "es":    "spanish",
    "fr":    "french",
    "de":    "german",
    "it":    "italian",
    "ja":    "japanese",
    "ko":    "korean",
    "zh-cn": "chinese",
    "zh-tw": "chinese",
    "ru":    "russian",
    "pl":    "polish",
    "nl":    "dutch",
    "tr":    "turkish",
}

GTTS_LANG_MAP: dict[str, str] = {
    "pt-br": "pt",
    "en":    "en",
    "es":    "es",
    "fr":    "fr",
    "de":    "de",
    "it":    "it",
    "ja":    "ja",
    "ko":    "ko",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "ru":    "ru",
    "pl":    "pl",
    "nl":    "nl",
    "tr":    "tr",
}


class TTSEngine:
    """Thread-safe text-to-speech engine with stop capability."""

    def __init__(self):
        self._playing = False
        self._stop_flag = False
        self._lock = threading.Lock()
        self._engine_name = self._pick_engine()
        logger.info("TTS engine: %s", self._engine_name or "none available")

    # -- engine selection ------------------------------------------------

    @staticmethod
    def _pick_engine() -> str | None:
        # prefer edge-tts (neural, human-like) → gtts → pyttsx3
        if EDGE_TTS_AVAILABLE and PYGAME_MIXER_AVAILABLE:
            return "edge-tts"
        if GTTS_AVAILABLE and PYGAME_MIXER_AVAILABLE:
            return "gtts"
        if PYTTSX3_AVAILABLE:
            return "pyttsx3"
        return None

    @property
    def is_available(self) -> bool:
        return self._engine_name is not None

    @staticmethod
    def available_engines() -> list[str]:
        engines: list[str] = []
        if EDGE_TTS_AVAILABLE and PYGAME_MIXER_AVAILABLE:
            engines.append("edge-tts")
        if PYTTSX3_AVAILABLE:
            engines.append("pyttsx3")
        if GTTS_AVAILABLE and PYGAME_MIXER_AVAILABLE:
            engines.append("gtts")
        return engines

    # -- public API ------------------------------------------------------

    def speak(self, text: str, lang: str = "pt-br",
              on_status=None, on_done=None):
        """Speak *text* in a background thread. Non-blocking."""
        if not self.is_available:
            logger.warning("No TTS engine available")
            return
        if not text.strip():
            return

        with self._lock:
            if self._playing:
                self._stop_flag = True

        threading.Thread(
            target=self._speak_worker,
            args=(text, lang, on_status, on_done),
            daemon=True,
        ).start()

    def stop(self):
        """Request playback stop."""
        with self._lock:
            self._stop_flag = True
        # stop pygame playback immediately if active
        if PYGAME_MIXER_AVAILABLE:
            try:
                _mixer.music.stop()
            except Exception:
                pass

    @property
    def is_playing(self) -> bool:
        return self._playing

    # -- workers ---------------------------------------------------------

    def _speak_worker(self, text: str, lang: str,
                      on_status, on_done):
        # wait for previous playback to actually finish
        while self._playing:
            time.sleep(0.1)

        with self._lock:
            self._playing = True
            self._stop_flag = False

        try:
            if on_status:
                on_status("🔊 Gerando áudio...")

            if self._engine_name == "edge-tts":
                self._speak_edge(text, lang)
            elif self._engine_name == "gtts":
                self._speak_gtts(text, lang)
            elif self._engine_name == "pyttsx3":
                self._speak_pyttsx3(text, lang)

            if on_status and not self._stop_flag:
                on_status("🔊 Reprodução concluída")
        except Exception as exc:
            logger.exception("TTS error")
            if on_status:
                on_status(f"❌ Erro TTS: {exc}")
        finally:
            with self._lock:
                self._playing = False
                self._stop_flag = False
            if on_done:
                on_done()

    # -- edge-tts (Microsoft neural voices) ------------------------------

    def _speak_edge(self, text: str, lang: str):
        voice = EDGE_VOICE_MAP.get(lang, "en-US-JennyNeural")
        logger.info("edge-tts: voice=%s  chars=%d", voice, len(text))

        buf = io.BytesIO()

        async def _generate():
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
                if self._stop_flag:
                    return

        # run the async generator in a new event loop
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_generate())
        finally:
            loop.close()

        if self._stop_flag or buf.tell() == 0:
            return

        buf.seek(0)
        self._play_audio(buf)

    # -- gTTS (online / Google) ------------------------------------------

    def _speak_gtts(self, text: str, lang: str):
        tts_lang = GTTS_LANG_MAP.get(lang, "en")
        logger.info("gTTS: lang=%s  chars=%d", tts_lang, len(text))

        tts = gTTS(text=text, lang=tts_lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)

        self._play_audio(buf)

    # -- pyttsx3 (offline) -----------------------------------------------

    def _speak_pyttsx3(self, text: str, lang: str):
        logger.info("pyttsx3: lang=%s  chars=%d", lang, len(text))
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)

        tts_lang = PYTTSX3_LANG_MAP.get(lang, "")
        voices = engine.getProperty("voices")
        for voice in voices:
            name_lower = voice.name.lower()
            if tts_lang and tts_lang in name_lower:
                engine.setProperty("voice", voice.id)
                logger.info("TTS voice: %s", voice.name)
                break
            if lang.replace("-", "") in (voice.id or "").lower():
                engine.setProperty("voice", voice.id)
                logger.info("TTS voice: %s", voice.name)
                break

        engine.say(text)
        engine.runAndWait()
        engine.stop()

    # -- audio playback (shared) -----------------------------------------

    def _play_audio(self, buf: io.BytesIO):
        """Play an MP3 buffer via pygame.mixer. Blocks until done or stopped."""
        _mixer.music.load(buf, "mp3")
        _mixer.music.play()

        while _mixer.music.get_busy():
            if self._stop_flag:
                _mixer.music.stop()
                return
            time.sleep(0.1)
