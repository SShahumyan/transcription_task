"""Prototype: microphone + system audio -> Armenian transcription -> English translation -> terminal."""

import argparse
import os
import queue
import sys
import threading
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# transformers is only used for the tokenizer, so its "PyTorch was not found" notice is noise.
# The bundled NLLB tokenizer also triggers a false "incorrect regex pattern" warning;
# its token ids were checked to match facebook/nllb-200-distilled-600M exactly.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from hyen.asr import ASR_MODELS, Transcriber
from hyen.audio import LoopbackStream, MicStream
from hyen.speakers import SpeakerTracker
from hyen.translate import MT_MODELS, Translator
from hyen.vad import Segment, Segmenter


def format_elapsed(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def capture(label: str, stream, segmenter: Segmenter, segments: queue.Queue, stop: threading.Event):
    """Capture thread: one per audio source. Cuts its stream into phrases and queues them."""
    for block in stream.blocks():
        for seg in segmenter.feed(block):
            segments.put((label, seg, stream.started_at))
        if stop.is_set():
            break
    for seg in segmenter.flush():
        segments.put((label, seg, stream.started_at))


def process(
    label: str, seg: Segment, stream_start: float, session_start: float, transcriber, translator, speakers
):
    t0 = time.perf_counter()
    hy = transcriber.transcribe(seg.audio)
    t1 = time.perf_counter()
    if not hy:
        return  # noise, coughs etc. never reach the speaker tracker, so they can't create a speaker
    if label == "Call":
        label = speakers.identify(seg.audio)
    t2 = time.perf_counter()
    en = translator.translate(hy)
    t3 = time.perf_counter()

    # Latency as the brief defines it: from the end of the spoken phrase to the printed line.
    phrase_end = stream_start + seg.end
    latency = time.monotonic() - phrase_end
    print(
        f"[{format_elapsed(phrase_end - session_start)}] {label:<9}  HY: {hy}  EN: {en}"
        f"   (asr {t1 - t0:.2f}s, spk {t2 - t1:.2f}s, mt {t3 - t2:.2f}s, lat {latency:.1f}s)",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-model", choices=ASR_MODELS, default="fastconformer")
    parser.add_argument("--mt-model", choices=MT_MODELS, default="600m")
    parser.add_argument("--threads", type=int, default=0, help="CPU threads (0 = auto)")
    parser.add_argument("--vad-threshold", type=float, default=0.5, help="speech probability")
    parser.add_argument(
        "--min-silence", type=float, default=0.5, help="pause (s) that ends a phrase"
    )
    parser.add_argument(
        "--max-segment", type=float, default=12.0, help="force a cut after this many seconds"
    )
    parser.add_argument(
        "--speaker-threshold", type=float, default=0.55, help="voice similarity to count as the same speaker"
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    print("Loading models...", flush=True)
    transcriber = Transcriber(args.asr_model, threads=args.threads)
    translator = Translator(args.mt_model, threads=args.threads)
    speakers = SpeakerTracker(threshold=args.speaker_threshold, threads=args.threads)
    sources = {"Me": MicStream(), "Call": LoopbackStream()}

    segments: queue.Queue = queue.Queue()
    stop = threading.Event()
    threads = []
    for label, stream in sources.items():
        print(f"{label:<4}  <- {stream.name}", flush=True)
        segmenter = Segmenter(
            stream.sample_rate,
            threshold=args.vad_threshold,
            min_silence=args.min_silence,
            max_segment=args.max_segment,
        )
        threads.append(
            threading.Thread(
                target=capture, args=(label, stream, segmenter, segments, stop), daemon=True
            )
        )

    session_start = time.monotonic()
    for t in threads:
        t.start()
    print("Listening. Ctrl+C to stop.\n", flush=True)

    # The main thread is the only worker: ASR and MT share the CPU, so phrases are processed one at a time.
    try:
        while True:
            try:
                item = segments.get(timeout=0.5)  # a timeout keeps Ctrl+C responsive on Windows
            except queue.Empty:
                continue
            process(*item, session_start, transcriber, translator, speakers)
    except KeyboardInterrupt:
        stop.set()
        for t in threads:
            t.join(timeout=2)
        while not segments.empty():
            process(*segments.get(), session_start, transcriber, translator, speakers)
        print(f"\nStopped after {format_elapsed(time.monotonic() - session_start)}.")


if __name__ == "__main__":
    main()
