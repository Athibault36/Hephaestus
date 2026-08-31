import { useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function VoiceConsole() {
  const { isRecording, setIsRecording, isConnected, agentState } = useMissionControlStore();
  const [localAudioLevel, setLocalAudioLevel] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);

  const canRecord = isConnected && agentState !== 'speaking' && agentState !== 'error';

  // Simulate audio level for visualization
  useEffect(() => {
    if (isRecording) {
      // In real implementation, this would come from actual microphone input
      const interval = setInterval(() => {
        setLocalAudioLevel(Math.random() * 0.8 + 0.2);
      }, 50);
      return () => clearInterval(interval);
    } else {
      setLocalAudioLevel(0);
    }
  }, [isRecording]);

  const startRecording = async () => {
    if (!canRecord) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Setup audio visualization
      audioContextRef.current = new AudioContext();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      // Setup media recorder
      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
      });

      const chunks: Blob[] = [];
      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        // Send to STT pipeline
        sendAudioToSTT(blob);
      };

      mediaRecorderRef.current.start(100); // Send chunks every 100ms
      setIsRecording(true);
    } catch (e) {
      console.error('Failed to start recording:', e);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
    }
    setIsRecording(false);
  };

  const sendAudioToSTT = async (blob: Blob) => {
    // Would send to Whisper/Faster-Whisper via WebSocket or HTTP
    console.log('Sending audio to STT:', blob.size, 'bytes');
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Generate waveform bars
  const bars = Array.from({ length: 32 }, (_, i) => {
    const height = isRecording ? Math.max(4, localAudioLevel * 100 * (0.5 + Math.random() * 0.5)) : 4;
    return (
      <div
        key={i}
        className="voice-bar"
        style={{ height: `${height}px` }}
      />
    );
  });

  return (
    <div className="voice-console">
      <div className="voice-visualizer">
        <div className="voice-waveform" role="img" aria-label="Audio waveform">
          {bars}
        </div>
        <div className="voice-status">
          {isRecording ? '🔴 Recording...' : canRecord ? 'Click to speak' : 'Connect to UE first'}
        </div>
      </div>

      <div className="voice-controls">
        <button
          className={`voice-btn ${isRecording ? 'recording' : ''}`}
          onClick={toggleRecording}
          disabled={!canRecord}
          aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          title={isRecording ? 'Stop (Space)' : 'Push to Talk (Space)'}
        >
          {isRecording ? '⏹' : '🎤'}
        </button>

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

      <div className="voice-history">
        <h4>Recent Commands</h4>
        <div className="command-history">
          {/* Would show recognized commands */}
        </div>
      </div>
    </div>
  );
}