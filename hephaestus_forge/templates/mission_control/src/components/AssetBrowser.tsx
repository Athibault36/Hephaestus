import { useMissionControlStore } from '../store/missionControlStore';
import { AssetInfo } from '../store/missionControlStore';

export function AssetBrowser() {
  const assets = useMissionControlStore((s) => s.assets);

  const getAssetIcon = (type: string) => {
    if (type.includes('StaticMesh')) return '📦';
    if (type.includes('SkeletalMesh')) return '🦴';
    if (type.includes('Material')) return '🎨';
    if (type.includes('Texture')) return '🖼️';
    if (type.includes('Blueprint')) return '🔷';
    if (type.includes('Niagara')) return '✨';
    if (type.includes('AnimSequence')) return '🎬';
    if (type.includes('Sound')) return '🔊';
    if (type.includes('Level')) return '🗺️';
    return '📄';
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  return (
    <div className="asset-grid" role="grid" aria-label="Asset Browser">
      {assets.length === 0 ? (
        <div className="asset-empty" style={{ gridColumn: '1 / -1' }}>
          <span className="empty-icon">📦</span>
          <p>No assets found</p>
          <p className="empty-hint">Connect to UE to browse assets</p>
        </div>
      ) : (
        assets.map((asset: AssetInfo) => (
          <div key={asset.path} className="asset-item" role="gridcell">
            <div className="asset-thumbnail">{getAssetIcon(asset.type)}</div>
            <span className="asset-name" title={asset.path}>{asset.name}</span>
            <span className="asset-type">{asset.type} • {formatSize(asset.size)}</span>
          </div>
        ))
      )}
    </div>
  );
}