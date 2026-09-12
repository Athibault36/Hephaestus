import { useRef } from 'react';
import { type CreativeBriefSlotName, useMissionControlStore } from '../store/missionControlStore';

const SLOT_LABELS: Record<CreativeBriefSlotName, { label: string; placeholder: string }> = {
  cast: {
    label: 'Cast',
    placeholder: 'Who or what is in the shot?',
  },
  style: {
    label: 'Style',
    placeholder: 'Lighting, medium, mood, art direction...',
  },
  shot: {
    label: 'Shot',
    placeholder: 'Camera angle, framing, movement...',
  },
};

const SLOT_ORDER: CreativeBriefSlotName[] = ['cast', 'style', 'shot'];

export function CreativeBriefPanel({ onUseBrief }: { onUseBrief: (prompt: string) => void }) {
  const {
    creativeBrief,
    attachCreativeBriefReferenceImage,
    updateCreativeBriefSlot,
    resetCreativeBrief,
  } = useMissionControlStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasConstraints = SLOT_ORDER.some((slot) => creativeBrief.slots[slot].value.trim());
  const isLoading = creativeBrief.status === 'loading';

  const attachFile = async (file: File | undefined) => {
    if (!file) return;
    await attachCreativeBriefReferenceImage(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const loadBriefIntoPrompt = () => {
    const lines = SLOT_ORDER
      .map((slot) => {
        const value = creativeBrief.slots[slot].value.trim();
        return value ? `${SLOT_LABELS[slot].label}: ${value}` : '';
      })
      .filter(Boolean);
    const imageLine = creativeBrief.referenceImage
      ? `Reference image attached: ${creativeBrief.referenceImage.name}`
      : 'No reference image attached';
    const prompt = [
      'Creative brief for confirmation before creating in PIE:',
      imageLine,
      ...lines,
      'Confirm these constraints before you create or spawn anything.',
    ].join('\n');
    onUseBrief(prompt);
  };

  return (
    <div className="creative-brief-card" aria-label="Creative Brief">
      <div className="creative-brief-head">
        <div>
          <span className="creative-brief-eyebrow">Creative Brief</span>
          <h3>Reference constraints</h3>
        </div>
        <span className={`brief-status ${creativeBrief.status}`}>
          {briefStatusLabel(creativeBrief.status)}
        </span>
      </div>

      <div className="brief-reference-row">
        <button
          type="button"
          className="secondary"
          disabled={isLoading}
          onClick={() => fileInputRef.current?.click()}
        >
          {creativeBrief.referenceImage ? 'Replace ref image' : 'Attach ref image'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="brief-file-input"
          onChange={(event) => void attachFile(event.currentTarget.files?.[0])}
        />
        {creativeBrief.referenceImage ? (
          <span className="brief-image-name" title={creativeBrief.referenceImage.name}>
            {creativeBrief.referenceImage.name}
          </span>
        ) : (
          <span className="brief-image-empty">No sketch attached</span>
        )}
      </div>

      {creativeBrief.referenceImage && (
        <div className="brief-preview-row">
          <img src={creativeBrief.referenceImage.previewUrl} alt="Attached reference" />
          <p>{creativeBrief.message}</p>
        </div>
      )}

      {!creativeBrief.referenceImage && creativeBrief.status !== 'error' && (
        <p className="brief-empty-state">{creativeBrief.message}</p>
      )}
      {creativeBrief.status === 'error' && (
        <p className="brief-error" role="alert">{creativeBrief.error || creativeBrief.message}</p>
      )}

      <div className="brief-slot-grid">
        {SLOT_ORDER.map((slot) => {
          const meta = SLOT_LABELS[slot];
          const value = creativeBrief.slots[slot].value;
          return (
            <label key={slot} className={`brief-slot ${creativeBrief.slots[slot].state}`}>
              <span>
                {meta.label}
                <em>{slotStateLabel(creativeBrief.slots[slot].state)}</em>
              </span>
              <input
                type="text"
                value={value}
                placeholder={meta.placeholder}
                onChange={(event) => updateCreativeBriefSlot(slot, event.target.value)}
              />
            </label>
          );
        })}
      </div>

      <div className="brief-actions">
        <button type="button" onClick={loadBriefIntoPrompt} disabled={!creativeBrief.referenceImage && !hasConstraints}>
          Load into prompt
        </button>
        <button type="button" onClick={resetCreativeBrief} disabled={isLoading}>
          Clear
        </button>
      </div>
    </div>
  );
}

function briefStatusLabel(status: string) {
  switch (status) {
    case 'loading':
      return 'Loading';
    case 'awaiting_vision_caption':
      return 'Awaiting vision';
    case 'caption_received':
      return 'Caption received';
    case 'manual_constraints_applied':
      return 'Constrained';
    case 'error':
      return 'Error';
    default:
      return 'Empty';
  }
}

function slotStateLabel(state: string) {
  switch (state) {
    case 'pending':
      return 'pending';
    case 'constrained':
      return 'set';
    case 'error':
      return 'needs review';
    default:
      return 'empty';
  }
}
