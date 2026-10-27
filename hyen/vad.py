"""Phrase segmentation with Silero VAD (via sherpa-onnx): cuts the audio stream at pauses."""

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

VAD_MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
VAD_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "silero_vad.onnx"


@dataclass
class Segment:
    audio: np.ndarray  # speech plus padding on both sides
    start: float  # detected speech start/end, in seconds since the stream started
    end: float


class Segmenter:
    """Feed it audio blocks of any size; it returns the phrases that have ended."""

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence: float = 0.5,
        max_segment: float = 12.0,
        min_speech: float = 0.25,
        padding: float = 0.3,
    ):
        if not VAD_MODEL_PATH.exists():
            VAD_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(VAD_MODEL_URL, VAD_MODEL_PATH)

        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(VAD_MODEL_PATH)
        config.silero_vad.threshold = threshold
        config.silero_vad.min_silence_duration = min_silence
        config.silero_vad.min_speech_duration = min_speech
        config.silero_vad.max_speech_duration = max_segment
        config.sample_rate = sample_rate
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)

        self.sample_rate = sample_rate
        self.window = config.silero_vad.window_size
        self.pending = np.zeros(0, dtype=np.float32)

        # Silero tends to clip the first syllable, so segments are re-cut from this rolling
        # history with some padding on both sides. history[0] is absolute sample history_start.
        self.padding = int(padding * sample_rate)
        self.history = np.zeros(0, dtype=np.float32)
        self.history_start = 0
        self.history_max = 60 * sample_rate

    def feed(self, block: np.ndarray) -> list[Segment]:
        self.history = np.concatenate([self.history, block])
        if len(self.history) > self.history_max:
            drop = len(self.history) - self.history_max
            self.history = self.history[drop:]
            self.history_start += drop

        self.pending = np.concatenate([self.pending, block])
        while len(self.pending) >= self.window:
            self.vad.accept_waveform(self.pending[: self.window])
            self.pending = self.pending[self.window :]
        return self._drain()

    def flush(self) -> list[Segment]:
        """Emit speech still in progress (call on shutdown)."""
        self.vad.flush()
        return self._drain()

    def _drain(self) -> list[Segment]:
        segments = []
        while not self.vad.empty():
            seg = self.vad.front
            speech_end = seg.start + len(seg.samples)
            begin = max(seg.start - self.padding, self.history_start)
            end = min(speech_end + self.padding, self.history_start + len(self.history))
            audio = self.history[begin - self.history_start : end - self.history_start]
            segments.append(
                Segment(audio, seg.start / self.sample_rate, speech_end / self.sample_rate)
            )
            self.vad.pop()
        return segments
