#!/usr/bin/env node
/**
 * Validates the Marketing OS. Run with `npm run validate` (or `npm test`, which also runs the unit tests).
 *
 * Checks: required files, YAML syntax, config consistency (organic scope, gates, workflows, channels, products),
 * skill frontmatter and layout (Claude Code + Agent Skills conventions), upstream skill hashes against the lock,
 * internal links and path references, and a secrets scan. Exit code 1 if any check fails.
 */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import YAML from 'yaml';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export const CUSTOM_SKILLS = ['marketing-orchestrator', 'product-discovery', 'campaign-operations', 'campaign-review'];
const SKILL_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const RESERVED_SKILL_NAMES = ['synced', 'anthropic-skills'];
const LISTING_LIMIT = 1536;      // Claude Code: description + when_to_use is cut at 1,536 characters in the listing
const PORTABLE_LIMIT = 1024;     // Agent Skills spec limit; above this some clients reject the skill
const SKIP_DIRS = new Set(['node_modules', '.git', '_sources']);
const TEXT_EXT = new Set(['.md', '.yaml', '.yml', '.json', '.mjs', '.js', '.ts', '.txt', '.csv', '.html', '.css', '.scss', '.svg', '']);

export const REQUIRED = [
  'README.md', 'CLAUDE.md', 'CHANGELOG.md', '.gitignore', 'package.json',
  'config/marketing-config.yaml', 'config/channels.yaml', 'config/workflow-rules.yaml', 'config/upstream-skills.yaml', 'config/sources.yaml',
  'scripts/sync-sources.mjs',
  'knowledge/company/company-profile.md', 'knowledge/company/brand-identity.md', 'knowledge/company/brand-voice.md',
  'knowledge/products/README.md',
  ...['product-profile', 'product-positioning', 'target-audience', 'messaging-matrix', 'proof-points'].map((f) => `knowledge/products/product-template/${f}.md`),
  'knowledge/audience/audience-research.md', 'knowledge/audience/buyer-personas.md', 'knowledge/audience/customer-pain-points.md',
  'knowledge/glossary/marketing-glossary.md',
  'research/source-log.md', 'research/discrepancies.md',
  'research/market-research/README.md', 'research/competitor-analysis/README.md', 'research/customer-insights/README.md',
  'strategy/marketing-principles.md', 'strategy/positioning-framework.md', 'strategy/content-strategy.md', 'strategy/channel-strategy.md',
  ...['campaign-brief', 'research-summary', 'strategy', 'messaging-matrix', 'content-calendar', 'landing-page-brief', 'seo-plan',
    'distribution-plan', 'measurement-plan', 'experiment-backlog', 'approvals', 'performance-report'].map((f) => `campaigns/campaign-template/${f}.md`),
  'campaigns/campaign-template/assets/README.md',
  ...['product-discovery', 'competitor-analysis', 'content-brief', 'social-post', 'video-brief', 'landing-page', 'campaign-review'].map((f) => `templates/${f}-template.md`),
  'analytics/metrics-dictionary.md', 'analytics/measurement-framework.md', 'analytics/reporting-template.md',
  'integrations/README.md', 'integrations/mcp-registry.md', 'integrations/setup-guides/marketingskills.md',
  'integrations/marketingskills/LICENSE', 'integrations/marketingskills/upstream-lock.json',
  '.agents/product-marketing.md',
  ...CUSTOM_SKILLS.map((s) => `.claude/skills/${s}/SKILL.md`),
];

// Secret patterns. Built from parts so this file doesn't match itself.
export const SECRET_PATTERNS = [
  ['AWS access key', new RegExp('AKI' + 'A[0-9A-Z]{16}')],
  ['GitHub token', new RegExp('gh' + '[pousr]_[A-Za-z0-9]{36,}')],
  ['GitHub fine-grained token', new RegExp('github' + '_pat_[A-Za-z0-9_]{40,}')],
  ['OpenAI/Anthropic-style key', new RegExp('\\bsk-' + '(ant-)?[A-Za-z0-9_-]{32,}')],
  ['Google API key', new RegExp('AI' + 'za[0-9A-Za-z_-]{35}')],
  ['Slack token', new RegExp('xox' + '[baprs]-[A-Za-z0-9-]{10,}')],
  ['Private key block', new RegExp('-----BEGIN ' + '(RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')],
  ['Assigned credential', new RegExp('(api[_-]?key|client[_-]?secret|secret|password|passwd|(access|auth|bearer|refresh)?[_-]?token)\\s*[:=]\\s*["\'][A-Za-z0-9/+_\\-]{16,}["\']', 'i')],
];

export function scanSecrets(text) {
  return SECRET_PATTERNS.filter(([, re]) => re.test(text)).map(([name]) => name);
}

/** Returns { data, body, error }. Frontmatter must start on the first line (Claude Code requirement). */
export function parseFrontmatter(text) {
  const t = text.replace(/^﻿/, '').replace(/\r\n/g, '\n'); // CRLF checkouts parse the same as LF
  if (!t.startsWith('---\n') && !t.startsWith('---\r\n')) return { error: 'frontmatter must start with --- on the first line' };
  const end = t.indexOf('\n---', 4);
  if (end < 0) return { error: 'frontmatter has no closing ---' };
  const raw = t.slice(t.indexOf('\n') + 1, end);
  const doc = YAML.parseDocument(raw);
  if (doc.errors.length) return { error: `frontmatter YAML: ${doc.errors[0].message.split('\n')[0]}` };
  const data = doc.toJSON();
  if (!data || typeof data !== 'object') return { error: 'frontmatter is empty' };
  return { data, body: t.slice(end + 4) };
}

/** Problems with one skill folder: [{level: 'fail'|'warn', msg}] */
export function checkSkillDir(dir) {
  const out = [];
  const dirName = path.basename(dir);
  const file = path.join(dir, 'SKILL.md');
  if (!fs.existsSync(file)) return [{ level: 'fail', msg: `${dirName}: no SKILL.md` }];
  const fm = parseFrontmatter(fs.readFileSync(file, 'utf8'));
  if (fm.error) return [{ level: 'fail', msg: `${dirName}: ${fm.error}` }];
  const { name, description, when_to_use: whenToUse } = fm.data;
  if (name === undefined) out.push({ level: 'warn', msg: `${dirName}: no name (Claude Code falls back to the folder name)` });
  else if (name !== dirName) out.push({ level: 'fail', msg: `${dirName}: name "${name}" does not match its folder` });
  const effective = name ?? dirName;
  if (!SKILL_NAME.test(effective) || effective.length > 64) out.push({ level: 'fail', msg: `${dirName}: name must be lowercase letters, digits and single hyphens, at most 64 characters` });
  if (RESERVED_SKILL_NAMES.some((r) => effective === r || effective.startsWith(`${r}:`))) out.push({ level: 'fail', msg: `${dirName}: reserved name` });
  if (typeof description !== 'string' || !description.trim()) out.push({ level: 'fail', msg: `${dirName}: description missing` });
  else {
    const len = description.length + (typeof whenToUse === 'string' ? whenToUse.length : 0);
    if (len > LISTING_LIMIT) out.push({ level: 'fail', msg: `${dirName}: description is ${len} characters; Claude Code truncates at ${LISTING_LIMIT}` });
    else if (description.length > PORTABLE_LIMIT) out.push({ level: 'warn', msg: `${dirName}: description is ${description.length} characters (over the ${PORTABLE_LIMIT} Agent Skills limit; fine in Claude Code)` });
    if (/[<>]/.test(description)) out.push({ level: 'warn', msg: `${dirName}: description contains < or >` });
  }
  const lines = fm.body.split('\n').length;
  if (lines > 500) out.push({ level: 'warn', msg: `${dirName}: SKILL.md body is ${lines} lines (recommended under 500)` });
  return out;
}

function walk(dir, filter = () => true) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, filter));
    else if (filter(p)) out.push(p);
  }
  return out;
}
const rel = (root, p) => path.relative(root, p).split(path.sep).join('/');
// Line-ending neutral: a text file hashes the same with CRLF or LF, so Windows checkouts match the lock (PR #326).
const sha256 = (p) => {
  const b = fs.readFileSync(p);
  const text = !b.includes(0);
  return createHash('sha256').update(text ? b.toString('utf8').replace(/\r\n/g, '\n') : b).digest('hex');
};

const PATH_PREFIXES = ['config/', 'knowledge/', 'research/', 'strategy/', 'workflows/', 'campaigns/', 'templates/', 'analytics/',
  'integrations/', 'scripts/', 'tests/', '.claude/', '.agents/', 'LinkedIn/', 'ProcurePilot/', '../'];
const PLACEHOLDER = /[<>*{}|]|YYYY|\.\.\.|\bv<|\bN\b/;

/** Path references in a markdown file: markdown links (strict) and backticked paths with a known prefix. */
export function pathRefs(text) {
  const refs = [];
  for (const m of text.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
    const target = m[1].split('#')[0];
    if (!target || /^[a-z]+:/i.test(target)) continue;
    refs.push({ ref: decodeURI(target), kind: 'link' });
  }
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const v = m[1].trim();
    if (!PATH_PREFIXES.some((p) => v.startsWith(p)) || PLACEHOLDER.test(v) || /\s(--|&&)\s/.test(v) || v.includes('=')) continue;
    refs.push({ ref: v.replace(/\\/g, '/'), kind: 'path' });
  }
  return refs;
}

export function runChecks(root = ROOT) {
  const results = [];
  const add = (check, status, detail = '') => results.push({ check, status, detail });
  const exists = (p) => fs.existsSync(path.join(root, p));

  // 1. Required files
  const missing = REQUIRED.filter((p) => !exists(p));
  add('Required files and directories', missing.length ? 'fail' : 'pass', missing.length ? `missing: ${missing.join(', ')}` : `${REQUIRED.length} present`);

  // 2. YAML syntax
  const cfg = {};
  const yamlFiles = walk(path.join(root, 'config'), (p) => /\.ya?ml$/.test(p));
  const yamlErrors = [];
  for (const f of yamlFiles) {
    const doc = YAML.parseDocument(fs.readFileSync(f, 'utf8'));
    if (doc.errors.length) yamlErrors.push(`${rel(root, f)}: ${doc.errors[0].message.split('\n')[0]}`);
    else cfg[path.basename(f).replace(/\.ya?ml$/, '')] = doc.toJSON();
  }
  add('YAML syntax (config/)', yamlErrors.length ? 'fail' : 'pass', yamlErrors.join('; ') || `${yamlFiles.length} files parse`);

  const mc = cfg['marketing-config'] ?? {};
  const ch = cfg.channels ?? {};
  const wr = cfg['workflow-rules'] ?? {};
  const us = cfg['upstream-skills'] ?? {};
  const skillsDir = path.join(root, '.claude/skills');
  const installedSkills = fs.existsSync(skillsDir) ? fs.readdirSync(skillsDir, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name) : [];

  // 3. Organic-only scope
  const scopeIssues = [];
  if (mc.marketing_model?.scope !== 'organic') scopeIssues.push('marketing_model.scope is not "organic"');
  if (mc.marketing_model?.paid_advertising !== false) scopeIssues.push('marketing_model.paid_advertising is not false');
  for (const [id, c] of Object.entries(ch.channels ?? {})) if (c.paid !== false) scopeIssues.push(`channel ${id} is not marked paid: false`);
  for (const id of mc.channels?.enabled ?? []) if (!ch.channels?.[id]) scopeIssues.push(`enabled channel ${id} not defined in channels.yaml`);
  const paidSkills = ['ads', 'ad-creative'].filter((s) => installedSkills.includes(s));
  if (paidSkills.length) scopeIssues.push(`paid-media skills installed: ${paidSkills.join(', ')}`);
  if (!/Organic only/i.test(fs.readFileSync(path.join(root, 'CLAUDE.md'), 'utf8'))) scopeIssues.push('CLAUDE.md does not state the organic-only rule');
  add('Organic-only scope is consistent', scopeIssues.length ? 'fail' : 'pass', scopeIssues.join('; ') || 'config, channels, skills and CLAUDE.md agree');

  // 4. Approval gates and workflows
  const gateIssues = [];
  const gates = wr.approval_gates ?? {};
  for (const g of ['G-positioning', 'G-campaign-strategy', 'G-claims', 'G-asset', 'G-publish', 'G-live-change', 'G-integration']) if (!gates[g]) gateIssues.push(`gate ${g} missing`);
  for (const [id, w] of Object.entries(wr.workflows ?? {})) {
    if (!w.doc || !exists(w.doc)) gateIssues.push(`workflow ${id}: doc ${w.doc} missing`);
    if (!installedSkills.includes(w.skill)) gateIssues.push(`workflow ${id}: skill ${w.skill} not installed`);
    for (const g of w.gates ?? []) if (!gates[g]) gateIssues.push(`workflow ${id}: unknown gate ${g}`);
    for (const d of w.depends_on ?? []) if (!wr.workflows[d]) gateIssues.push(`workflow ${id}: unknown dependency ${d}`);
  }
  const qcIds = Object.keys(wr.quality_checks ?? {});
  const reviewTpl = exists('templates/campaign-review-template.md') ? fs.readFileSync(path.join(root, 'templates/campaign-review-template.md'), 'utf8') : '';
  for (const q of qcIds) if (!reviewTpl.includes(q)) gateIssues.push(`quality check ${q} missing from the review template`);
  if (!/Approval before action/.test(fs.readFileSync(path.join(root, 'CLAUDE.md'), 'utf8'))) gateIssues.push('CLAUDE.md lacks the approval rule');
  for (const s of ['publish', 'live-website-change']) if (!(mc.approvals?.required_before ?? []).includes(s)) gateIssues.push(`approvals.required_before lacks ${s}`);
  add('Approval gates and workflows', gateIssues.length ? 'fail' : 'pass', gateIssues.join('; ') || `${Object.keys(gates).length} gates, ${Object.keys(wr.workflows ?? {}).length} workflows, ${qcIds.length} quality checks wired`);

  // 5. Channels reference real skills and templates
  const chIssues = [];
  for (const [id, c] of Object.entries(ch.channels ?? {})) {
    for (const s of c.upstream_skills ?? []) if (!installedSkills.includes(s)) chIssues.push(`${id}: skill ${s} not installed`);
    for (const t of c.templates ?? []) if (!exists(t)) chIssues.push(`${id}: template ${t} missing`);
  }
  add('Channel definitions reference installed skills and templates', chIssues.length ? 'fail' : 'pass', chIssues.join('; ') || `${Object.keys(ch.channels ?? {}).length} channels`);

  // 6. Product registry
  const prodIssues = [];
  const registry = exists('knowledge/products/README.md') ? fs.readFileSync(path.join(root, 'knowledge/products/README.md'), 'utf8') : '';
  const statuses = ['not-started', 'discovery-in-progress', 'discovery-report-ready', 'positioning-approved', 'active'];
  for (const p of mc.products ?? []) {
    if (!statuses.includes(p.onboarding_status)) prodIssues.push(`${p.id}: unknown onboarding_status ${p.onboarding_status}`);
    if (!registry.includes(`| ${p.id} |`)) prodIssues.push(`${p.id}: not in knowledge/products/README.md registry`);
    if (p.onboarding_status !== 'not-started' && !exists(p.knowledge_dir)) prodIssues.push(`${p.id}: ${p.knowledge_dir} missing for status ${p.onboarding_status}`);
    if (p.folder && !String(p.knowledge_dir ?? '').startsWith(`${p.folder}/`)) prodIssues.push(`${p.id}: knowledge_dir should sit inside the product folder ${p.folder}/`);
    for (const s of p.sources ?? []) if (!cfg.sources?.sources?.[s]) prodIssues.push(`${p.id}: source ${s} not in config/sources.yaml`);
  }
  add('Product registry consistent', prodIssues.length ? 'fail' : 'pass', prodIssues.join('; ') || `${(mc.products ?? []).length} product(s)`);

  // 7. Skill frontmatter and layout
  const skillProblems = installedSkills.flatMap((s) => checkSkillDir(path.join(skillsDir, s)));
  const lockPath = path.join(root, us.lock_file ?? 'integrations/marketingskills/upstream-lock.json');
  const lock = fs.existsSync(lockPath) ? JSON.parse(fs.readFileSync(lockPath, 'utf8')) : { skills: {} };
  const upstreamNames = Object.keys(lock.skills ?? {});
  for (const c of CUSTOM_SKILLS) if (upstreamNames.includes(c)) skillProblems.push({ level: 'fail', msg: `custom skill ${c} collides with an upstream skill` });
  for (const s of installedSkills) if (!CUSTOM_SKILLS.includes(s) && !upstreamNames.includes(s)) skillProblems.push({ level: 'warn', msg: `${s}: neither custom nor in the upstream lock` });
  const sf = skillProblems.filter((p) => p.level === 'fail');
  const sw = skillProblems.filter((p) => p.level === 'warn');
  add('Skill frontmatter and layout', sf.length ? 'fail' : sw.length ? 'warn' : 'pass',
    [...sf, ...sw].map((p) => `${p.level}: ${p.msg}`).join('; ') || `${installedSkills.length} skills (${CUSTOM_SKILLS.length} custom, ${upstreamNames.length} upstream)`);

  // 8. Upstream skills match the lock and the config
  const upIssues = [];
  if (lock.commit !== us.ref) upIssues.push(`lock commit ${lock.commit} differs from config ref ${us.ref}`);
  for (const s of us.skills ?? []) if (!lock.skills?.[s]) upIssues.push(`${s} selected but not in the lock (run npm run skills:sync)`);
  for (const s of upstreamNames) if (!(us.skills ?? []).includes(s)) upIssues.push(`${s} in the lock but no longer selected (run npm run skills:sync)`);
  let filesChecked = 0;
  for (const [s, info] of Object.entries(lock.skills ?? {})) {
    const dir = path.join(skillsDir, s);
    if (!fs.existsSync(dir)) { upIssues.push(`${s} missing from .claude/skills`); continue; }
    const actual = new Set(walk(dir).map((p) => rel(dir, p)));
    for (const [f, h] of Object.entries(info.files)) {
      filesChecked++;
      if (!actual.has(f)) upIssues.push(`${s}/${f} missing`);
      else if (sha256(path.join(dir, f)) !== h) upIssues.push(`${s}/${f} edited locally (hash mismatch)`);
      actual.delete(f);
    }
    for (const extra of actual) upIssues.push(`${s}/${extra} not from upstream`);
  }
  add('Upstream skills match the pinned lock', upIssues.length ? 'fail' : 'pass', upIssues.join('; ') || `${upstreamNames.length} skills, ${filesChecked} files, commit ${String(lock.commit).slice(0, 7)}`);

  // 9. Links and path references (our files strictly; upstream files and generated mirrors only as information)
  const linkFails = [];
  const mirrorDirs = Object.values(cfg.sources?.sources ?? {}).filter((s) => s.mirror?.to).map((s) => path.join(root, s.mirror.to) + path.sep);
  const isMirror = (p) => mirrorDirs.some((d) => p.startsWith(d));
  let mirrorSkipped = 0;
  const upstreamDirs = upstreamNames.map((s) => path.join(skillsDir, s) + path.sep);
  const isUpstream = (p) => upstreamDirs.some((d) => p.startsWith(d));
  const mdFiles = walk(root, (p) => p.endsWith('.md'));
  let refsChecked = 0;
  let upstreamMissing = 0;
  for (const f of mdFiles) {
    if (isMirror(f)) { mirrorSkipped++; continue; }
    const text = fs.readFileSync(f, 'utf8');
    for (const { ref, kind } of pathRefs(text)) {
      const candidates = kind === 'link' || ref.startsWith('../') ? [path.resolve(path.dirname(f), ref), path.resolve(root, ref)] : [path.resolve(root, ref)];
      if (kind === 'link' && ref.startsWith('/')) continue;
      const ok = candidates.some((c) => fs.existsSync(c));
      if (isUpstream(f)) { if (!ok && kind === 'link') upstreamMissing++; continue; }
      refsChecked++;
      if (!ok) linkFails.push(`${rel(root, f)} → ${ref}`);
    }
  }
  add('Internal links and path references', linkFails.length ? 'fail' : 'pass',
    linkFails.join('; ') || `${refsChecked} references in ${mdFiles.filter((f) => !isUpstream(f) && !isMirror(f)).length} files resolve`
      + (upstreamMissing ? ` (info: ${upstreamMissing} links inside upstream skills point to skills or files not installed)` : '')
      + (mirrorSkipped ? ` (info: ${mirrorSkipped} files in generated mirrors not link-checked; their links point into the source repo)` : ''));

  // 10. Secrets
  const secretHits = [];
  const textFiles = walk(root, (p) => TEXT_EXT.has(path.extname(p).toLowerCase()) && fs.statSync(p).size < 2_000_000);
  for (const f of textFiles) {
    const hits = scanSecrets(fs.readFileSync(f, 'utf8'));
    if (hits.length) secretHits.push(`${rel(root, f)}: ${hits.join(', ')}`);
  }
  add('No secrets in files', secretHits.length ? 'fail' : 'pass', secretHits.join('; ') || `${textFiles.length} text files scanned`);

  return results;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const results = runChecks();
  const icon = { pass: 'PASS', warn: 'WARN', fail: 'FAIL' };
  for (const r of results) console.log(`${icon[r.status]}  ${r.check}${r.detail ? `\n      ${r.detail}` : ''}`);
  const fails = results.filter((r) => r.status === 'fail').length;
  console.log(`\n${results.length - fails}/${results.length} checks without failures.`);
  process.exit(fails ? 1 : 0);
}
