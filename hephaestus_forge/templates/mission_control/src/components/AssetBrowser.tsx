import { useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { AssetInfo } from '../store/missionControlStore';
import { PanelState } from './PanelState';

const CLASS_FILTERS = [
  { id: '', label: 'All' },
  { id: 'SkeletalMesh', label: 'Skeletal' },
  { id: 'AnimMontage', label: 'Montage' },
  { id: 'AnimSequence', label: 'Anim' },
  { id: 'StaticMesh', label: 'Static' },
];

export function AssetBrowser() {
  const { assets, assetsLoading, assetsError, assetSearchAttempted, isConnected, searchAssets, spawnAsset } = useMissionControlStore();
  const [query, setQuery] = useState('');
  const [assetClass, setAssetClass] = useState('');

  const getAssetIcon = (type: string) => {
    if (type.includes('StaticMesh')) return '📦';
    if (type.includes('SkeletalMesh')) return '🦴';
    if (type.includes('Anim')) return '🎬';
    if (type.includes('Material')) return '🎨';
    return '📄';
  };

  const onSearch = () => {
    if (!isConnected || assetsLoading) return;
    searchAssets(query, assetClass || undefined);
  };

  return (
    <div className="asset-browser">
      <div className="asset-filter-row">
        {CLASS_FILTERS.map((f) => (
          <button
            key={f.id || 'all'}
            type="button"
            className={`asset-filter-chip ${assetClass === f.id ? 'active' : ''}`}
            onClick={() => setAssetClass(f.id)}
            disabled={!isConnected || assetsLoading}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="asset-search-row">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={isConnected ? 'Search /Game assets…' : 'Connect PIE before searching assets'}
          disabled={!isConnected || assetsLoading}
          onKeyDown={(e) => e.key === 'Enter' && onSearch()}
        />
        <button type="button" onClick={onSearch} disabled={!isConnected || assetsLoading}>Search</button>
      </div>
      <div className="asset-grid" role="grid" aria-label="Asset Browser">
        {!isConnected ? (
          <PanelState
            tone="offline"
            icon="📦"
            title="Asset search offline"
            message="Asset search uses the UE bridge. Start PIE before browsing project assets."
          />
        ) : assetsLoading ? (
          <PanelState tone="loading" icon="📦" title="Searching assets" message="Mission Control is asking UE for matching project assets." />
        ) : assetsError ? (
          <PanelState tone="error" icon="⚠️" title="Asset search failed" message={assetsError} />
        ) : assets.length === 0 ? (
          <PanelState
            tone="empty"
            icon="📦"
            title={assetSearchAttempted ? 'No matching assets' : 'Search project assets'}
            message={assetSearchAttempted ? 'Try a broader name or a different asset type filter.' : 'Search by name, type, or animation cue to find assets you can spawn into PIE.'}
          />
        ) : (
          assets.map((asset: AssetInfo) => (
            <div
              key={asset.path}
              className="asset-item"
              role="gridcell"
              title={`${asset.path} — double-click to spawn`}
              onDoubleClick={() => spawnAsset(asset.path)}
            >
              <div className="asset-thumbnail">{getAssetIcon(asset.type)}</div>
              <span className="asset-name">{asset.name}</span>
              <span className="asset-type">{asset.type}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
