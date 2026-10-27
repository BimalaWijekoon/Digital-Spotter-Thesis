import assert from 'node:assert/strict';
import test from 'node:test';
import { formatPoseTestResult } from '../../src/digital_spotter/web/static/ui-preview/pose-test-result.mjs';

test('detected poses are not labelled as zero when visibility is insufficient', () => {
  assert.equal(formatPoseTestResult({ frames_received: 175, good_pose_frames: 0,
    poses_not_found: 85, poses_low_visibility: 90 }),
    'Detected 90/175 · quality OK 0 · saved');
});

test('missing result counters do not fabricate a detection count', () => {
  assert.equal(formatPoseTestResult({}), 'Result unavailable');
});
