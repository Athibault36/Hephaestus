import { useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { AssetInfo } from '../store/missionControlStore';

const CLASS_FILTERS = [
  { id: '', label: 'All' },
  { id: 'SkeletalMesh', label: 'Skeletal' },
  { id: 'AnimMontage', label: 'Montage' },
  { id: 'AnimSequence', label: 'Anim' },
  { id: 'StaticMesh', label: 'Static' },
];

export function AssetBrowser() {
  const { assets, searchAssets, spawnAsset } = useMissionControlStore();
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
          placeholder="Search /Game assets…"
          onKeyDown={(e) => e.key === 'Enter' && onSearch()}
        />
        <button type="button" onClick={onSearch}>Search</button>
      </div>
      <div className="asset-grid" role="grid" aria-label="Asset Browser">
        {assets.length === 0 ? (
          <div className="asset-empty" style={{ gridColumn: '1 / -1' }}>
            <span className="empty-icon">📦</span>
            <p>No assets yet</p>
            <p className="empty-hint">Search by name (dog, cube, idle…)</p>
          </div>
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
