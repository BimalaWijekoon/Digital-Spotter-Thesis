/** Rendering-only CMU squat retiming; never pose inference or ML features. */
import { sampleDemoPose } from './demo-motion.mjs';

export function sampleCapturedSquat(clip, form, progress) {
  if (clip.schema !== 'ds_demo_squat_mocap_v1' || clip.render_only !== true ||
      clip.classifier_features !== false || clip.frames.length < 2) throw new Error('Invalid squat motion asset');
  const amount = Math.min(1, Math.max(0, progress)) * (clip.frames.length - 1);
  const index = Math.min(Math.floor(amount), clip.frames.length - 2), fraction = amount - index;
  const a = clip.frames[index], b = clip.frames[index + 1];
  const lerp = (x, y) => x.map((number, i) => number + (y[i] - number) * fraction);
  const hip = lerp(a.hip, b.hip);
  const spine = a.spine.map((vector, i) => lerp(vector, b.spine[i]));
  const depth = Math.min(1, Math.max(0, (clip.frames[0].hip[1] - hip[1]) / .55));
  // Error presentation is an authored overlay, not captured incorrect technique.
  const extraLean = form === 'incorrect' ? .28 * depth : 0;
  for (const vector of spine) {
    const y = vector[1], z = vector[2];
    vector[1] = y * Math.cos(extraLean) - z * Math.sin(extraLean);
    vector[2] = y * Math.sin(extraLean) + z * Math.cos(extraLean);
    const length = Math.hypot(...vector);
    vector.forEach((value, i) => { vector[i] = value / length; });
  }
  const pose = sampleDemoPose('squat', form, progress);
  const heightOffset = 1.03 - clip.frames[0].hip[1];
  pose.hipL = [hip[0] - .16, hip[1] + heightOffset, hip[2]];
  pose.hipR = [hip[0] + .16, hip[1] + heightOffset, hip[2]];
  for (const [side, sign] of [['L', -1], ['R', 1]]) {
    pose[`shoulder${side}`] = [hip[0] + sign * .23 + spine[2][0] * .55,
      hip[1] + heightOffset + spine[2][1] * .55, hip[2] + spine[2][2] * .55];
  }
  // Capture uses anatomical left (+X); old drawing names are screen-side names.
  pose.kneeR = lerp(a.knees[0], b.knees[0]);
  pose.kneeL = lerp(a.knees[1], b.knees[1]);
  pose.captureSpine = spine;
  return pose;
}
