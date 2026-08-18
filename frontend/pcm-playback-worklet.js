class PcmPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.current = null;
    this.position = 0;
    this.step = 24000 / sampleRate;
    this.levelFrames = 0;
    this.levelSum = 0;
    this.port.onmessage = ({ data }) => {
      if (data.type === "clear") {
        this.queue.length = 0;
        this.current = null;
        this.position = 0;
        return;
      }
      if (data.type === "audio") {
        const pcm = new Int16Array(data.buffer);
        const floats = new Float32Array(pcm.length);
        for (let i = 0; i < pcm.length; i += 1) floats[i] = pcm[i] / 32768;
        this.queue.push(floats);
      }
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    for (let i = 0; i < output.length; i += 1) {
      while (!this.current || this.position >= this.current.length - 1) {
        this.current = this.queue.shift() || null;
        this.position = 0;
        if (!this.current) break;
      }
      let value = 0;
      if (this.current) {
        const index = Math.floor(this.position);
        const mix = this.position - index;
        value = this.current[index] + (this.current[index + 1] - this.current[index]) * mix;
        this.position += this.step;
      }
      output[i] = value;
      this.levelSum += value * value;
      this.levelFrames += 1;
      if (this.levelFrames >= 480) {
        this.port.postMessage({ type: "level", value: Math.sqrt(this.levelSum / this.levelFrames) });
        this.levelFrames = 0;
        this.levelSum = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-playback", PcmPlaybackProcessor);
