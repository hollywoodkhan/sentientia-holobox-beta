class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.inputRate = options.processorOptions?.inputSampleRate || sampleRate;
    this.ratio = this.inputRate / 16000;
    this.pending = [];
    this.phase = 0;
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input?.length) return true;
    while (this.phase < input.length) {
      const index = Math.floor(this.phase);
      const next = Math.min(index + 1, input.length - 1);
      const mix = this.phase - index;
      const sample = input[index] + (input[next] - input[index]) * mix;
      this.pending.push(Math.max(-1, Math.min(1, sample)));
      this.phase += this.ratio;
    }
    this.phase -= input.length;
    if (this.pending.length >= 640) {
      const pcm = new Int16Array(this.pending.splice(0, 640).map((value) =>
        value < 0 ? value * 0x8000 : value * 0x7fff,
      ));
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("mic-capture", MicCaptureProcessor);
