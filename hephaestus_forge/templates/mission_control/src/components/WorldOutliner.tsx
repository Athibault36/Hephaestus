import React, { useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { ActorInfo } from '../store/missionControlStore';
import { PanelState } from './PanelState';

export function WorldOutliner() {
  const { actors, actorsLoading, actorsError, isConnected, selectedActor, selectActor, playLocomotion, frameActor, destroyActor } = useMissionControlStore();
  const [menu, setMenu] = useState<{ x: number; y: number; path: string } | null>(null);

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

  const onContextMenu = (e: React.MouseEvent, path: string) => {
    e.preventDefault();
    selectActor(path);
    setMenu({ x: e.clientX, y: e.clientY, path });
  };

  const runAction = async (action: 'idle' | 'walk' | 'run' | 'frame' | 'destroy') => {
    if (!menu) return;
    selectActor(menu.path);
    setMenu(null);
    if (action === 'frame') await frameActor();
    else if (action === 'destroy') await destroyActor();
    else await playLocomotion(action);
  };

  return (
    <div className="actor-tree" role="tree" aria-label="World Outliner">
      {!isConnected ? (
        <PanelState
          tone="offline"
          icon="🌍"
          title="World unavailable"
          message="Start PIE with HephaestusBridge; actors will appear after the bridge connects."
        />
      ) : actorsLoading && actors.length === 0 ? (
        <PanelState tone="loading" icon="🌍" title="Loading world" message="Reading actor names and details from the UE bridge." />
      ) : actorsError && actors.length === 0 ? (
        <PanelState tone="error" icon="⚠️" title="Could not load actors" message={actorsError} />
      ) : actors.length === 0 ? (
        <PanelState
          tone="empty"
          icon="🌍"
          title="Scene is empty"
          message="No PIE actors were returned yet. Author into PIE or spawn an asset to begin blocking the shot."
        />
      ) : (
        <ul className="actor-list">
          {actors.map((actor: ActorInfo) => (
            <li
              key={actor.path}
              className={`actor-item ${actor.path === selectedActor ? 'selected' : ''}`}
              onClick={() => selectActor(actor.path)}
              onContextMenu={(e) => onContextMenu(e, actor.path)}
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
      {menu && (
        <div className="outliner-context-menu" style={{ top: menu.y, left: menu.x }}>
          <button type="button" onClick={() => runAction('idle')}>Play idle</button>
          <button type="button" onClick={() => runAction('walk')}>Play walk</button>
          <button type="button" onClick={() => runAction('run')}>Play run</button>
          <button type="button" onClick={() => runAction('frame')}>Frame</button>
          <button type="button" className="danger" onClick={() => runAction('destroy')}>Destroy</button>
        </div>
      )}
    </div>
  );
}
