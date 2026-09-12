import { useMissionControlStore } from '../store/missionControlStore';
import { PanelState } from './PanelState';

export function ActorActions() {
  const { actors, actorsError, actorsLoading, isConnected, selectedActor, playLocomotion, playMontage, frameActor, destroyActor } = useMissionControlStore();

  if (!selectedActor) {
    if (!isConnected || actorsLoading || actorsError || actors.length === 0) return null;
    return (
      <PanelState
        tone="empty"
        icon="🎬"
        title="No actor selected"
        message="Select an actor in the outliner to frame, animate, or remove it from PIE."
      />
    );
  }

  return (
    <div className="actor-actions">
      <code className="actor-path" title={selectedActor}>{selectedActor}</code>
      <div className="actor-action-row">
        <button type="button" onClick={() => playLocomotion('idle')}>Play idle</button>
        <button type="button" onClick={() => playLocomotion('walk')}>Play walk</button>
        <button type="button" onClick={() => playLocomotion('run')}>Play run</button>
        <button type="button" onClick={() => playMontage()}>Play montage</button>
        <button type="button" onClick={() => frameActor()}>Frame</button>
        <button type="button" className="danger" onClick={() => destroyActor()}>Destroy</button>
      </div>
    </div>
  );
}
