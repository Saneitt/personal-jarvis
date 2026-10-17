"use strict";
// Decode ahead and schedule on the audio clock, rather than on JS end callbacks.
class JarvisAudioPlayer {
  constructor(getContext, onState, onError) {
    this.getContext = getContext;
    this.onState = onState;
    this.onError = onError;
    this.epoch = 0;
    this.sources = new Set();
    this.chain = Promise.resolve();
    this.pending = 0;
    this.nextStart = 0;
    this.finished = true;
    this.active = false;
  }
  setActive(value) {
    if (this.active === value) return;
    this.active = value;
    this.onState(value);
  }
  enqueue(wav) {
    const epoch = this.epoch;
    this.pending++;
    this.finished = false;
    this.setActive(true);
    const job = this.chain.then(async () => {
      const context = await this.getContext();
      if (epoch !== this.epoch) return;
      const bytes = Uint8Array.from(atob(wav), c => c.charCodeAt(0));
      const buffer = await context.decodeAudioData(bytes.buffer);
      if (epoch !== this.epoch) return;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      this.sources.add(source);
      // Subsequent sentences are scheduled before the current sentence ends.
      const start = Math.max(this.nextStart, context.currentTime + 0.04);
      this.nextStart = start + buffer.duration;
      source.onended = () => {
        source.disconnect();
        if (epoch !== this.epoch) return;
        this.sources.delete(source);
        this.settle();
      };
      try { source.start(start); }
      catch (error) { this.sources.delete(source); source.disconnect(); throw error; }
    }).catch(error => {
      if (epoch === this.epoch) {
        this.finished = true;
        this.onError(error);
      }
    }).finally(() => {
      if (epoch === this.epoch) { this.pending--; this.settle(); }
    });
    this.chain = job;
    return job;
  }
  finish() { this.finished = true; this.settle(); }
  settle() {
    if (this.finished && !this.pending && !this.sources.size) {
      this.nextStart = 0;
      this.setActive(false);
    }
  }
  cancel() {
    this.epoch++;
    for (const source of this.sources) {
      source.onended = null;
      try { source.stop(); } catch {}
      source.disconnect();
    }
    this.sources.clear();
    this.chain = Promise.resolve();
    this.pending = 0;
    this.nextStart = 0;
    this.finished = true;
    this.setActive(false);
  }
}
if (typeof module !== "undefined") module.exports = {JarvisAudioPlayer};
