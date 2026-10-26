"""Prototype: microphone -> Armenian transcription -> English translation -> terminal."""

import argparse
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# transformers is only used for the tokenizer, so its "PyTorch was not found" notice is noise.
# The bundled NLLB tokenizer also triggers a false "incorrect regex pattern" warning;
# its token ids were checked to match facebook/nllb-200-distilled-600M exactly.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import numpy as np

from hyen.asr import Transcriber
from hyen.audio import MicChunker
from hyen.translate import MT_MODELS, Translator


def format_elapsed(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-seconds", type=float, default=5.0)
    parser.add_argument("--mt-model", choices=MT_MODELS, default="600m")
    parser.add_argument("--threads", type=int, default=0, help="MT CPU threads (0 = auto)")
    parser.add_argument(
        "--silence-rms", type=float, default=0.005, help="skip chunks quieter than this"
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    print("Loading models...", flush=True)
    transcriber = Transcriber()
    translator = Translator(args.mt_model, threads=args.threads)
    mic = MicChunker(args.chunk_seconds)
    print(f"Listening (chunks of {args.chunk_seconds:g}s). Ctrl+C to stop.\n", flush=True)

    start = time.monotonic()
    audio_seconds = 0.0
    try:
        for chunk in mic.chunks():
            audio_seconds += len(chunk) / mic.sample_rate
            if np.sqrt(np.mean(chunk**2)) < args.silence_rms:
                continue

            t0 = time.perf_counter()
            hy = transcriber.transcribe(chunk)
            t1 = time.perf_counter()
            if not hy:
                continue
            en = translator.translate(hy)
            t2 = time.perf_counter()

            print(
                f"[{format_elapsed(audio_seconds)}] Me  HY: {hy}  EN: {en}"
                f"   (asr {t1 - t0:.2f}s, mt {t2 - t1:.2f}s,"
                f" behind {mic.backlog_seconds():.1f}s)",
                flush=True,
            )
    except KeyboardInterrupt:
        print(f"\nStopped after {format_elapsed(time.monotonic() - start)}.")


if __name__ == "__main__":
    main()
