const {test} = require("node:test");
const assert = require("node:assert/strict");
const {JarvisAudioPlayer} = require("../web/audio-player.js");
const wav = Buffer.from("fixture").toString("base64");
function fixture() {
  const made=[], states=[], errors=[];
  const context = {
    currentTime:10, destination:{},
    decodeAudioData:async()=>({duration:2}),
    createBufferSource() {
      const source={start(when){this.when=when;},stop(){this.stopped=true;},connect(){},disconnect(){}};
      made.push(source);return source;
    }
  };
  const player=new JarvisAudioPlayer(async()=>context,s=>states.push(s),e=>errors.push(e));
  return {context,player,made,states,errors};
}
test("decodes and schedules consecutive sentences without callback gaps",async()=>{
  const {player,made,states}=fixture();
  const first=player.enqueue(wav),second=player.enqueue(wav);
  player.finish();
  await Promise.all([first,second]);
  assert.equal(made.length,2);
  assert.equal(made[1].when,made[0].when+made[0].buffer.duration);
  assert.deepEqual(states,[true]);
  made[0].onended();assert.equal(player.active,true);
  made[1].onended();assert.deepEqual(states,[true,false]);
});
test("keeps echo protection active between sentences while generation continues",async()=>{
  const {player,made,states,context}=fixture();
  await player.enqueue(wav);
  made[0].onended();
  assert.deepEqual(states,[true]);
  context.currentTime=14;
  await player.enqueue(wav);
  player.finish();
  made[1].onended();
  assert.deepEqual(states,[true,false]);
});
test("cancel stops all scheduled audio and discards a decoding stale sentence",async()=>{
  const {player,made,context,states}=fixture();
  await player.enqueue(wav);
  let decode;
  context.decodeAudioData=()=>new Promise(resolve=>{decode=resolve;});
  const pending=player.enqueue(wav);
  await new Promise(resolve=>setImmediate(resolve));
  player.cancel();
  assert.equal(made[0].stopped,true);
  decode({duration:2});
  await pending;
  assert.equal(made.length,1);
  assert.equal(player.active,false);
  assert.deepEqual(states,[true,false]);
});
test("finishing before decoding resolves does not cut off the last sentence",async()=>{
  const {player,made,states}=fixture();
  const job=player.enqueue(wav);player.finish();
  assert.deepEqual(states,[true]);
  await job;
  assert.equal(player.active,true);
  made[0].onended();
  assert.equal(player.active,false);
});
