class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(1280);
    this.offset = 0;
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.ratio = sampleRate / 16000;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.sum += input[i]; this.count++; this.phase++;
      if (this.phase >= this.ratio) {
        const sample = Math.max(-1, Math.min(1, this.sum / this.count));
        this.buffer[this.offset++] = Math.round(sample * 32767);
        this.phase -= this.ratio; this.sum = 0; this.count = 0;
        if (this.offset === 1280) {
          this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
          this.buffer = new Int16Array(1280); this.offset = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("jarvis-pcm", PCMProcessor);
