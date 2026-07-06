/* Mic capture — getUserMedia → 16 kHz mono Float32 PCM frames.
 *
 * The backend's WS endpoint expects raw Float32 LE PCM at 16 kHz mono
 * (src/main.py :: _decode_pcm_f32). Browsers default to 44.1 / 48 kHz, so
 * we resample on the fly with a linear interpolator and emit ~250 ms frames
 * (4000 samples) over the provided onFrame callback.
 *
 * Public API:
 *   const mic = new MicCapture({ targetRate: 16000, frameMs: 250, onFrame });
 *   await mic.start();   // throws if permission denied / no audio device
 *   mic.stop();
 */

(function () {
  const TARGET_RATE = 16000;

  class MicCapture {
    constructor(opts = {}) {
      this.targetRate = opts.targetRate || TARGET_RATE;
      this.frameMs = opts.frameMs || 250;
      this.onFrame = opts.onFrame || (() => {});
      this.onLevel = opts.onLevel || (() => {});

      this.stream = null;
      this.audioCtx = null;
      this.source = null;
      this.processor = null;
      this._resampleAccum = [];
      this._frameSize = Math.round((this.targetRate * this.frameMs) / 1000);
      this._pending = new Float32Array(0);
    }

    async start() {
      if (this.stream) return;
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });

      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new Ctx();
      this.source = this.audioCtx.createMediaStreamSource(this.stream);

      // ScriptProcessorNode is deprecated but ships everywhere with no extra files.
      // Buffer size 4096 at 48 kHz = ~85 ms per callback — small enough latency, large
      // enough to keep callback overhead low. Migrate to AudioWorklet if needed.
      const bufferSize = 4096;
      this.processor = this.audioCtx.createScriptProcessor(bufferSize, 1, 1);
      this.processor.onaudioprocess = (ev) => this._handleAudio(ev);

      this.source.connect(this.processor);
      // Connect to destination so the node is kept alive; gain 0 keeps it silent.
      const sink = this.audioCtx.createGain();
      sink.gain.value = 0;
      this.processor.connect(sink);
      sink.connect(this.audioCtx.destination);
    }

    _handleAudio(ev) {
      const input = ev.inputBuffer.getChannelData(0);
      const srcRate = this.audioCtx.sampleRate;

      const resampled = srcRate === this.targetRate
        ? input
        : downsampleLinear(input, srcRate, this.targetRate);

      // Append to pending and emit fixed-size frames
      const merged = new Float32Array(this._pending.length + resampled.length);
      merged.set(this._pending, 0);
      merged.set(resampled, this._pending.length);

      let offset = 0;
      while (merged.length - offset >= this._frameSize) {
        const frame = merged.subarray(offset, offset + this._frameSize);
        // .slice() so the underlying buffer isn't reused on the next callback
        const out = new Float32Array(frame);
        this.onFrame(out);
        offset += this._frameSize;
      }
      this._pending = merged.slice(offset);

      // Report a coarse RMS level so the UI can drive the waveform
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);
      this.onLevel(rms);
    }

    stop() {
      if (this.processor) {
        try { this.processor.disconnect(); } catch (e) {}
        this.processor.onaudioprocess = null;
      }
      if (this.source) {
        try { this.source.disconnect(); } catch (e) {}
      }
      if (this.audioCtx) {
        try { this.audioCtx.close(); } catch (e) {}
      }
      if (this.stream) {
        this.stream.getTracks().forEach((t) => t.stop());
      }
      this.stream = null;
      this.audioCtx = null;
      this.source = null;
      this.processor = null;
      this._pending = new Float32Array(0);
    }
  }

  function downsampleLinear(input, srcRate, dstRate) {
    if (dstRate === srcRate) return input;
    const ratio = srcRate / dstRate;
    const outLen = Math.floor(input.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * ratio;
      const i0 = Math.floor(srcIdx);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = srcIdx - i0;
      out[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return out;
  }

  window.MicCapture = MicCapture;
})();
