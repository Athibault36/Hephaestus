import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = resolve(root, 'src/store/voiceCaptureState.ts');

assert.ok(existsSync(sourcePath), 'voiceCaptureState.ts exists');

const source = readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
});

const module = { exports: {} };
vm.runInNewContext(compiled.outputText, { exports: module.exports, module }, { filename: sourcePath });

const {
  applyVoicePartial,
  beginVoiceCapture,
  cancelVoiceCapture,
  failVoiceCapture,
  finishVoiceCapture,
  initialVoiceCaptureState,
} = module.exports;

function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test('barge-in starts a fresh listening turn and clears old transcripts', () => {
  const speaking = {
    ...initialVoiceCaptureState,
    status: 'speaking',
    partialTranscript: 'old partial',
    finalTranscript: 'old final',
  };

  const next = beginVoiceCapture(speaking, 'turn-2');

  assert.equal(next.status, 'listening');
  assert.equal(next.isRecording, true);
  assert.equal(next.activeTurnId, 'turn-2');
  assert.equal(next.partialTranscript, '');
  assert.equal(next.finalTranscript, '');
  assert.equal(next.error, '');
});

test('cancel exits listening and ignores late finals for the cancelled turn', () => {
  const listening = applyVoicePartial(
    beginVoiceCapture(initialVoiceCaptureState, 'turn-1'),
    'turn-1',
    'spawn a dragon',
  );

  const cancelled = cancelVoiceCapture(listening, 'operator_cancelled');
  const lateFinal = finishVoiceCapture(cancelled, 'turn-1', 'spawn a dragon');

  assert.equal(cancelled.status, 'idle');
  assert.equal(cancelled.isRecording, false);
  assert.equal(cancelled.activeTurnId, null);
  assert.equal(cancelled.partialTranscript, '');
  assert.equal(cancelled.finalTranscript, '');
  assert.equal(cancelled.cancelReason, 'operator_cancelled');
  assert.deepEqual(lateFinal, cancelled);
});

test('stale partials cannot overwrite a newer barge-in turn', () => {
  const firstTurn = applyVoicePartial(
    beginVoiceCapture(initialVoiceCaptureState, 'turn-1'),
    'turn-1',
    'old words',
  );
  const secondTurn = beginVoiceCapture(firstTurn, 'turn-2');

  const stale = applyVoicePartial(secondTurn, 'turn-1', 'late old words');
  const current = applyVoicePartial(stale, 'turn-2', 'new words');

  assert.equal(stale.partialTranscript, '');
  assert.equal(current.partialTranscript, 'new words');
});

test('finish finalizes only the active turn and moves to processing', () => {
  const listening = applyVoicePartial(
    beginVoiceCapture(initialVoiceCaptureState, 'turn-1'),
    'turn-1',
    'make a cube',
  );

  const finished = finishVoiceCapture(listening, 'turn-1', 'make a cube');

  assert.equal(finished.status, 'processing');
  assert.equal(finished.isRecording, false);
  assert.equal(finished.activeTurnId, null);
  assert.equal(finished.partialTranscript, '');
  assert.equal(finished.finalTranscript, 'make a cube');
});

test('failure leaves an honest error state instead of recording forever', () => {
  const listening = beginVoiceCapture(initialVoiceCaptureState, 'turn-1');

  const failed = failVoiceCapture(listening, 'Microphone permission denied');

  assert.equal(failed.status, 'error');
  assert.equal(failed.isRecording, false);
  assert.equal(failed.activeTurnId, null);
  assert.equal(failed.partialTranscript, '');
  assert.equal(failed.error, 'Microphone permission denied');
});
