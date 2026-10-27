/** Detection is distinct from the stricter per-joint quality gate. */
export function formatPoseTestResult(result) {
  const { frames_received: total, good_pose_frames: good, poses_not_found: missing } = result;
  if (![total, good, missing].every(value => Number.isSafeInteger(value) && value >= 0)
      || missing > total || good > total - missing) return 'Result unavailable';
  if (total === 0) return 'No frames received · saved';
  return `Detected ${total - missing}/${total} · quality OK ${good} · saved`;
}
