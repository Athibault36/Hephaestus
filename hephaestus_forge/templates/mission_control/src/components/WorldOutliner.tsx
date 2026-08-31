import React from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { ActorInfo } from '../store/missionControlStore';

export function WorldOutliner() {
  const { actors, selectedActor, selectActor } = useMissionControlStore();

  const getActorIcon = (className: string) => {
    if (className.includes('StaticMesh')) return '📦';
    if (className.includes('SkeletalMesh')) return '🦴';
    if (className.includes('Blueprint')) return '🔷';
    if (className.includes('Light')) return '💡';
    if (className.includes('Camera')) return '🎥';
    if (className.includes('Particle')) return '✨';
    if (className.includes('Foliage')) return '🌿';
    if (className.includes('Landscape')) return '🏔️';
    if (className.includes('Water')) return '🌊';
    return '🎭';
  };

  const formatVector = (v: [number, number, number]) => {
    return `[${v[0].toFixed(1)}, ${v[1].toFixed(1)}, ${v[2].toFixed(1)}]`;
  };

  return (
    <div className="actor-tree" role="tree" aria-label="World Outliner">
      {actors.length === 0 ? (
        <div className="outliner-empty">
          <span className="empty-icon">🌍</span>
          <p>No actors in scene</p>
          <p className="empty-hint">Connect to UE to populate</p>
        </div>
      ) : (
        <ul className="actor-list">
          {actors.map((actor: ActorInfo) => (
            <li
              key={actor.path}
              className={`actor-item ${actor.path === selectedActor ? 'selected' : ''}`}
              onClick={() => selectActor(actor.path)}
              role="treeitem"
              aria-selected={actor.path === selectedActor}
            >
              <span className="actor-icon">{getActorIcon(actor.class)}</span>
              <span className="actor-name" title={actor.path}>
                {actor.name}
              </span>
              <span className="actor-class">{actor.class}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}