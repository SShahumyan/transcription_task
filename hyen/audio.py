"""Microphone capture, cut into fixed-length chunks (no phrase detection yet)."""

import queue
from collections.abc import Iterator

import numpy as np
import sounddevice as sd


class MicChunker:
    """Records the default input device and yields chunks of `chunk_seconds`.

    The sounddevice callback only copies blocks into a queue, so recording keeps
    going while the caller is busy transcribing/translating the previous chunk.
    """

    def __init__(self, chunk_seconds: float = 5.0, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.chunk_samples = int(chunk_seconds * sample_rate)
        self.blocks: queue.Queue[np.ndarray] = queue.Queue()
        self.stream = sd.InputStream(
            samplerate=sample_rate, channels=1, dtype="float32", callback=self._callback
        )

    def _callback(self, indata, frames, time_info, status):
        self.blocks.put(indata[:, 0].copy())

    def backlog_seconds(self) -> float:
        """Audio waiting in the queue, i.e. how far processing lags behind real time."""
        return sum(len(b) for b in list(self.blocks.queue)) / self.sample_rate

    def chunks(self) -> Iterator[np.ndarray]:
        buffer = np.zeros(0, dtype=np.float32)
        with self.stream:
            while True:
                buffer = np.concatenate([buffer, self.blocks.get()])
                while len(buffer) >= self.chunk_samples:
                    yield buffer[: self.chunk_samples]
                    buffer = buffer[self.chunk_samples :]
