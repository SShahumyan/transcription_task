# Live Armenian → English transcription (Mathrix coding challenge)

Python CLI: captures audio, transcribes spoken Armenian, translates to English, prints labelled lines live.
The brief is `Mathrix_AI_Coding_Challenge.docx` (not committed). **Read `docs/PROJECT_STATE.md` first**: it has the
decisions, measurements, progress and next steps.

## Rules from the user
- **Never run git write commands** (add/commit/push/reset…). The user does all git/GitHub work. Read-only git is fine;
  suggest a commit message at the end of a step.
- The user wants to research together and steer: explain trade-offs with references, ask before big pivots.
- Brief requirements to keep in mind: local models only (no cloud APIs), ≤5 s from phrase end to printed line,
  README must explain model choices/alternatives/architecture/limitations, every AI chat session exported to `chats/`
  as separate .md files, never commit model weights/audio/keys. ~20 h total budget.

## Environment
- Windows 10, Intel i5-8265U (4 cores / 8 threads), 16 GB RAM, **no GPU**. Python 3.12.10 in `venv/`.
- Run: `venv\Scripts\python -m hyen.main` (use Windows Terminal for Armenian script). Options: `--asr-model
  fastconformer|whisper`, `--mt-model 600m|1.3b`, `--threads`, `--vad-threshold`, `--min-silence`, `--max-segment`, `--speaker-threshold`.
- Install: `venv\Scripts\pip install -r requirements.txt`. **No PyTorch** in the stack: onnxruntime, CTranslate2, sherpa-onnx.
- Models download on first run into the HF cache (`~/.cache/huggingface`); the VAD model goes into `models/` (gitignored).

## Code layout (`hyen/`)
- `audio.py`: `MicStream` (default mic, sounddevice) and `LoopbackStream` (default output device via PyAudioWPatch WASAPI
  loopback, downmix + soxr to 16 kHz, fills silence gaps by wall clock); both: `blocks()` yields 16 kHz mono, `started_at` = wall clock of sample 0
- `vad.py`: `Segmenter` (Silero VAD via sherpa-onnx); `feed(block) -> list[Segment]`, `flush()`; re-cuts segments with 0.3 s padding from a rolling buffer
- `asr.py`: `FastConformerTranscriber` (default, onnx-asr) and `WhisperTranscriber` (faster-whisper); `ASR_MODELS` dict, `Transcriber(name)` factory; interface `transcribe(np.float32 16 kHz) -> str`
- `translate.py`: `Translator` (NLLB-200 on CTranslate2 int8); `MT_MODELS` dict; `translate(str) -> str`
- `speakers.py`: `SpeakerTracker` (CAM++ zh+en embeddings via sherpa-onnx, model in `models/`); `identify(audio) -> "Speaker N"`,
  split into `embed()` + `assign(voiceprint)` so studies can replay precomputed voiceprints; online clustering, no enrollment
- `main.py`: CLI; one capture thread + `Segmenter` per source → shared queue → main thread runs ASR → speaker ID (Call
  only) → MT → print `[phrase end] Me|Speaker N HY: … EN: … (asr, spk, mt, lat)`

## Testing without a microphone
The laptop mic does NOT pick up the laptop speakers (Realtek echo cancellation), so acoustic loopback tests don't work.
For the `Call` side, just play a wav through the speakers (e.g. `sounddevice.play` from a driver script that starts
`hyen.main` as a subprocess): WASAPI loopback captures it digitally. For the mic side, feed audio files to `hyen.main` in real time by monkeypatching `MicStream` with a fake class whose `blocks()`
yields 100 ms blocks at real-time pace and sets `started_at`. Armenian test clips: Common Voice 20 via the HF datasets-server
rows API (`Chillarmo/common_voice_20_armenian`, test split, mp3 → decode with `soundfile`, resample to 16 kHz).
Multi-speaker tests: group rows by `client_id` (same id = same person; ~10 ids have 8+ clips in the first 700 test rows).
Keep such scripts and clips in the session scratchpad, not the repo.
