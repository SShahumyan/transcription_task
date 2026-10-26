"""Armenian speech -> Armenian text with NVIDIA FastConformer (CTC) running on ONNX Runtime."""

import numpy as np
import onnx_asr

ASR_MODEL = "OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx"


class Transcriber:
    def __init__(self, sample_rate: int = 16000):
        self.model = onnx_asr.load_model(ASR_MODEL)
        self.sample_rate = sample_rate

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: mono float32 samples in [-1, 1] at self.sample_rate."""
        return self.model.recognize(audio, sample_rate=self.sample_rate).strip()
