# Model Experiment Log — Elcoria Healthcare PoC

Running record of every model we have tried in each pipeline stage, with what worked, what failed, and why. Append new entries at the top of each stage section.

Pipeline stages: **VAD → ASR (Hungarian) → Emotion → Fusion (LLM)**.

Hardware reference: NVIDIA RTX 2000 Ada (8 GB VRAM), Windows 11, Python 3.13, PyTorch 2.6.0+cu124, cuDNN disabled via `torch.backends.cudnn.enabled = False` (system-wide cuDNN symbol mismatch).

---

## ASR — Hungarian speech-to-text

### ✅ `sarpba/whisper-large-v3-hu-turbo` (CURRENT — `configs/turbo.yaml`)
- **Status**: in production use
- **Verdict**: Best Hungarian transcription we have tried. Noticeably faster decoder than non-turbo large-v3-hu. Output is good but not perfect — occasional word substitutions on medical vocabulary.
- **Runtime**: ~1 s per utterance on RTX 2000 Ada, fp16, short-form (no `chunk_length_s`).
- **Loader**: `HuggingFaceWhisperASR` (transformers `AutoModelForSpeechSeq2Seq` + `AutoProcessor`, `local_files_only=True`).
- **generate_kwargs**: `language="hu"`, `task="transcribe"`, `max_new_tokens=96`, `no_repeat_ngram_size=3`.

### ❌ `openai/whisper-small` (fine-tuned for HU) — DELETED
- **Status**: removed; `configs/lightweight.yaml` deleted.
- **Verdict**: "Absolutely useless" on real Hungarian doctor-patient speech. Too many substitution errors to be usable.
- **Lesson**: Don't bother with small-class models for clinical Hungarian. The size/quality tradeoff is wrong for this domain.

### Known failure modes across Whisper variants
- Forcing `chunk_length_s=30` pads every utterance to 30 s and triggers heavy hallucination on short clips. **Removed.** Use short-form mode.
- Without `no_repeat_ngram_size`, long pauses produced repetition loops ("a térdem a térdem a térdem…").
- Without audio normalization (target RMS 0.1, max gain 12×, peak 0.99), quiet mic input gave empty or nonsense output.

### To try next (ASR)
- Convert `whisper-large-v3-hu` to CTranslate2 format and run via `faster-whisper` for further speed-up.
- Domain-adapted fine-tune on Hungarian medical vocabulary if we can collect a dataset.

---

## Emotion — patient mood from audio

### ✅ `AcousticBiomarkersEmotion` (parselmouth/Praat) — CURRENT
- **Status**: in production use as of latest iteration.
- **Approach**: language-independent prosodic features (pitch mean/std, intensity, jitter, shimmer, voiced ratio) → heuristic mapping to emotion scores. Rolling personal speaker baseline calibrated over first ~10 utterances (alpha = 1/min(n, 10)).
- **Verdict**: Designed for Hungarian-agnostic operation. Whether the rule thresholds (arousal cutoffs at ±0.6/−0.4, jitter > 0.02, shimmer > 0.10) match real users still needs validation.
- **Why we picked it**: prior wav2vec2 SER was English-trained and produced near-uniform output on Hungarian. Acoustic biomarkers sidestep language entirely.

### ❌ `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition`
- **Status**: replaced.
- **Verdict**: Produced near-uniform scores on Hungarian audio (e.g. `surprised 14% / neutral 13% / anxious 13%` — essentially 1/8 across all classes). The model was trained on English emotional speech (RAVDESS / similar) and does not transfer to Hungarian prosody/phonetics.
- **Fix attempts that didn't help**:
  - Using `AutoFeatureExtractor` instead of `AutoProcessor` — solved a load-time crash but did not improve outputs.
  - Removing wrong `calm → anxious` alias (these are opposites).
  - Low-confidence guard (top class < 0.20 → force `neutral`) — masked the problem but didn't solve it.
- **Lesson**: English-trained SER heads do **not** generalize to Hungarian. Don't try another English XLSR-based SER and expect it to work; either fine-tune on Hungarian or go acoustic-feature based.

### To try next (Emotion)
- Fine-tune a SER head on Hungarian emotional speech (if/when we get a labeled dataset).
- Search for any community-released Hungarian or multilingual SER model that has been validated on non-English data.
- Tune the AcousticBiomarkersEmotion thresholds against real recorded sessions once we have telemetry.

---

## Fusion — clarification-question LLM

### ✅ `llama3.2:3b` (Ollama, 4-bit quantized) — CURRENT
- **Status**: in production use.
- **VRAM**: ~2.8 GB → fits 100 % on GPU alongside Whisper-turbo. **This is the deciding factor on 8 GB cards.**
- **Verdict**: Hungarian output quality is acceptable for 3-question clarification prompts when paired with a strict prompt + few-shot example. Generation runs ~100 % GPU.
- **Settings**: `temperature=0.2`, `num_predict=256`, `keep_alive=-1` (resident in VRAM), pre-warmed at startup with an empty prompt.

### ⚠️ `llama3.1:8b` (Ollama)
- **Status**: tried, abandoned for VRAM reasons.
- **VRAM**: ~5.9 GB → with Whisper-turbo loaded, spilled to CPU. Result: generation ran ~25 % CPU / 75 % GPU and was visibly slow.
- **Quality**: Hungarian output was modestly better than 3.2:3b but **not enough to justify the slowdown** on this hardware.
- **Lesson**: 8 B-class LLMs do not coexist with a fp16 Whisper-large on 8 GB. Either go 3 B or quantize harder.

### ❌ `qwen2.5:7b` (Ollama)
- **Status**: tried, abandoned.
- **Verdict**: Hungarian output noticeably worse than both Llama variants. Generated awkward, non-idiomatic phrasing and made-up clinical-sounding compound words ("fájdalomszindróma", "kórszak", "fenomenológia", "erejesség"). Banned those tokens in the prompt as a workaround but the underlying language ability wasn't there.
- **Lesson**: Don't reach for Qwen for Hungarian generation. Llama family is meaningfully better on this language.

### ❌ `TemplateFusion` (rule-based fallback)
- **Status**: superseded by Ollama; kept in code as a fallback path only.
- **Verdict**: Always returned the same 3 questions per emotion bucket — completely useless for a real conversation. Only viable if Ollama is unreachable.

### Prompt engineering notes (apply to whichever LLM we use)
- **Hard cap at 3 questions.** Without this, models drift to 5–10 and the last ones get silly.
- **Max 10–12 words per question.** Long questions read like a textbook, not a doctor.
- **Few-shot with a concrete Hungarian example** is the single biggest quality lever.
- **Explicit ban list** for invented compound words (especially with Qwen, less needed with Llama).
- **Ask-back path**: when transcript looks unusable (empty / <3 chars / single word / repetition collapse / common hallucinations), don't generate 3 empty questions — ask the patient to repeat. Implemented via `_looks_unusable()` heuristic in the orchestrator.
- See [prompts/doctor_questions_hu.txt](prompts/doctor_questions_hu.txt) for the live prompt.

### To try next (Fusion)
- `gemma2:2b` or `phi-3.5-mini` — see if either matches Llama 3.2:3b Hungarian quality at lower VRAM.
- A Hungarian-specific fine-tune of Llama 3.2:3b if one becomes available.

---

## VAD — voice activity detection

### ✅ `EnergyVAD` (custom, energy threshold) — CURRENT
- **Status**: in production use.
- **Settings**: `threshold_db=-40`, `min_silence_ms=600`, `frame_ms=30`.
- **Verdict**: Works well enough for a single-speaker mic input in a quiet room. Cheap, deterministic, no model load.

### ❌ `SileroVAD`
- **Status**: tried, abandoned.
- **Failure**: torch.hub local clone path resolution broke (`'snakers4/silero-vad\\hubconf.py'` not found). Could be fixed but EnergyVAD was already good enough — not worth the dependency.

### Known issue (any VAD)
- A subsequent session sometimes records silent audio (RMS=0.00000) — appears to be a browser/AudioContext re-init issue, not a VAD problem. Deferred.

---

## Cross-cutting infrastructure decisions

### Audio capture (browser)
- **Switched from**: `MediaRecorder` → WebM/Opus chunks → server-side PyAV decode.
- **Switched to**: `AudioContext` + `ScriptProcessorNode` (4096 buffer, 16 kHz) → raw Float32 PCM → WebSocket binary frames.
- **Reason**: MediaRecorder chunks lack the container header on the wire; server got hundreds of "could not decode WebM" errors and never produced a transcript. Raw PCM eliminated the whole class of problems.

### GPU enablement
- Default Python 3.13 `pip install torch` installs the **CPU** wheel silently. We installed `torch==2.6.0+cu124` explicitly. cu121 had no 3.13 wheels.
- After enabling CUDA, hit `Could not load symbol cudnnGetLibConfig (error 127)` from a system-wide cuDNN clashing with torch's bundled one. Workaround applied in `src/main.py`:
  ```python
  import torch as _torch
  if _torch.cuda.is_available():
      _torch.backends.cudnn.enabled = False
  ```
  Whisper runs fine without cuDNN; the speed loss is negligible compared to what we gained from CUDA at all.

### Model preloading
- All ASR/Emotion/Fusion stacks for every config are loaded once at FastAPI startup into `_shared_stacks` (see [src/main.py](src/main.py)). Per-session orchestrator reuses them; only VAD is per-session. First WebSocket session is now fast.
- `/configs` endpoint filters to only return stacks that successfully preloaded — a misconfigured config is hidden from the UI rather than crashing on first use.

### Parallel utterance processing
- Question generation is launched as a background `asyncio.Task` so transcription can continue.
- When a new `speech_start` arrives, the pending utterance task is **cancelled** if not done. Otherwise the UI ended up with 10+ stale question sets stacking up.

---

## Quick reference: what NOT to retry without a new reason

| Item | Why it was rejected |
|---|---|
| `whisper-small` (any HU fine-tune) | Quality too low for clinical Hungarian. |
| English XLSR-based SER (e.g. `ehcalabres/...`) | Does not transfer to Hungarian; near-uniform output. |
| `qwen2.5:7b` for Hungarian generation | Worse Hungarian than Llama 3.2:3b at more than 2× the VRAM. |
| `llama3.1:8b` (on 8 GB VRAM) | Spills to CPU next to Whisper-turbo; slow with no quality justification. |
| `chunk_length_s=30` in Whisper pipeline | Triggers hallucinations on short utterances. |
| `MediaRecorder` for WebSocket streaming | Chunks lack container headers; un-decodable on the server. |
| `TemplateFusion` as primary path | Always same 3 questions per emotion bucket. Fallback only. |
| `SileroVAD` (current setup) | Local hub path issues; EnergyVAD already good enough. |
