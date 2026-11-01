# Live Armenian → English transcription

A Python command-line program that listens to a live conversation, such as a video call, transcribes spoken Armenian
and prints an English translation in the terminal, labelled by speaker:

- your microphone is labelled **`Me`**
- what the computer plays (the other side of the call) is split by voice into **`Speaker 1`, `Speaker 2`, …**

Everything runs locally on the CPU. After the one-time model download no audio or text leaves the machine, and it
works with Wi-Fi off.

```
[00:00:24] Speaker 2  HY: Արժանապատվություն հասկացությունը պատմական տարբեր ժամամանակահատվածներում տարբեր բովանդակություն է ունեցել։  EN: The concept of dignity has had different meanings at different times in history.   (asr 0.29s, spk 0.10s, mt 0.88s, lat 1.9s)
```

Each line shows the time the phrase ended (since the program started), the speaker, the Armenian original and the
English translation. The part in brackets shows how long each stage took and `lat`, the time from the end of the
phrase to the printed line (the brief's limit is 5 s; measured 1.3–2.7 s).

## Setup

Tested on Windows 10, Python 3.12, Intel i5-8265U (4 cores), 16 GB RAM, no GPU. Windows only: system audio is captured
with WASAPI loopback.

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

No PyTorch is needed: the models run on ONNX Runtime, CTranslate2 and sherpa-onnx. On the first run the models are
downloaded (about 1 GB in total): ASR and translation models into the Hugging Face cache (`~/.cache/huggingface`), the
VAD and speaker models (about 30 MB) into `models/`. Nothing is stored in the repository.

## Run

Use Windows Terminal; the classic console may not render Armenian script.

```
venv\Scripts\python -m hyen.main
```

Startup takes a few seconds (model loading). It then prints the devices it records and `Listening. Ctrl+C to stop.`

| Option | Default | Meaning |
|---|---|---|
| `--asr-model fastconformer\|whisper` | `fastconformer` | Speech recognition model (Whisper is too slow on this CPU; kept for comparison) |
| `--mt-model 600m\|1.3b` | `600m` | NLLB translation model size |
| `--speaker-threshold` | `0.55` | Voice similarity needed to count as the same speaker. Lower: fewer, larger speaker groups |
| `--vad-threshold` | `0.5` | Speech probability for voice activity detection |
| `--min-silence` | `0.5` | Pause in seconds that ends a phrase |
| `--max-segment` | `12` | Force a cut after this many seconds of continuous speech |
| `--threads` | `0` (auto) | CPU threads for the models |

## Audio setup

- **`Me`** is the Windows default microphone. **The call side** is the Windows default output device (speakers or
  headphones), recorded with WASAPI loopback, Windows' built-in way to record what a device plays. This is the Windows
  equivalent of BlackHole on macOS, except that no virtual audio driver and no Multi-Output Device are needed: you
  keep hearing the call as usual.
- The startup lines show which devices are recorded:
  ```
  Me    <- Microphone Array (Realtek(R) Au
  Call  <- Speakers (Realtek(R) Audio) [Loopback]
  ```
  To use other devices, set them as the Windows defaults (Sound settings) before starting.
- **For a Zoom / Google Meet call:**
  1. Plug in headphones *before* starting the program (the default output device is picked at startup).
  2. Leave the call app's speaker setting on the system default ("Same as system").
  3. The call app plays the other participants to that device, so they appear as `Speaker N`. It doesn't play your
     own voice back, so you appear only as `Me`.
- **Use headphones.** The call app's echo cancellation only cleans its own copy of the microphone, not ours. Through
  speakers, the other participants can reach the microphone and be printed a second time as `Me`.
- Everything the output device plays is captured, so mute notification sounds and close other audio (videos, music).
- Testing without other people: play Armenian recordings on the computer. They are captured exactly like a call.

## Architecture

```
mic ───────► MicStream ──────► Segmenter (VAD) ─┐
                                                ├─► queue ─► worker: ASR ─► speaker ID ─► translation ─► print
output ────► LoopbackStream ─► Segmenter (VAD) ─┘                       (call side only)
(loopback)
```

- **Capture** (`hyen/audio.py`): one thread per source. `MicStream` uses sounddevice. `LoopbackStream` uses
  PyAudioWPatch, downmixes the device's native format (usually 48 kHz stereo) to 16 kHz mono with soxr, and fills gaps
  with silence: WASAPI delivers no data while nothing plays, and without the fill the VAD would never see the pause
  that ends a phrase.
- **Segmentation** (`hyen/vad.py`): Silero VAD cuts each stream into phrases at pauses. Phrases are re-cut from a
  rolling buffer with 0.3 s padding, because Silero tends to clip the first syllable.
- **Worker** (`hyen/main.py`): the main thread takes phrases from both sources in the order they end and processes
  them one at a time, because all models share the same 4 CPU cores. Phrases where ASR finds no words (noise, coughs)
  are dropped before speaker identification, so they never create a speaker.
- **ASR** (`hyen/asr.py`), **translation** (`hyen/translate.py`), **speaker identification** (`hyen/speakers.py`):
  each behind a small interface (`transcribe(audio) -> str`, `translate(text) -> str`, `identify(audio) -> label`), so
  models can be swapped independently.

## Models and why

| Stage | Model | Runtime | Licence |
|---|---|---|---|
| ASR | [nvidia/stt_hy_fastconformer_hybrid_large_pc](https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc), CTC decoder ([ONNX export](https://huggingface.co/OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx)) | onnx-asr / ONNX Runtime | CC-BY-4.0 |
| Translation | [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M), int8 ([CT2 conversion](https://huggingface.co/pulkitchowdry/nllb-600m-ct2-int8)); 1.3B optional ([CT2](https://huggingface.co/michaelfeil/ct2fast-nllb-200-distilled-1.3B)) | CTranslate2 | **CC-BY-NC-4.0** (non-commercial) |
| VAD | [Silero VAD](https://github.com/snakers4/silero-vad) | sherpa-onnx | MIT |
| Speaker embeddings | [3D-Speaker CAM++](https://github.com/modelscope/3D-Speaker) zh+en "common advanced" ([sherpa-onnx export](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models)) | sherpa-onnx | see model page |

### Speech recognition

Armenian is low-resource, and model cards are optimistic. I chose by the independent
[ArmBench-ASR](https://metric-ai-armbench-asr.static.hf.space/) leaderboard (WER, lower is better). Cloud models
(Gemini, ElevenLabs, …) score best but are not allowed here. Among open models:

| Model | Overall WER | Conversational ("Movies") WER | On this CPU |
|---|---|---|---|
| **NVIDIA FastConformer hy (chosen)** | **19.9%** | **61%** | 0.2–0.4 s per phrase |
| SeamlessM4T v2 large | 28.9% | 80% | too slow (2.3B params) |
| Chillarmo whisper-large-v3-turbo-armenian | 33.0% | 82% | 15–17 s per phrase |
| Meta Omnilingual ASR (300M–3B) | 38–51% | 79–92% | slow |
| MMS-1B | 47.5% | 83% | – |
| stock Whisper large-v3 | 65.1% | 106% | – |

FastConformer is both the most accurate open model and fast enough by a wide margin. The Whisper fine-tune is kept
behind `--asr-model whisper` because it was the obvious alternative and I measured it: it always encodes a 30 s
window and decodes token by token, so live latency grew from 17 s to 61 s within 6 phrases, and it invented a long
sentence from 3 s of noise. [BuzzASR/armenian](https://huggingface.co/BuzzASR/armenian) (a Whisper-large-v3 fine-tune)
reports very low WER on read speech but isn't on ArmBench and is even larger, so it can't run live here either.

### Translation

NLLB-200 is a dedicated translation model covering Armenian, small enough for CPU when quantised to int8 with
CTranslate2 (0.4–1.6 s per sentence for 600M). The 1.3B version is one flag away (`--mt-model 1.3b`) for better
quality at higher latency. Alternatives considered:

- **NLLB 3.3B, MADLAD-400 3B:** likely better, but several times slower; would eat most of the 5 s budget on this CPU.
- **LLMs (TranslateGemma 4B, Armenian-adapted Gemma):** more fluent and more tolerant of messy ASR output, but token
  by token generation on a laptop CPU is risky for the 5 s budget, and there were reports of TranslateGemma inserting
  and repeating text in Armenian.
- **End-to-end speech translation (SeamlessM4T v2):** one model instead of two, but its Armenian recognition is
  clearly worse than FastConformer and it is too large for live use here.

### Voice activity detection

Silero VAD, the standard small VAD, run through sherpa-onnx (the `silero-vad` pip package needs PyTorch). Without VAD
the first prototype cut fixed 5 s chunks, which split words, and the ASR made up short phrases from pure noise.

### Speaker identification

No enrollment: the tracker starts empty and learns voices during the call. Each call-side phrase is turned into a
voiceprint (a 192-number speaker embedding). It is compared (cosine similarity) with the average voiceprint of every
speaker heard so far: if the best match is ≥ 0.55 it gets that speaker's label (and their average is updated),
otherwise it becomes a new `Speaker N`. Cost: 0.05–0.17 s per phrase.

The model was chosen by measurement on 72 Common Voice clips (12 speakers × 6 clips, cut by our VAD):

| Speaker model (sherpa-onnx exports) | Same speaker, median similarity | Different speakers, median / 95th pct |
|---|---|---|
| **3D-Speaker CAM++ zh+en "common advanced"** (chosen, 28 MB) | 0.77 | 0.24 / 0.43 |
| 3D-Speaker CAM++ VoxCeleb (English) | 0.63 | 0.42 / 0.85 |
| WeSpeaker ResNet34 VoxCeleb (English) | 0.84 | 0.65 / 0.82 |

The two models trained on VoxCeleb (~7k mostly English speakers) barely separate Armenian speakers; the model trained
on ~200k speakers does. pyannote was not used: its pipeline needs PyTorch and gated downloads, works on whole files
rather than live, and its embedding model is the WeSpeaker ResNet34 above.

The threshold was chosen by replaying 300 simulated calls (2–4 random speakers, shuffled turns, empty tracker at the
start): at 0.55, ~95% of lines get the right label. The typical error is one unusual phrase getting an extra label of
its own. A deliberately bad first phrase (noise at 5 dB SNR) still gave 92%: it becomes a one-off extra label, and the
person's later phrases form their real speaker. A minimum phrase length for new speakers and merging of near-duplicate
speakers were tried and dropped for simplicity (no measurable gain). Live test with 3 speakers and 12 phrases played
through the speakers: 11/12 correct; the miss was a new female speaker's first phrase given to the other female speaker.

## How it was tested

The laptop microphone does not reliably pick up its own speakers, so the call side was tested by playing Armenian
Common Voice clips through the speakers: WASAPI loopback captures them digitally, exactly like call audio. Results:

| Test | Result |
|---|---|
| 4 clips, call side | correct lines, lat 1.4–2.4 s; transcripts near-perfect |
| 20 s with nothing playing | no false lines |
| Clips with real gaps (nothing playing in between) | every phrase still ends and prints; timestamps match playback |
| 3 speakers × 4 phrases, shuffled | 11/12 speaker labels right, lat 1.3–2.7 s |
| Whisper-turbo vs FastConformer, live | Whisper falls behind (17 → 61 s); FastConformer 1.3–1.5 s |

## Known limitations

- **Recognition of live conversation is much worse than of test recordings.** Clean read speech (Common Voice) is
  transcribed almost perfectly, but in a real meeting test both the Armenian transcript and the English translation
  were poor. This matches ArmBench, where even the best open model gets ~61% of words wrong on conversational speech.
  Translation can't recover from recognition errors. Possible contributors not yet separated: spontaneous speech,
  Windows microphone "enhancements", microphone distance, call-app audio compression, phrases cut at short pauses.
- **Speakers:** two people talking without a 0.5 s pause in between, or at the same time, end up in one phrase with
  one label. Similar voices can share a label, and an unusual or very short phrase can get an extra label. Printed
  lines are never relabelled. The threshold was tuned on read speech; call audio may need a different value
  (`--speaker-threshold`).
- **Devices:** always the Windows default microphone and output device; there is no device list or device flags yet
  (the brief asks for them). Switching the output device while running (e.g. plugging in headphones) is not followed.
- **Segmentation:** phrases are cut at pauses of 0.5 s or more; speech with no pause for 12 s is force-cut, which can
  split a word. Silero VAD sometimes still clips a quiet first syllable.
- **Throughput:** phrases are processed one at a time. If many phrases end at once, later ones wait (visible in `lat`).

## What I would improve with more time

1. **Record and replay:** save the raw audio of real calls locally and replay it through the pipeline, to find which
   stage fails on live speech and to compare models on real call audio instead of read speech.
2. **Evaluation harness:** WER/CER for ASR and chrF for translation on FLEURS Armenian (which has English references),
   plus latency percentiles, to compare NLLB 600M / 1.3B / 3.3B and FastConformer's second (RNNT) decoder, which
   should be about 1 point better in WER.
3. **Device selection:** `--list-devices`, `--mic`, `--output` flags.
4. **Speaker robustness:** compare other embedding models (ERes2NetV2, NVIDIA TitaNet) and tune the threshold on
   real call audio.
5. Drop junk ASR outputs (one or two letters) that come from echo or noise.
6. Implement merging of embeddings in the case when the same person has more then one embedding
