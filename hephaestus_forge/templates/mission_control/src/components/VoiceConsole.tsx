import { useCallback, useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function VoiceConsole() {
  const {
    isRecording,
    audioLevel,
    isConnected,
    agentBusy,
    agentState,
    beginVoiceCapture,
    cancelVoiceCapture,
    failVoiceCapture,
    finishVoiceCapture,
    partialTranscript,
    finalTranscript,
    voiceCancelReason,
    voiceError,
    setAgentState,
  } = useMissionControlStore();
  const [localAudioLevel, setLocalAudioLevel] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const activeTurnRef = useRef<string | null>(null);
  const cancelledTurnsRef = useRef<Set<string>>(new Set());
  const chunksRef = useRef<Blob[]>([]);
  const partialTranscriptRef = useRef('');

  const canStartCapture = isConnected && agentState !== 'error' && (!agentBusy || agentState === 'speaking');
  const controlsDisabled = isRecording ? false : !canStartCapture;
  const isBargeIn = !isRecording && agentState === 'speaking';

  useEffect(() => {
    partialTranscriptRef.current = partialTranscript;
  }, [partialTranscript]);

  const stopMeter = useCallback(() => {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setLocalAudioLevel(0);
  }, []);

  const cleanupMedia = useCallback(() => {
    stopMeter();
    const recorder = mediaRecorderRef.current;
    if (recorder) {
      recorder.stream.getTracks().forEach((track) => track.stop());
      mediaRecorderRef.current = null;
    }
    const audioContext = audioContextRef.current;
    if (audioContext && audioContext.state !== 'closed') {
      void audioContext.close();
    }
    audioContextRef.current = null;
    analyserRef.current = null;
  }, [stopMeter]);

  const startMeter = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const samples = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      const rms = Math.sqrt(
        samples.reduce((sum, sample) => {
          const centered = (sample - 128) / 128;
          return sum + centered * centered;
        }, 0) / samples.length,
      );
      setLocalAudioLevel(Math.max(audioLevel, Math.min(1, rms * 4)));
      animationFrameRef.current = window.requestAnimationFrame(tick);
    };
    tick();
  }, [audioLevel]);

  const sendAudioToSTT = useCallback(async (turnId: string, blob: Blob) => {
    // Mission Control does not own a streaming STT server yet. Keep this as an
    // explicit processing boundary so future partial/final events can use turnId.
    console.log('Voice capture ready for STT:', { turnId, bytes: blob.size });
    setAgentState('idle');
  }, [setAgentState]);

  const startRecording = useCallback(async () => {
    if (!canStartCapture || isRecording) return;

    const turnId = beginVoiceCapture();
    activeTurnRef.current = turnId;
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContextRef.current = new AudioContext();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      const mimeType = 'audio/webm;codecs=opus';
      const recorderOptions = MediaRecorder.isTypeSupported(mimeType) ? { mimeType } : undefined;
      const recorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        cleanupMedia();
        const wasCancelled = cancelledTurnsRef.current.has(turnId);
        cancelledTurnsRef.current.delete(turnId);
        if (wasCancelled) return;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        finishVoiceCapture(turnId, partialTranscriptRef.current);
        void sendAudioToSTT(turnId, blob);
      };

      recorder.start(100);
      startMeter();
    } catch (e) {
      cleanupMedia();
      activeTurnRef.current = null;
      const message = e instanceof Error ? e.message : String(e);
      failVoiceCapture(message);
    }
  }, [
    beginVoiceCapture,
    canStartCapture,
    cleanupMedia,
    failVoiceCapture,
    finishVoiceCapture,
    isRecording,
    sendAudioToSTT,
    startMeter,
  ]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    const turnId = activeTurnRef.current;
    activeTurnRef.current = null;
    if (!turnId) {
      cancelVoiceCapture('no_active_turn');
      cleanupMedia();
      return;
    }

    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      cleanupMedia();
      finishVoiceCapture(turnId, partialTranscriptRef.current);
      void sendAudioToSTT(turnId, new Blob([], { type: 'audio/webm' }));
    }
  }, [cancelVoiceCapture, cleanupMedia, finishVoiceCapture, sendAudioToSTT]);

  const cancelRecording = useCallback((reason = 'operator_cancelled') => {
    const recorder = mediaRecorderRef.current;
    const turnId = activeTurnRef.current;
    activeTurnRef.current = null;
    if (turnId) cancelledTurnsRef.current.add(turnId);
    cancelVoiceCapture(reason);

    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      cleanupMedia();
    }
  }, [cancelVoiceCapture, cleanupMedia]);

  const toggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      void startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName?.toLowerCase();
      const isTyping = tagName === 'input' || tagName === 'textarea' || target?.isContentEditable;

      if (event.key === 'Escape' && isRecording) {
        event.preventDefault();
        cancelRecording('escape_key');
        return;
      }

      if (event.code === 'Space' && !isTyping && (isRecording || canStartCapture)) {
        event.preventDefault();
        toggleRecording();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [canStartCapture, cancelRecording, isRecording, toggleRecording]);

  useEffect(() => {
    return () => {
      if (activeTurnRef.current) {
        cancelVoiceCapture('component_unmounted');
      }
      cleanupMedia();
    };
  }, [cancelVoiceCapture, cleanupMedia]);

  const bars = Array.from({ length: 32 }, (_, i) => {
    const phase = 0.55 + Math.sin(i * 0.65) * 0.35;
    const height = isRecording ? Math.max(4, localAudioLevel * 100 * phase) : 4;
    return (
      <div
        key={i}
        className="voice-bar"
        style={{ height: `${height}px` }}
      />
    );
  });

  const statusText = voiceError
    ? `Error: ${voiceError}`
    : isRecording
      ? 'Listening...'
      : agentState === 'processing'
        ? 'Processing audio...'
        : isBargeIn
          ? 'Speaking - click to interrupt'
          : canStartCapture
            ? 'Click to speak'
            : isConnected
              ? 'Voice unavailable while agent is busy'
              : 'Connect to UE first';

  return (
    <div className="voice-console">
      <div className="voice-visualizer">
        <div className="voice-waveform" role="img" aria-label="Audio waveform">
          {bars}
        </div>
        <div className="voice-status">
          {statusText}
        </div>
      </div>

      <div className="voice-controls">
        <button
          className={`voice-btn ${isRecording ? 'recording' : ''} ${isBargeIn ? 'barge-in' : ''}`}
          onClick={toggleRecording}
          disabled={controlsDisabled}
          aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          title={isRecording ? 'Stop and process (Space)' : isBargeIn ? 'Interrupt speech and talk (Space)' : 'Push to Talk (Space)'}
        >
          {isRecording ? 'Stop' : isBargeIn ? 'Interrupt' : 'Mic'}
        </button>
        {isRecording && (
          <button type="button" className="voice-cancel-btn" onClick={() => cancelRecording()} title="Cancel without submitting audio">
            Cancel
          </button>
        )}

        <div className="voice-input-level">
          <div
            className="voice-input-level-fill"
            style={{ width: `${localAudioLevel * 100}%` }}
          />
        </div>

        <div className="voice-shortcuts">
          <kbd>Space</kbd> Push-to-Talk
          {isRecording && <><kbd>Esc</kbd> Cancel</>}
        </div>
      </div>

      <div className="voice-transcript" aria-live="polite">
        {partialTranscript ? (
          <p><strong>Partial:</strong> {partialTranscript}</p>
        ) : finalTranscript ? (
          <p><strong>Final:</strong> {finalTranscript}</p>
        ) : voiceCancelReason ? (
          <p>Cancelled: {voiceCancelReason.replace(/_/g, ' ')}</p>
        ) : (
          <p>Transcript will appear here. Review before sending any command.</p>
        )}
      </div>

      <div className="voice-history">
        <h4>Recent Commands</h4>
        <div className="command-history">
          {/* Would show recognized commands */}
        </div>
      </div>
    </div>
  );
}