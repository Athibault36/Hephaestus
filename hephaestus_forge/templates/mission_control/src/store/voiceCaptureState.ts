export type VoiceCaptureStatus = 'idle' | 'listening' | 'processing' | 'speaking' | 'error';

export interface VoiceCaptureState {
  status: VoiceCaptureStatus;
  isRecording: boolean;
  activeTurnId: string | null;
  partialTranscript: string;
  finalTranscript: string;
  error: string;
  cancelReason: string;
}

export const initialVoiceCaptureState: VoiceCaptureState = {
  status: 'idle',
  isRecording: false,
  activeTurnId: null,
  partialTranscript: '',
  finalTranscript: '',
  error: '',
  cancelReason: '',
};

export function beginVoiceCapture(state: VoiceCaptureState, turnId: string): VoiceCaptureState {
  return {
    ...state,
    status: 'listening',
    isRecording: true,
    activeTurnId: turnId,
    partialTranscript: '',
    finalTranscript: '',
    error: '',
    cancelReason: '',
  };
}

export function applyVoicePartial(
  state: VoiceCaptureState,
  turnId: string,
  transcript: string,
): VoiceCaptureState {
  if (state.activeTurnId !== turnId || state.status !== 'listening') return state;
  return {
    ...state,
    partialTranscript: transcript,
    error: '',
  };
}

export function finishVoiceCapture(
  state: VoiceCaptureState,
  turnId: string,
  transcript: string,
): VoiceCaptureState {
  if (state.activeTurnId !== turnId || state.status !== 'listening') return state;
  return {
    ...state,
    status: 'processing',
    isRecording: false,
    activeTurnId: null,
    partialTranscript: '',
    finalTranscript: transcript.trim(),
    error: '',
    cancelReason: '',
  };
}

export function cancelVoiceCapture(state: VoiceCaptureState, reason = 'cancelled'): VoiceCaptureState {
  return {
    ...state,
    status: 'idle',
    isRecording: false,
    activeTurnId: null,
    partialTranscript: '',
    finalTranscript: '',
    error: '',
    cancelReason: reason,
  };
}

export function failVoiceCapture(state: VoiceCaptureState, error: string): VoiceCaptureState {
  return {
    ...state,
    status: 'error',
    isRecording: false,
    activeTurnId: null,
    partialTranscript: '',
    error,
    cancelReason: '',
  };
}
