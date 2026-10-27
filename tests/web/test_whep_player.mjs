import assert from "node:assert/strict";
import test from "node:test";

import {
  MediaMtxWhepPlayer,
  WhepPlayerState,
} from "../../src/digital_spotter/web/static/whep-player.mjs";


function fakeVideo() {
  return {
    srcObject: null,
    playCalls: 0,
    pauseCalls: 0,
    async play() {
      this.playCalls += 1;
    },
    pause() {
      this.pauseCalls += 1;
    },
  };
}


test("starts the official MediaMTX reader with an explicit WHEP endpoint", async () => {
  const video = fakeVideo();
  const states = [];
  let readerOptions;
  let closeCalls = 0;
  const player = new MediaMtxWhepPlayer({
    videoElement: video,
    readerFactory: (options) => {
      readerOptions = options;
      return { close: () => { closeCalls += 1; } };
    },
    onState: (state) => states.push(state),
  });

  await player.start({
    whepUrl: "http://spotter.local:8889/picamera2/whep",
    accessToken: "short-lived-token",
  });

  assert.equal(readerOptions.url, "http://spotter.local:8889/picamera2/whep");
  assert.equal(readerOptions.token, "short-lived-token");
  assert.equal(typeof readerOptions.onTrack, "function");
  assert.equal(typeof readerOptions.onError, "function");
  assert.deepEqual(states, [{ state: WhepPlayerState.CONNECTING, reason: null }]);

  const stream = { id: "video-stream" };
  readerOptions.onTrack({ streams: [stream] });
  await Promise.resolve();

  assert.equal(video.srcObject, stream);
  assert.equal(video.playCalls, 1);
  assert.deepEqual(states.at(-1), { state: WhepPlayerState.PLAYING, reason: null });

  player.stop();
  assert.equal(closeCalls, 1);
  assert.equal(video.pauseCalls, 1);
  assert.equal(video.srcObject, null);
  assert.deepEqual(states.at(-1), { state: WhepPlayerState.STOPPED, reason: null });
});


test("reports a safe degraded state when the reader fails", async () => {
  const states = [];
  let readerOptions;
  const player = new MediaMtxWhepPlayer({
    videoElement: fakeVideo(),
    readerFactory: (options) => {
      readerOptions = options;
      return { close() {} };
    },
    onState: (state) => states.push(state),
  });

  await player.start({
    whepUrl: "https://spotter.local/picamera2/whep",
    accessToken: "must-not-leak",
  });
  readerOptions.onError(new Error("server rejected must-not-leak"));

  assert.deepEqual(states.at(-1), {
    state: WhepPlayerState.DEGRADED,
    reason: "whep_reader_error",
  });
  assert.doesNotMatch(JSON.stringify(states), /must-not-leak/);
});


test("rejects unsafe or ambiguous WHEP endpoints before creating a reader", async () => {
  const invalidEndpoints = [
    "ws://spotter.local/picamera2/whep",
    "http://user:pass@spotter.local/picamera2/whep",
    "http://spotter.local/picamera2",
    "http://spotter.local/picamera2/whep?token=secret",
    "http://spotter.local/picamera2/whep#fragment",
  ];

  for (const whepUrl of invalidEndpoints) {
    let factoryCalls = 0;
    const player = new MediaMtxWhepPlayer({
      videoElement: fakeVideo(),
      readerFactory: () => {
        factoryCalls += 1;
        return { close() {} };
      },
    });

    await assert.rejects(player.start({ whepUrl }), /WHEP endpoint/);
    assert.equal(factoryCalls, 0);
  }
});


test("does not allow two active readers", async () => {
  const player = new MediaMtxWhepPlayer({
    videoElement: fakeVideo(),
    readerFactory: () => ({ close() {} }),
  });

  await player.start({ whepUrl: "http://spotter.local/picamera2/whep" });
  await assert.rejects(
    player.start({ whepUrl: "http://spotter.local/picamera2/whep" }),
    /already active/,
  );
});


test("ignores a late track callback after stop", async () => {
  const video = fakeVideo();
  const states = [];
  let readerOptions;
  const player = new MediaMtxWhepPlayer({
    videoElement: video,
    readerFactory: (options) => {
      readerOptions = options;
      return { close() {} };
    },
    onState: (state) => states.push(state),
  });
  await player.start({ whepUrl: "http://spotter.local/picamera2/whep" });
  player.stop();

  readerOptions.onTrack({ streams: [{ id: "late-stream" }] });
  await Promise.resolve();

  assert.equal(video.srcObject, null);
  assert.equal(video.playCalls, 0);
  assert.deepEqual(states.at(-1), { state: WhepPlayerState.STOPPED, reason: null });
});


test("requires a closable reader and a bounded string token", async () => {
  const endpoint = "http://spotter.local/picamera2/whep";
  const missingClose = new MediaMtxWhepPlayer({
    videoElement: fakeVideo(),
    readerFactory: () => ({}),
  });
  await assert.rejects(missingClose.start({ whepUrl: endpoint }), /closable reader/);

  const invalidToken = new MediaMtxWhepPlayer({
    videoElement: fakeVideo(),
    readerFactory: () => ({ close() {} }),
  });
  await assert.rejects(
    invalidToken.start({ whepUrl: endpoint, accessToken: { secret: true } }),
    /access token/,
  );
});
