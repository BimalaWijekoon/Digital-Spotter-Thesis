// Scenario selection is metadata only. Decisions come exclusively from the model API.
import { parseReplayIMU } from './demo-imu-replay.mjs';

export const DEMO_MODEL_VERSION = 'digital_spotter_v5_imu_synthetic_r1';

export function describeDemoDecision(value) {
  const result = value.predicted_class === 0 ? 'Good form' : 'Check form';
  const probability = (value.calibrated_probability * 100).toFixed(2);
  const threshold = (value.threshold * 100).toFixed(2);
  const relation = value.predicted_class === 0 ? '<' : '≥';
  const detail = value.matches_source_label === false
    ? `Label: ${value.source_label === 1 ? 'incorrect' : 'correct'} · ${probability}% ${relation} ${threshold}% threshold`
    : `Synthetic replay · rep ${value.rep_id}`;
  return { result, detail };
}

export class DemoInferenceClient {
  constructor(fetcher = globalThis.fetch.bind(globalThis)) {
    this.fetcher = fetcher;
    this.generation = 0;
    this.busy = false;
  }
  reset() { this.generation++; }
  async catalog() {
    const response = await this.fetcher('/api/research/demo', { cache: 'no-store' });
    if (!response.ok) throw new Error('Demo inference is not enabled');
    const value = await response.json();
    if (value.model_version !== DEMO_MODEL_VERSION || value.reference_only !== true ||
        value.live !== false || value.cases?.length !== 4) throw new Error('Replay contract mismatch');
    for (const exercise of ['squat', 'deadlift']) for (const form of ['correct', 'incorrect']) {
      const cases = value.cases.filter(item => item.exercise === exercise && item.form === form);
      if (cases.length !== 1 || !Number.isFinite(cases[0].load_kg) || cases[0].load_kg < 0) {
        throw new Error('Replay catalog mismatch');
      }
      parseReplayIMU(cases[0].imu_replay);
    }
    return value;
  }
  async startFeedback() {
    const response = await this.fetcher('/api/research/demo/start', {
      method: 'POST', cache: 'no-store', headers: { 'X-DS-Demo': '1' },
    });
    if (!response.ok) throw new Error('Demo feedback unavailable');
    const value = await response.json();
    if (typeof value.enabled !== 'boolean' || value.cue !== 'start' ||
        typeof value.dispatched !== 'boolean' || !Array.isArray(value.warnings)) {
      throw new Error('Demo feedback response mismatch');
    }
    return value;
  }
  async predict(selection, repId) {
    if (this.busy) return null;
    const generation = this.generation;
    this.busy = true;
    try {
      const request = { exercise: selection.exercise, form: selection.form, rep_id: repId };
      const response = await this.fetcher('/api/research/demo/predict', {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-DS-Demo': '1' },
        body: JSON.stringify(request),
      });
      if (!response.ok) throw new Error('Model inference unavailable');
      const value = await response.json();
      if (value.source !== 'synthetic_training_replay' || value.live !== false ||
          value.reference_only !== true || typeof value.actuators_enabled !== 'boolean' ||
          value.feedback?.enabled !== value.actuators_enabled ||
          value.feedback?.cue !== (value.predicted_class === 1 ? 'bad' : 'good') ||
          typeof value.feedback?.dispatched !== 'boolean' || !Array.isArray(value.feedback?.warnings) ||
          value.animation_drives_features !== false || value.model_version !== DEMO_MODEL_VERSION ||
          value.exercise !== request.exercise || value.form !== request.form || value.rep_id !== repId ||
          ![value.raw_probability, value.calibrated_probability, value.threshold].every(
            number => Number.isFinite(number) && number >= 0 && number <= 1) ||
          value.predicted_class !== Number(value.calibrated_probability >= value.threshold)) {
        throw new Error('Model response contract mismatch');
      }
      return generation === this.generation ? value : null;
    } catch (error) {
      if (generation !== this.generation) return null;
      throw error;
    } finally { this.busy = false; }
  }
}
