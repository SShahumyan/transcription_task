# Live Armenian → English transcription (prototype)

Status: **prototype**. It listens to the default microphone ("Me") and to what the computer plays, e.g. the other side
of a video call, where people are told apart as "Speaker 1", "Speaker 2", …). Both streams are split into phrases at pauses (voice activity detection); each phrase is
transcribed in Armenian and translated to English. Everything runs locally on CPU; no audio or text leaves the machine.

## Setup (Windows, Python 3.11+)

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Models are downloaded on first run (~1 GB) into the Hugging Face cache, and the VAD model (~2 MB) into `models/`.
Nothing is stored in the repo.

## Run

```
venv\Scripts\python -m hyen.main
```

Options: `--asr-model fastconformer|whisper`, `--mt-model 600m|1.3b`, `--threads 0`, `--vad-threshold 0.5`, `--min-silence 0.5` (pause that ends a
phrase), `--max-segment 12` (force a cut after this many seconds of continuous speech), `--speaker-threshold 0.55`
(voice similarity to count as the same speaker; lower = fewer, larger speaker groups).
Use Windows Terminal; the classic console may not render Armenian script.

## Audio setup

- **Me** = the Windows default microphone. **Call** = the Windows default output device (speakers/headphones),
  recorded with WASAPI loopback, Windows' built-in way to record what a device plays. No virtual audio driver is
  needed (the Windows equivalent of BlackHole on macOS), and you still hear the call as usual.
- The startup lines show which devices are used:
  ```
  Me    <- Microphone Array (Realtek(R) Au
  Call  <- Speakers (Realtek(R) Audio) [Loopback]
  ```
- **For a Zoom / Google Meet call:** plug in headphones *before* starting the program (the default output device is
  picked at startup) and leave the call app's speaker setting on the system default. The call app plays the other
  participants to that device, so they appear as `Speaker N`; it doesn't play your own voice back, so you appear only as `Me`.
- **Use headphones.** The call app's echo cancellation only cleans its own copy of the microphone, not ours; through
  speakers, the other participants can reach the microphone and be printed a second time as `Me`.
- Everything the output device plays is captured, so mute notification sounds and close other audio (videos, music).
- Testing without other people: play Armenian recordings on the computer; they are captured exactly like a call.

Output, one line per phrase:

```
[00:00:24] Speaker 2  HY: Արժանապատվություն հասկացությունը պատմական տարբեր ժամամանակահատվածներում տարբեր բովանդակություն է ունեցել։  EN: The concept of dignity has had different meanings at different times in history.   (asr 0.29s, spk 0.10s, mt 0.88s, lat 1.9s)
```

The timestamp is when the phrase ended, since the program started. `lat` is the time from the end of the phrase to the
printed line (the brief's limit is 5 s). Measured 1.3–2.7 s on Common Voice clips played through the speakers.

How it works: each source has its own capture thread and VAD; finished phrases from both go into one queue, and a
single worker runs ASR → (call side only) speaker identification → translation → print, one phrase at a time, since
all models share the CPU.

## Speaker identification

No enrollment: the tracker starts empty and learns voices during the call. Each call-side phrase is turned into a
voiceprint (a 192-number speaker embedding) by a small local model. It is compared (cosine similarity) with the average
voiceprint of every speaker heard so far: ≥ 0.55 → that speaker (and their average is updated), otherwise a new
`Speaker N`. Phrases where ASR finds no words (noise, coughs) are not printed and never reach this step. Cost:
0.05–0.17 s per phrase.

Model choice, measured on 72 Common Voice clips (12 speakers × 6, cut by our VAD):

| Speaker model (sherpa-onnx exports) | Same speaker, median similarity | Different speakers, median / 95th pct |
|---|---|---|
| **3D-Speaker CAM++ zh+en "common advanced"** (chosen, 28 MB) | 0.77 | 0.24 / 0.43 |
| 3D-Speaker CAM++ VoxCeleb (English) | 0.63 | 0.42 / 0.85 |
| WeSpeaker ResNet34 VoxCeleb (English) | 0.84 | 0.65 / 0.82 |

The two English VoxCeleb models barely separate these Armenian speakers; the zh+en model (trained on far more
speakers) does. The threshold was chosen by replaying 300 simulated calls (2–4 random speakers, shuffled turns, empty tracker at the
start): at 0.55, ~95% of lines get the right label; the typical error is one odd phrase getting an extra label of its
own. A deliberately bad first phrase (noise at 5 dB SNR) cost little (92% of lines right): it becomes a one-off extra
label and the person's later phrases form their real speaker. Tried and dropped for simplicity: a minimum phrase
length for creating speakers and merging of near-duplicate speakers (no measurable gain in the simulation). Live test (3 speakers, 12 phrases through the
speakers): 11/12 correct; the miss was a new female speaker's first phrase given to the other female speaker.

## Models (current)

| Stage | Model | Runtime |
|---|---|---|
| ASR | [nvidia/stt_hy_fastconformer_hybrid_large_pc](https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc) (CTC, via [ONNX export](https://huggingface.co/OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx)) | onnx-asr / ONNX Runtime |
| MT | NLLB-200 distilled 600M, int8 ([CT2 conversion](https://huggingface.co/pulkitchowdry/nllb-600m-ct2-int8)); 1.3B optional | CTranslate2 |
| VAD | [Silero VAD](https://github.com/snakers4/silero-vad) | sherpa-onnx |
| Speaker embeddings | [3D-Speaker CAM++](https://github.com/modelscope/3D-Speaker) zh+en common advanced ([sherpa-onnx export](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models)) | sherpa-onnx |
| ASR (alternative, `--asr-model whisper`) | [Chillarmo/whisper-large-v3-turbo-armenian](https://huggingface.co/Chillarmo/whisper-large-v3-turbo-armenian) ([CT2 conversion](https://huggingface.co/hurricup/whisper-large-v3-turbo-armenian-ct2), int8 on load) | faster-whisper |

### ASR comparison (first measurements, Intel i5-8265U, 4 cores, CPU only)

| | FastConformer (default) | Whisper-turbo Armenian |
|---|---|---|
| Time to transcribe a 6–7 s clip | 0.2 s | 15–17 s (thread count makes no difference) |
| Phrase end → printed line, live pipeline | 1.3–1.5 s, stable | 17 s rising to 61 s after 6 phrases (falls behind) |
| 2 Common Voice clips | 1 wrong word | 2 wrong words in one clip, 1 in the other |
| 3 s of background noise | short made-up phrase (2 words) | long made-up sentence, took 30 s |
| [ArmBench-ASR](https://metric-ai-armbench-asr.static.hf.space/) overall WER | 19.9% | 33.0% |

Whisper always encodes a 30 s window and decodes token by token, which this CPU can't do in real time. It's kept
as an option for comparison only. Two clips are not a benchmark; a larger evaluation is planned.

Model choices, alternatives and benchmarks will be documented here in phase 2. Note: NLLB is licensed CC-BY-NC.

## Prototype limitations

- Phrases are cut at pauses of 0.5 s or longer. Speech with no pause for 12 s is force-cut, which can split a word.
- Silero VAD tends to clip the first syllable, so each phrase is padded with 0.3 s of audio on both sides. A quiet
  first syllable is sometimes still lost.
- Speakers: two people talking without a 0.5 s pause in between, or at the same time, end up in one phrase with one
  label. Similar voices can share a label, and an unusual or very short phrase can get an extra label; printed lines
  are never relabelled. The threshold was tuned on read speech (Common Voice); Zoom/Meet audio compression may shift it
  (`--speaker-threshold`).
- Always the default microphone and output device; no device selection. Switching the output device while running
  (e.g. plugging in headphones) is not followed.
- Through speakers instead of headphones, the call audio leaks into the mic and produces junk `Me` lines (seen in
  tests: single letters like "Կ։"). Echo handling is out of scope; use headphones.
- Phrases from both sources are processed one at a time; if many phrases end at once, later ones wait (visible in `lat`).
- Transcription quality on live microphone speech is noticeably worse than on clean test recordings (not yet investigated).
