/* Elcoria WebSocket client — implements the v1 message contract from INSTRUCTIONS.md §4.
 *
 * Inbound message types (server → client):
 *   session.start       → connection accepted, session is live
 *   transcript.partial  → in-progress utterance text
 *   transcript.final    → finalized utterance + emotion + biomarkers (fan-out join)
 *   intent.update       → fusion-stage prediction + recommended questions
 *   error               → server-side error
 *
 * Outbound:
 *   binary PCM frames (Float32 LE, 16 kHz mono)  — streamed mic audio
 *   { type: "session.end" } JSON                 — explicit end-of-stream
 *
 * Usage:
 *   const ws = new ElcoriaWebSocket({
 *     url: "ws://localhost:8000/v1/stream",
 *     config: "lightweight-cpu",
 *     onSessionStart: (sid) => …,
 *     onTranscriptPartial: (msg) => …,
 *     onTranscriptFinal:   (msg) => …,
 *     onIntentUpdate:      (msg) => …,
 *     onError:             (msg) => …,
 *     onOpen:              () => …,
 *     onClose:             () => …,
 *   });
 *   ws.connect();
 *   ws.sendAudio(float32Frame);
 *   ws.close();
 */

(function () {
  const NOOP = () => {};

  class ElcoriaWebSocket {
    constructor(opts = {}) {
      this.url = opts.url || defaultUrl();
      this.config = opts.config || "lightweight-cpu";
      this.sessionId = opts.sessionId || cryptoRandomId();

      this.onSessionStart = opts.onSessionStart || NOOP;
      this.onTranscriptPartial = opts.onTranscriptPartial || NOOP;
      this.onTranscriptFinal = opts.onTranscriptFinal || NOOP;
      this.onIntentUpdate = opts.onIntentUpdate || NOOP;
      this.onError = opts.onError || NOOP;
      this.onOpen = opts.onOpen || NOOP;
      this.onClose = opts.onClose || NOOP;
      this.onUnknown = opts.onUnknown || NOOP;

      this.ws = null;
      this._closedByUser = false;
    }

    connect() {
      const url = withParams(this.url, {
        session_id: this.sessionId,
        config: this.config,
      });

      this._closedByUser = false;
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      this.ws = ws;

      ws.addEventListener("open", () => {
        this.onOpen();
      });

      ws.addEventListener("message", (ev) => {
        if (typeof ev.data !== "string") {
          // Server should not send binary down to us; ignore.
          return;
        }
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch (e) {
          console.warn("[Elcoria WS] non-JSON text frame:", ev.data);
          return;
        }
        this._dispatch(msg);
      });

      ws.addEventListener("error", (ev) => {
        console.error("[Elcoria WS] socket error", ev);
      });

      ws.addEventListener("close", (ev) => {
        this.onClose({ code: ev.code, reason: ev.reason, clean: this._closedByUser });
        this.ws = null;
      });
    }

    _dispatch(msg) {
      switch (msg.type) {
        case "session.start":
          this.onSessionStart(msg);
          break;
        case "transcript.partial":
          this.onTranscriptPartial(msg);
          break;
        case "transcript.final":
          this.onTranscriptFinal(msg);
          break;
        case "intent.update":
          this.onIntentUpdate(msg);
          break;
        case "error":
          this.onError(msg);
          break;
        default:
          this.onUnknown(msg);
      }
    }

    /** Send one mic frame. `frame` is a Float32Array at the target rate. */
    sendAudio(frame) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      // Float32Array.buffer may be a SharedArrayBuffer in some browsers; copy to a
      // plain ArrayBuffer view so the WS impl accepts it.
      this.ws.send(frame.buffer.slice(0));
    }

    /** Optional: tell the server we're done. The server should flush + close. */
    sendEnd() {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try {
        this.ws.send(JSON.stringify({ type: "session.end" }));
      } catch (e) {}
    }

    close() {
      this._closedByUser = true;
      if (this.ws && this.ws.readyState <= WebSocket.OPEN) {
        try { this.sendEnd(); } catch (e) {}
        try { this.ws.close(); } catch (e) {}
      }
      this.ws = null;
    }

    get readyState() {
      return this.ws ? this.ws.readyState : WebSocket.CLOSED;
    }
  }

  function defaultUrl() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    // Honor ?ws=… for ad-hoc backend overrides; otherwise default to same-origin.
    const override = new URLSearchParams(window.location.search).get("ws");
    if (override) return override;
    return `${proto}//${window.location.host}/v1/stream`;
  }

  function withParams(url, params) {
    const u = new URL(url, window.location.href);
    for (const [k, v] of Object.entries(params)) {
      if (v != null) u.searchParams.set(k, v);
    }
    // Convert back to a string. URL with ws:/wss: works in modern browsers.
    return u.toString();
  }

  function cryptoRandomId() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  window.ElcoriaWebSocket = ElcoriaWebSocket;
})();
