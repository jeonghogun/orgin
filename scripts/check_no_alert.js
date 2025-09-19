#!/usr/bin/env node

import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(scriptDir, '../app/frontend/src');
const JS_EXTENSIONS = new Set(['.js', '.jsx']);
const matches = [];

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walk(fullPath);
      continue;
    }
    const ext = path.extname(entry.name).toLowerCase();
    if (!JS_EXTENSIONS.has(ext)) continue;
    const contents = await readFile(fullPath, 'utf8');
    if (/\balert\s*\(/.test(contents) || /window\.alert\s*\(/.test(contents)) {
      matches.push(fullPath);
    }
  }
}

try {
  await walk(SRC_ROOT);
  if (matches.length > 0) {
    console.error('Disallowed alert() usage detected in the following files:');
    for (const file of matches) {
      console.error(` - ${path.relative(process.cwd(), file)}`);
    }
    process.exit(1);
  }
  console.log('No disallowed alert() usage detected.');
} catch (err) {
  console.error('Failed to scan for alert() usage:', err);
  process.exit(2);
}
