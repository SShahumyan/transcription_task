# Live Armenian → English transcription (prototype)

Status: **phase 1 prototype**. It listens to the default microphone, cuts the audio into fixed-length chunks,
transcribes each chunk in Armenian and translates it to English. Everything runs locally on CPU.

## Setup (Windows, Python 3.11+)

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Models are downloaded from Hugging Face on first run (~1 GB) into the HF cache. Nothing is stored in the repo.

## Run

```
venv\Scripts\python -m hyen.main
```

Options: `--chunk-seconds 5`, `--mt-model 600m|1.3b`, `--threads 0`, `--silence-rms 0.005`.
Use Windows Terminal; the classic console may not render Armenian script.

Output, one line per chunk:

```
[00:00:15] Me  HY: Բարև, ինչպե՞ս ես։  EN: Hi, how are you?   (asr 0.20s, mt 0.37s, behind 0.5s)
```

`behind` is audio still waiting to be processed. If it keeps growing, processing is slower than real time.

## Models (current)

| Stage | Model | Runtime |
|---|---|---|
| ASR | [nvidia/stt_hy_fastconformer_hybrid_large_pc](https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc) (CTC, via [ONNX export](https://huggingface.co/OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx)) | onnx-asr / ONNX Runtime |
| MT | NLLB-200 distilled 600M, int8 ([CT2 conversion](https://huggingface.co/pulkitchowdry/nllb-600m-ct2-int8)); 1.3B optional | CTranslate2 |

Model choices, alternatives and benchmarks will be documented here in phase 2. Note: NLLB is licensed CC-BY-NC.

## Prototype limitations

- Fixed chunks cut words and sentences at the boundaries, which hurts both ASR and translation.
- Latency is up to one chunk length plus processing time (~0.5 s measured), because there is no end-of-phrase detection yet.
- Microphone only, single speaker ("Me"); no system audio and no device selection.
- Near-silent chunks are skipped by a simple loudness threshold; without it the ASR invents short phrases from room noise.
