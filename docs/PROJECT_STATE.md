# Project state (last updated 2026-11-01, session 2, pre-submission)

## Target (from the brief)
- Capture **mic + system audio at the same time**; let the user pick devices (list or flags)
- Armenian ASR → English translation per segment
- Speakers: mic = **"Me"**; system audio = **Speaker 1, Speaker 2…**, stable for the whole session
- Live terminal lines with time, speaker, HY original, EN translation; **≤5 s** from phrase end
- Local models only, Python, runs on this laptop (live demo with ≥2 people on the call side)
- Out of scope: GUI, installer, echo handling, naming speakers, saving transcripts, other input languages
- Deliverables: Git repo, README (setup incl. audio devices, models + alternatives + why, architecture, limitations),
  `chats/` with every AI session exported as separate .md, no weights/audio/keys
- Evaluated on: working method, steering the AI (not following it), reasoned decisions, live result, code structure, README,
  honesty about limits
- Open concern: the brief says to use **Claude Cowork** ("any other AI assistant is not allowed"). Session 1 used Claude Code.
  The user should confirm with the reviewers or switch.

## Done
1. **Research & model selection** (details below)
2. **Phase 1 prototype**: mic → fixed 5 s chunks → ASR → MT → terminal
3. **Phase 2a: VAD segmentation**: Silero VAD (sherpa-onnx) replaced the fixed chunks; 0.3 s padding against clipped
   first syllables; output shows `lat` = phrase end → printed line
4. **Whisper as an optional ASR backend** (`--asr-model whisper`) for comparison
5. **System audio + two streams (session 2)**: `LoopbackStream` (PyAudioWPatch WASAPI loopback of the *default* output
   device, downmix + soxr resample to 16 kHz, silence gap filling by wall clock because WASAPI sends nothing while
   nothing plays). `main.py`: one capture thread + Segmenter per source → shared queue → main thread is the single
   ASR/MT worker; labels `Me` / `Call`; one session timeline. Decided with the user: WASAPI is a local OS audio API
   (not a "cloud API"), it is the Windows equivalent of BlackHole; **no device selection for now** (keep it simple).
6. **Speaker identification (session 2)**: `hyen/speakers.py` `SpeakerTracker` (no enrollment, starts empty): CAM++
   embedding per Call phrase → cosine vs running speaker averages; ≥ 0.55 assign, else new `Speaker N`. Runs after
   ASR, so empty-text segments never reach it. User raised: cost (measured 0.05–0.17 s), locality (local model file),
   cold start / bad first phrase. A min-length rule and merging were built, then **removed at the user's request
   (keep it simple)**; the simulation showed no gain from them (simple: 95.3% lines right at 0.55, same as with merging). See the "Speaker study" below and the README section.

7. **Final README (2026-11-01)**: rewritten for submission (setup, options table, audio setup, architecture diagram,
   models + alternatives with ArmBench numbers, speaker study, tests, limitations, improvements). States honestly that
   the user's real meeting test gave poor ASR and translation.

## Measurements so far (i5-8265U, CPU only)
| What | Result |
|---|---|
| NLLB-600M int8 translation | 0.4–0.9 s per sentence, good quality on test sentences |
| FastConformer ASR | ~0.2 s per 6–7 s clip; near-perfect on clean Common Voice clips |
| Whisper-turbo-armenian (CT2 int8) | 15–17 s per 6–7 s clip (thread count irrelevant), live latency grows 17 → 61 s; made up a long sentence from 3 s of noise |
| Full pipeline (FastConformer + VAD + NLLB-600M), clips fed in real time | **lat 1.3–1.5 s**, one line per sentence, no false segments from 30 s of noise |
| Loopback: 4 CV clips played through speakers (session 2) | `Call` lines, **lat 1.4–2.4 s**, timestamps match playback; 20 s idle → no false lines; real gaps (nothing playing) still end phrases |
| Speaker embedding (CAM++ zh+en), per phrase | 122 ms median on 1 thread, 64 ms on 4; live 0.05–0.17 s |
| Speaker live test, 3 CV speakers × 4 phrases via loopback | 11/12 labels right (miss = first phrase of 2nd female voice); lat 1.3–2.7 s |
| ASR on noise without VAD | made up short phrases ("Այդ էին") → VAD/silence handling is needed |

## Known problems / open questions
- **Live mic transcription quality is poor** (user's own test), though clean clips are near-perfect. Hypotheses, not yet tested:
  (a) Realtek mic processing (echo cancellation/noise suppression, "Audio enhancements") distorts speech, (b) low/distant mic level,
  (c) spontaneous vs read speech (the model's real-world WER is ~20% on ArmBench). Suggested first check: turn off mic enhancements
  in Windows Sound settings; record a live sample and replay it through the pipeline.
- Forced cut at 12 s (`--max-segment`) not yet verified on a real long monologue.
- The user's re-test of the VAD version live: pending.
- **User's real meeting test (2026-11-01): both ASR and translation poor.** No output sample shared yet. ArmBench "Movies"
  (conversational) WER: FastConformer 61%, every other open model worse → a model swap won't fix ASR; record & replay needed.
- Pre-submission gaps: `chats/` folder missing; device selection (brief requirement) not done; `/docs` is gitignored, so
  PROJECT_STATE.md is not in the repo although the committed CLAUDE.md points to it.
- Not yet tested: Ctrl+C shutdown with both streams (tests killed the process), a real Zoom/Meet call.
- The laptop mic DOES pick up loud speaker playback partly: the 3-speaker test produced ~9 junk `Me` lines
  (single letters "Կ։", "Հ։"). Headphones for the demo; possible later fix: drop ASR outputs with < 2 letters.
- Speaker threshold tuned on Common Voice read speech; needs a check on a real Zoom/Meet call (codec).

## Model decisions (research 2026-10-25)
- **ASR: `nvidia/stt_hy_fastconformer_hybrid_large_pc`** via ONNX export `OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx`
  (CTC head only; the RNNT head is ~1 pt better WER but isn't in the export). ~115M params, punctuation, CC-BY-4.0.
  Why: best open-weight model on the independent **ArmBench-ASR** leaderboard (overall WER 19.9%), vs SeamlessM4T-v2 28.9%,
  chillarmo whisper-turbo-armenian 33.0%, MMS 47.5%, stock whisper-large-v3 65.1%. Model-card WERs (15%, 2.4%) don't hold up there.
- **ASR alternative: `Chillarmo/whisper-large-v3-turbo-armenian`** via the CT2 conversion `hurricup/whisper-large-v3-turbo-armenian-ct2`
  (float16, int8 on load, no torch needed). Too slow on this CPU; kept for comparison only.
- **MT: NLLB-200 distilled**, CTranslate2 int8. Default 600M (`pulkitchowdry/nllb-600m-ct2-int8`), option 1.3B
  (`michaelfeil/ct2fast-nllb-200-distilled-1.3B`). The bundled tokenizer gives a false "incorrect regex" warning; its token IDs were
  verified identical to `facebook/nllb-200-distilled-600M` (silenced via `TRANSFORMERS_VERBOSITY=error`). NLLB is CC-BY-NC → state it in the README.
  Rejected: TranslateGemma-4B (Armenian insertion/repetition reports; too slow on CPU), MADLAD-3B (slower), general LLMs.
- **VAD: Silero** via `sherpa-onnx` (pip silero-vad needs torch). Model `silero_vad.onnx` from the sherpa-onnx GitHub release.
- **Speakers: voice embeddings + our own online clustering**, sherpa-onnx `SpeakerEmbeddingExtractor` with
  **`3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx`** (192-dim, 28 MB). Speaker study (session 2, 72 CV clips,
  12 speakers × 6): same-speaker median cosine 0.77, different 0.24 (95th pct 0.43). The planned English VoxCeleb models
  separated badly on Armenian (CAM++ en: 0.63 vs 0.42; WeSpeaker ResNet34: 0.84 vs 0.65) → rejected. 300 simulated calls
  (2–4 speakers, cold start): threshold 0.55 → ~95% lines right (noisy first phrase: 92%); main residual error = one odd
  phrase gets an extra label. Merging at the assignment threshold wrongly merged people in 8–26% of calls. Scripts: session-2
  scratchpad (`embed_study*.py`, `simulate_*.py`), not in the repo. One embedding per VAD segment → cosine similarity to running centroids → assign or create
  "Speaker N"; segments < ~1 s don't create new speakers. Rejected diart/pyannote (torch, gated models, heavy on CPU).

## Next steps (agreed order, model-independent work first)
1. User re-tests live; investigate the poor live mic quality (see hypotheses above)
2. **Record & replay dev tooling** (save raw session audio to a gitignored file, feed it back for repeatable tests) + timing log (p50/p95 latency)
3. ~~System audio capture~~ + ~~two-stream pipeline~~ done (session 2); still open: device selection flags
   (`--list-devices`, `--mic`, `--loopback`; the brief asks for it), real call test with the phone as 2nd participant
5. ~~Speaker identification~~ done (session 2); still open: check on a real call
6. **Evaluation harness** (`bench/`): FLEURS hy_am (its `id` joins to `en_us` → English references for a cascade ASR→MT score) and
   Common Voice 20; WER/CER (jiwer), chrF/BLEU (sacrebleu), latency p50/p95; results in `bench/RESULTS.md` → README
7. Model revisit if needed (NLLB 1.3B vs 600M, FastConformer RNNT head), final README, export chats

## Key references
- ArmBench-ASR leaderboard: https://metric-ai-armbench-asr.static.hf.space/
- FastConformer hy model card: https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc · onnx-asr: https://github.com/istupakov/onnx-asr
- faster-whisper: https://github.com/SYSTRAN/faster-whisper · CTranslate2: https://opennmt.net/CTranslate2/
- NLLB paper: https://arxiv.org/abs/2207.04672
- sherpa-onnx: https://github.com/k2-fsa/sherpa-onnx (VAD example: python-api-examples/vad-microphone.py)
- The full research plan with the benchmark design: `C:\Users\Admin\.claude\plans\look-at-the-word-cozy-map.md`
