"""Speaker identification on the call side: voice embeddings + online clustering ("Speaker 1", "Speaker 2", ...)."""

import urllib.request
from pathlib import Path

import numpy as np
import sherpa_onnx

MODEL_NAME = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/{MODEL_NAME}"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / MODEL_NAME


class SpeakerTracker:
    """Tells call-side speakers apart without any enrollment: starts empty and learns voices as they speak.

    Each phrase becomes a voiceprint (CAM++ embedding). It goes to the known speaker whose average voiceprint
    is most similar (cosine >= threshold); otherwise it starts a new speaker.
    """

    def __init__(self, threshold: float = 0.55, sample_rate: int = 16000, threads: int = 0):
        if not MODEL_PATH.exists():
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(MODEL_PATH), num_threads=threads or 4
        )
        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.sums: list[np.ndarray] = []  # per speaker: sum of unit voiceprints; its direction is the average

    def identify(self, audio: np.ndarray) -> str:
        return self.assign(self.embed(audio))

    def embed(self, audio: np.ndarray) -> np.ndarray:
        stream = self.extractor.create_stream()
        stream.accept_waveform(self.sample_rate, audio)
        stream.input_finished()
        e = np.array(self.extractor.compute(stream))
        return e / np.linalg.norm(e)

    def assign(self, voiceprint: np.ndarray) -> str:
        if self.sums:
            scores = [s @ voiceprint / np.linalg.norm(s) for s in self.sums]
            best = int(np.argmax(scores))
            if scores[best] >= self.threshold:
                self.sums[best] = self.sums[best] + voiceprint
                return f"Speaker {best + 1}"
        self.sums.append(voiceprint)
        return f"Speaker {len(self.sums)}"
