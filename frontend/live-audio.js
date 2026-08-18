export class LiveAvatarSession {
  constructor({ baseUrl, clientId, onEvent }) {
    this.baseUrl = baseUrl;
    this.clientId = clientId;
    this.onEvent = onEvent;
    this.socket = null;
    this.context = null;
    this.playback = null;
    this.capture = null;
    this.stream = null;
    this.readyPromise = null;
  }

  async ensureAudio() {
    if (!this.context) {
      this.context = new AudioContext({ latencyHint: "interactive" });
      await Promise.all([
        this.context.audioWorklet.addModule("./mic-capture-worklet.js?v=20260818-binary1"),
        this.context.audioWorklet.addModule("./pcm-playback-worklet.js?v=20260818-binary1"),
      ]);
      this.playback = new AudioWorkletNode(this.context, "pcm-playback", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [1],
      });
      this.playback.port.onmessage = ({ data }) => {
        if (data.type === "level") this.onEvent({ type: "level", value: data.value });
      };
      this.playback.connect(this.context.destination);
    }
    if (this.context.state === "suspended") await this.context.resume();
  }

  connect() {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve();
    if (this.readyPromise) return this.readyPromise;
    const url = new URL(this.baseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `${url.pathname.replace(/\/$/, "")}/ws/live/${this.clientId}`;
    url.search = "";
    this.readyPromise = new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      socket.binaryType = "arraybuffer";
      this.socket = socket;
      socket.onmessage = async ({ data }) => {
        if (data instanceof ArrayBuffer) {
          await this.ensureAudio();
          this.playback.port.postMessage({ type: "audio", buffer: data }, [data]);
          this.onEvent({ type: "audio" });
          return;
        }
        const message = JSON.parse(data);
        if (message.type === "ready") {
          this.readyPromise = null;
          resolve();
        } else if (message.type === "interrupted") {
          this.clearPlayback();
        }
        this.onEvent(message);
      };
      socket.onerror = () => {
        this.readyPromise = null;
        reject(new Error("Live voice connection failed"));
      };
      socket.onclose = () => {
        this.readyPromise = null;
        this.onEvent({ type: "closed" });
      };
    });
    return this.readyPromise;
  }

  async sendText(text) {
    await this.ensureAudio();
    await this.connect();
    this.socket.send(JSON.stringify({ type: "text", text }));
  }

  async startMicrophone() {
    await this.ensureAudio();
    await this.connect();
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const source = this.context.createMediaStreamSource(this.stream);
    this.capture = new AudioWorkletNode(this.context, "mic-capture", {
      processorOptions: { inputSampleRate: this.context.sampleRate },
    });
    const silent = this.context.createGain();
    silent.gain.value = 0;
    this.capture.port.onmessage = ({ data }) => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(data);
      }
    };
    source.connect(this.capture).connect(silent).connect(this.context.destination);
  }

  stopMicrophone() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.capture?.disconnect();
    this.capture = null;
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "audio_end" }));
    }
  }

  clearPlayback() {
    this.playback?.port.postMessage({ type: "clear" });
  }

  close() {
    this.stopMicrophone();
    this.clearPlayback();
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "close" }));
    }
    this.socket?.close();
  }
}
