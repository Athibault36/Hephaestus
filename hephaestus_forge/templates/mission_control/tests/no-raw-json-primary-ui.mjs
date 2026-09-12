import { readFileSync } from 'node:fs';
import { relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const primaryUiFiles = [
  'src/MissionControl.tsx',
  'src/components/ActorActions.tsx',
  'src/components/AgentConsole.tsx',
  'src/components/AssetBrowser.tsx',
  'src/components/ChainOfThought.tsx',
  'src/components/PanelState.tsx',
  'src/components/PerformanceMonitor.tsx',
  'src/components/ViewportStream.tsx',
  'src/components/VoiceConsole.tsx',
  'src/components/WorldOutliner.tsx',
];

const disallowedPatterns = [
  { label: 'JSON.stringify rendered in TSX', pattern: /JSON\.stringify\s*\(/ },
  { label: 'raw preformatted data block', pattern: /<pre[\s>]/ },
];

const storeErrorPatterns = [
  { label: 'unsafe object-to-string error formatting', pattern: /String\([^)]*(?:error|llm_error)[^)]*\)/ },
];

const failures = [];

for (const file of primaryUiFiles) {
  const absolute = resolve(root, file);
  const source = readFileSync(absolute, 'utf8');
  for (const { label, pattern } of disallowedPatterns) {
    if (pattern.test(source)) {
      failures.push(`${relative(root, absolute)}: ${label}`);
    }
  }
}

const storeSource = readFileSync(resolve(root, 'src/store/missionControlStore.ts'), 'utf8');
for (const { label, pattern } of storeErrorPatterns) {
  if (pattern.test(storeSource)) {
    failures.push(`src/store/missionControlStore.ts: ${label}`);
  }
}

if (failures.length > 0) {
  console.error('Primary Mission Control UI must not render raw JSON/data dumps:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Primary Mission Control UI raw JSON scan passed.');
