"""Audio capture: the microphone and the system audio output, as continuous streams of 16 kHz mono blocks."""

import queue
import time
from collections.abc import Iterator

import numpy as np
import pyaudiowpatch as pyaudio
import sounddevice as sd
import soxr


class MicStream:
    """Records the default input device and yields raw audio blocks.

    The sounddevice callback only copies blocks into a queue, so recording keeps
    going while the caller is busy transcribing/translating.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.name = sd.query_devices(kind="input")["name"]
        self.queue: queue.Queue[np.ndarray] = queue.Queue()
        self.stream = sd.InputStream(
            samplerate=sample_rate, channels=1, dtype="float32", callback=self._callback
        )

    def _callback(self, indata, frames, time_info, status):
        self.queue.put(indata[:, 0].copy())

    def blocks(self) -> Iterator[np.ndarray]:
        with self.stream:
            self.started_at = time.monotonic()  # wall clock of sample 0
            while True:
                yield self.queue.get()


class LoopbackStream:
    """Records what the default output device plays (WASAPI loopback), e.g. the other side of a call.

    The device runs at its own rate/channels (typically 48 kHz stereo), so blocks are downmixed
    and resampled to 16 kHz mono. WASAPI delivers no data at all while nothing is playing; such
    gaps are filled with silence by the wall clock, otherwise the VAD would never see the pause
    that ends a phrase and the stream time would drift from the real time.
    """

    def __init__(self, sample_rate: int = 16000, gap_timeout: float = 0.2, gap_margin: float = 0.1):
        self.sample_rate = sample_rate
        self.gap_timeout = gap_timeout  # no data for this long = nothing is playing
        self.gap_margin = gap_margin  # leave room for data still in flight when filling
        self.queue: queue.Queue[bytes] = queue.Queue()

        self.pa = pyaudio.PyAudio()
        device = self.pa.get_default_wasapi_loopback()
        self.name = device["name"]
        self.channels = device["maxInputChannels"]
        self.device_rate = int(device["defaultSampleRate"])
        self.resampler = soxr.ResampleStream(self.device_rate, sample_rate, 1, dtype="float32")
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=self.channels,
            rate=self.device_rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=self.device_rate // 50,  # 20 ms
            stream_callback=self._callback,
            start=False,
        )

    def _callback(self, in_data, frame_count, time_info, status):
        self.queue.put(in_data)
        return None, pyaudio.paContinue

    def blocks(self) -> Iterator[np.ndarray]:
        self.stream.start_stream()
        self.started_at = time.monotonic()  # wall clock of sample 0
        received = 0  # device-rate frames so far, real or filled
        try:
            while True:
                try:
                    data = self.queue.get(timeout=self.gap_timeout)
                    frames = np.frombuffer(data, dtype=np.float32).reshape(-1, self.channels).mean(axis=1)
                except queue.Empty:
                    elapsed = time.monotonic() - self.started_at - self.gap_margin
                    missing = int(elapsed * self.device_rate) - received
                    if missing <= 0:
                        continue
                    frames = np.zeros(missing, dtype=np.float32)
                received += len(frames)
                block = self.resampler.resample_chunk(frames)
                if len(block):
                    yield block
        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
