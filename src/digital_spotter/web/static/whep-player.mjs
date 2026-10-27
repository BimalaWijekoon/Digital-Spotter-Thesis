/**
 * Small lifecycle wrapper around MediaMTX's supported MediaMTXWebRTCReader.
 *
 * Negotiation stays inside the pinned upstream reader. This module owns only
 * endpoint validation, video attachment, safe state reporting, and cleanup.
 */

export const WhepPlayerState = Object.freeze({
  IDLE: "idle",
  CONNECTING: "connecting",
  PLAYING: "playing",
  DEGRADED: "degraded",
  STOPPED: "stopped",
});


function validateWhepEndpoint(value) {
  let endpoint;
  try {
    endpoint = new URL(value);
  } catch {
    throw new TypeError("WHEP endpoint must be an absolute HTTP(S) URL");
  }

  if (!['http:', 'https:'].includes(endpoint.protocol)) {
    throw new TypeError("WHEP endpoint must use HTTP or HTTPS");
  }
  if (endpoint.username || endpoint.password) {
    throw new TypeError("WHEP endpoint must not embed credentials");
  }
  if (endpoint.search || endpoint.hash) {
    throw new TypeError("WHEP endpoint must not contain a query or fragment");
  }
  if (!endpoint.pathname.endsWith('/whep')) {
    throw new TypeError("WHEP endpoint path must end with /whep");
  }
  return endpoint.toString();
}


export class MediaMtxWhepPlayer {
  constructor({ videoElement, readerFactory, onState = () => {} }) {
    if (!videoElement || typeof videoElement.play !== 'function') {
      throw new TypeError("videoElement with play() is required");
    }
    if (typeof readerFactory !== 'function') {
      throw new TypeError("readerFactory is required");
    }
    if (typeof onState !== 'function') {
      throw new TypeError("onState must be a function");
    }

    this.videoElement = videoElement;
    this.readerFactory = readerFactory;
    this.onState = onState;
    this.reader = null;
    this.state = WhepPlayerState.IDLE;
    this.generation = 0;
  }

  async start({ whepUrl, accessToken = '' }) {
    if (this.reader !== null) {
      throw new Error("WHEP reader is already active");
    }
    const url = validateWhepEndpoint(whepUrl);
    if (typeof accessToken !== 'string' || accessToken.length > 4096) {
      throw new TypeError("access token must be a string of at most 4096 characters");
    }
    const generation = this.generation + 1;
    this.generation = generation;
    this.#transition(WhepPlayerState.CONNECTING, null);

    try {
      const reader = this.readerFactory({
        url,
        token: accessToken,
        onError: () => {
          if (generation !== this.generation) {
            return;
          }
          this.#transition(WhepPlayerState.DEGRADED, "whep_reader_error");
        },
        onTrack: (event) => {
          if (generation !== this.generation) {
            return;
          }
          const stream = event?.streams?.[0];
          if (!stream) {
            this.#transition(WhepPlayerState.DEGRADED, "video_stream_missing");
            return;
          }

          this.videoElement.srcObject = stream;
          Promise.resolve(this.videoElement.play())
            .then(() => {
              if (generation === this.generation) {
                this.#transition(WhepPlayerState.PLAYING, null);
              }
            })
            .catch(() => {
              if (generation === this.generation) {
                this.#transition(WhepPlayerState.DEGRADED, "video_play_failed");
              }
            });
        },
      });
      if (!reader || typeof reader.close !== 'function') {
        throw new TypeError("readerFactory must return a closable reader");
      }
      this.reader = reader;
    } catch (error) {
      this.reader = null;
      this.#transition(WhepPlayerState.DEGRADED, "whep_reader_start_failed");
      throw error;
    }
  }

  stop() {
    this.generation += 1;
    if (this.reader !== null) {
      this.reader.close();
      this.reader = null;
    }
    if (typeof this.videoElement.pause === 'function') {
      this.videoElement.pause();
    }
    this.videoElement.srcObject = null;
    this.#transition(WhepPlayerState.STOPPED, null);
  }

  #transition(state, reason) {
    this.state = state;
    this.onState({ state, reason });
  }
}
