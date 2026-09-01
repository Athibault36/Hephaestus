import React from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function ActorActions() {
  const { selectedActor, playLocomotion, frameActor, destroyActor } = useMissionControlStore();

  if (!selectedActor) {
    return <p className="actor-actions-hint">Select an actor in the outliner</p>;
  }

  return (
    <div className="actor-actions">
      <code className="actor-path" title={selectedActor}>{selectedActor}</code>
      <div className="actor-action-row">
        <button type="button" onClick={() => playLocomotion('idle')}>Play idle</button>
        <button type="button" onClick={() => playLocomotion('walk')}>Play walk</button>
        <button type="button" onClick={() => playLocomotion('run')}>Play run</button>
        <button type="button" onClick={() => frameActor()}>Frame</button>
        <button type="button" className="danger" onClick={() => destroyActor()}>Destroy</button>
      </div>
    </div>
  );
}
