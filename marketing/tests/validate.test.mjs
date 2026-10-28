// Unit tests for scripts/validate.mjs. Run: npm test
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { checkSkillDir, parseFrontmatter, pathRefs, runChecks, scanSecrets } from '../scripts/validate.mjs';

function skill(name, frontmatter) {
  const dir = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'mos-test-')), name);
  fs.mkdirSync(dir);
  fs.writeFileSync(path.join(dir, 'SKILL.md'), frontmatter);
  return dir;
}
const fails = (problems) => problems.filter((p) => p.level === 'fail');

test('a valid skill has no failures', () => {
  assert.deepEqual(fails(checkSkillDir(skill('good-skill', '---\nname: good-skill\ndescription: Does a thing. Use when X.\n---\n# Body\n'))), []);
});

test('name must match the folder', () => {
  assert.equal(fails(checkSkillDir(skill('folder-a', '---\nname: folder-b\ndescription: x\n---\n'))).length, 1);
});

test('uppercase or underscore names fail', () => {
  assert.ok(fails(checkSkillDir(skill('Bad_Name', '---\nname: Bad_Name\ndescription: x\n---\n'))).length >= 1);
});

test('missing description fails', () => {
  assert.equal(fails(checkSkillDir(skill('no-desc', '---\nname: no-desc\n---\n'))).length, 1);
});

test('frontmatter must start on line one', () => {
  assert.match(parseFrontmatter('\n---\nname: x\n---\n').error, /first line/);
});

test('descriptions over the Claude Code listing limit fail', () => {
  const long = 'a'.repeat(1600);
  assert.equal(fails(checkSkillDir(skill('long-desc', `---\nname: long-desc\ndescription: ${long}\n---\n`))).length, 1);
});

test('secret scanner finds common key formats and ignores prose', () => {
  assert.deepEqual(scanSecrets('AKI' + 'AIOSFODNN7EXAMPLE'), ['AWS access key']);
  assert.ok(scanSecrets('api_key: "' + 'abcd1234efgh5678ijkl' + '"').includes('Assigned credential'));
  assert.deepEqual(scanSecrets('Never store an API key or password in this folder.'), []);
});

test('path references skip placeholders and commands', () => {
  const refs = pathRefs('See `knowledge/products/<id>/`, `npm run x -- y`, `config/channels.yaml` and [a](../README.md).');
  assert.deepEqual(refs.map((r) => r.ref).sort(), ['../README.md', 'config/channels.yaml']);
});

test('the Marketing OS itself passes every check', () => {
  const failed = runChecks().filter((r) => r.status === 'fail');
  assert.deepEqual(failed, []);
});
