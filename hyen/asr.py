"""Armenian speech -> Armenian text. Two interchangeable backends with the same interface."""

import numpy as np


class FastConformerTranscriber:
    """NVIDIA FastConformer (CTC head) on ONNX Runtime via onnx-asr."""

    MODEL = "OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx"

    def __init__(self, sample_rate: int = 16000, threads: int = 0):
        import onnx_asr

        self.model = onnx_asr.load_model(self.MODEL)
        self.sample_rate = sample_rate  # onnx-asr types this as a Literal of supported rates

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: mono float32 samples in [-1, 1] at self.sample_rate."""
        return self.model.recognize(audio, sample_rate=self.sample_rate).strip()  # type: ignore[call-overload]


class WhisperTranscriber:
    """Chillarmo/whisper-large-v3-turbo-armenian (CTranslate2 conversion) via faster-whisper."""

    MODEL = "hurricup/whisper-large-v3-turbo-armenian-ct2"

    def __init__(self, sample_rate: int = 16000, threads: int = 0):
        from faster_whisper import WhisperModel

        # The checkpoint is float16; CTranslate2 quantizes it to int8 at load time for CPU.
        self.model = WhisperModel(self.MODEL, device="cpu", compute_type="int8", cpu_threads=threads)
        self.sample_rate = sample_rate  # faster-whisper expects 16 kHz arrays

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="hy",
            beam_size=1,
            vad_filter=False,  # phrases are already cut by our own VAD
            condition_on_previous_text=False,
            without_timestamps=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()


ASR_MODELS = {
    "fastconformer": FastConformerTranscriber,
    "whisper": WhisperTranscriber,
}


def Transcriber(name: str = "fastconformer", sample_rate: int = 16000, threads: int = 0):
    return ASR_MODELS[name](sample_rate=sample_rate, threads=threads)
