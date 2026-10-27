// Predefined demonstrations, never error categories inferred by the binary model.
const directory = '../vendor/exercise-scenarios-character-r1/';
function clip(file, animation, technique, sha256) {
  return Object.freeze({ url: new URL(`${directory}${file}.glb`, import.meta.url),
    animation, technique, sha256 });
}
const CLIPS = Object.freeze({
  squat: Object.freeze({
    correct: clip('squat_correct', 'Squat_Correct', 'Correct form',
      '0632171fa10f2a4975d4681ceb03fec5449d2efd9814f0c01d7ac4d1dee3e095'),
    incorrect: clip('squat_forward_lean', 'Squat_ExcessiveForwardLean', 'Excessive forward lean',
      '6089bab9a8e1bbc3e3dda514b8d669ffddd0c2699365fc83372cc3116217d365'),
  }),
  deadlift: Object.freeze({
    correct: clip('deadlift_correct', 'Deadlift_Correct', 'Correct form',
      'b73ee8fcba0b2704c9830eab79e6b81c6ad80e307566851b6adac58abffc42ca'),
    incorrect: clip('deadlift_spinal_rounding', 'Deadlift_SpinalRounding', 'Spinal rounding',
      '76c3ca3d68be2bc7dc09506db8ce98acb8a88395fa4f83fecc9a2adcad9c7498'),
  }),
});

export function getReviewClip(exercise, form) {
  if (!Object.hasOwn(CLIPS, exercise) || !['correct', 'incorrect'].includes(form)) {
    throw new TypeError('Invalid review scenario');
  }
  return CLIPS[exercise][form] ?? null;
}

export function reviewClipTime(progress, duration) {
  if (!Number.isFinite(progress) || !Number.isFinite(duration) || duration <= 0) {
    throw new TypeError('Invalid review playback');
  }
  return Math.max(0, Math.min(1, progress)) * duration;
}
