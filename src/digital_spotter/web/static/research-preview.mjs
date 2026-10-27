/** Private bench composition only; not the authenticated product video UI. */
import { MediaMtxWhepPlayer } from './whep-player.mjs';

export function createResearchPreview({
  videoElement, Reader, onState = () => {},
  onDeadline = () => {},
  maxDurationMs = 120000,
  allowEndpoint = endpoint => endpoint.protocol === 'http:' && endpoint.hostname === '127.0.0.1',
  setTimer = setTimeout, clearTimer = clearTimeout,
}) {
  if (typeof Reader !== 'function') throw new TypeError('Pinned reader is required');
  if (typeof allowEndpoint !== 'function') throw new TypeError('Endpoint policy is required');
  if (maxDurationMs !== null && (!Number.isSafeInteger(maxDurationMs) || maxDurationMs <= 0)) {
    throw new TypeError('Preview duration must be a positive integer or null');
  }
  let timer = null;
  const player = new MediaMtxWhepPlayer({
    videoElement, onState,
    readerFactory: ({ token, ...options }) => {
      // This pinned upstream reader has no token-authentication support.
      // Never silently discard a credential if this boundary is reused later.
      if (token) throw new Error('Research reader does not support access tokens');
      return new Reader(options);
    },
  });
  const stop = () => {
    if (timer !== null) clearTimer(timer);
    timer = null;
    player.stop();
  };
  return {
    get state() { return player.state; },
    async start(whepUrl) {
      const endpoint = new URL(whepUrl);
      if (!allowEndpoint(endpoint)) {
        throw new TypeError('Research preview endpoint is outside its private access policy');
      }
      await player.start({ whepUrl });
      if (maxDurationMs !== null) {
        timer = setTimer(() => { stop(); onDeadline(); }, maxDurationMs);
      }
    },
    stop,
  };
}
