#!/usr/bin/env node
/**
 * Installs the upstream marketing skills listed in config/upstream-skills.yaml into .claude/skills/.
 *
 * - Fetches exactly one commit of the upstream repository with git (no npm package, no upstream script is run).
 * - Copies each selected skill folder unchanged, plus the upstream LICENSE.
 * - Removes upstream skills that were installed before but are no longer selected (custom skills are never touched:
 *   only names recorded in the previous lock file can be removed).
 * - Writes integrations/marketingskills/upstream-lock.json with the commit, upstream version and a sha256 per file,
 *   so scripts/validate.mjs can detect local edits to upstream files.
 *
 * Usage:  node scripts/sync-upstream-skills.mjs [--ref <commit|branch>] [--source <local clone>] [--dry-run]
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const dryRun = args.includes('--dry-run');

const config = YAML.parse(fs.readFileSync(path.join(ROOT, 'config/upstream-skills.yaml'), 'utf8'));
const ref = opt('--ref') ?? config.ref;
const installDir = path.join(ROOT, config.install_dir);
const lockPath = path.join(ROOT, config.lock_file);
const NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/;

for (const s of config.skills) if (!NAME.test(s)) throw new Error(`Invalid skill name in config: ${s}`);

function git(cwd, ...a) { return execFileSync('git', a, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim(); }

let source = opt('--source');
let tmp;
if (!source) {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'marketingskills-'));
  console.log(`Fetching ${config.repository} @ ${ref}`);
  git(tmp, 'init', '-q');
  git(tmp, 'remote', 'add', 'origin', config.repository);
  git(tmp, 'fetch', '-q', '--depth', '1', 'origin', ref);
  git(tmp, 'checkout', '-q', 'FETCH_HEAD');
  source = tmp;
}
const commit = git(source, 'rev-parse', 'HEAD');
let version = null;
try { version = JSON.parse(fs.readFileSync(path.join(source, '.claude-plugin/plugin.json'), 'utf8')).version; } catch { /* optional */ }

// Skill test material (evals/) is not installed: it is only used to test skills upstream, and its sample prompts
// contain fake credentials that trip the repo's secret scan (gitleaks), see PR #326.
const EXCLUDE_DIRS = new Set(['evals']);
const hashFile = (p) => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function walk(dir, base = dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isSymbolicLink()) throw new Error(`Refusing symlink in upstream skill: ${p}`);
    if (e.isDirectory() && EXCLUDE_DIRS.has(e.name)) return [];
    return e.isDirectory() ? walk(p, base) : [path.relative(base, p).split(path.sep).join('/')];
  });
}

const previous = fs.existsSync(lockPath) ? JSON.parse(fs.readFileSync(lockPath, 'utf8')) : { skills: {} };
const lock = { repository: config.repository, ref_requested: ref, commit, version, synced_at: new Date().toISOString(), skills: {} };

for (const name of config.skills) {
  const from = path.join(source, 'skills', name);
  if (!fs.existsSync(path.join(from, 'SKILL.md'))) throw new Error(`Upstream skill not found at ${commit}: ${name}`);
  const to = path.join(installDir, name);
  const files = {};
  for (const rel of walk(from)) files[rel] = hashFile(path.join(from, rel));
  lock.skills[name] = { files };
  if (dryRun) { console.log(`would install ${name} (${Object.keys(files).length} files)`); continue; }
  fs.rmSync(to, { recursive: true, force: true });
  fs.cpSync(from, to, { recursive: true, filter: (src) => !EXCLUDE_DIRS.has(path.basename(src)) || !fs.statSync(src).isDirectory() });
  console.log(`installed ${name} (${Object.keys(files).length} files)`);
}

for (const old of Object.keys(previous.skills ?? {})) {
  if (config.skills.includes(old)) continue;
  console.log(`${dryRun ? 'would remove' : 'removed'} ${old} (no longer selected)`);
  if (!dryRun) fs.rmSync(path.join(installDir, old), { recursive: true, force: true });
}

if (!dryRun) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  fs.copyFileSync(path.join(source, 'LICENSE'), path.join(ROOT, config.license_copy));
  fs.writeFileSync(lockPath, JSON.stringify(lock, null, 2) + '\n');
}
if (tmp) fs.rmSync(tmp, { recursive: true, force: true });

console.log(`\n${config.skills.length} upstream skills ${dryRun ? 'checked' : 'installed'} from commit ${commit}${version ? ` (v${version})` : ''}.`);
if (commit !== config.ref) console.log(`Note: config ref is ${config.ref}. To pin this result, set ref: ${commit} in config/upstream-skills.yaml.`);
