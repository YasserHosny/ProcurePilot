#!/usr/bin/env node
/**
 * Creates a campaign or product folder from its template.
 *   node scripts/new-from-template.mjs product procurepilot ProcurePilot   → ProcurePilot/knowledge/
 *   node scripts/new-from-template.mjs campaign 2026-11-procurepilot-pilot-launch
 * A campaign whose product part (after YYYY-MM-) is a product id in config/marketing-config.yaml goes to that
 * product's folder (<folder>/campaigns/<id>); other campaigns go to campaigns/<id>.
 * Refuses to overwrite an existing folder.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [kind, id, folderArg] = process.argv.slice(2);
const today = new Date().toISOString().slice(0, 10);
const config = YAML.parse(fs.readFileSync(path.join(ROOT, 'config/marketing-config.yaml'), 'utf8'));
const products = config.products ?? [];

function campaignTarget(i) {
  const productPart = i.split('-')[2];
  const product = products.find((p) => p.id === productPart && p.folder);
  return product ? `${product.folder}/campaigns/${i}` : `campaigns/${i}`;
}

function productTarget(i) {
  const known = products.find((p) => p.id === i);
  const folder = folderArg ?? known?.folder;
  if (!folder || !/^[A-Z][A-Za-z0-9]+$/.test(folder)) {
    console.error('Give the product folder name, as the product writes its name: new:product -- <id> <FolderName>  (e.g. procurepilot ProcurePilot)');
    process.exit(1);
  }
  return `${folder}/knowledge`;
}

const KINDS = {
  campaign: {
    template: 'campaigns/campaign-template',
    target: campaignTarget,
    pattern: /^\d{4}-\d{2}-[a-z0-9]+(-[a-z0-9]+)+$/,
    example: '2026-11-procurepilot-pilot-launch',
    replace: { '<YYYY-MM-product-slug>': id, 'created: <YYYY-MM-DD>': `created: ${today}` },
  },
  product: {
    template: 'knowledge/products/product-template',
    target: productTarget,
    pattern: /^[a-z0-9]+(-[a-z0-9]+)*$/,
    example: 'procurepilot',
    replace: { '<product-id>': id },
  },
};

const spec = KINDS[kind];
if (!spec || !id) {
  console.error('Usage: new-from-template.mjs campaign <id> | product <id> <FolderName>');
  process.exit(1);
}
if (!spec.pattern.test(id) || id.endsWith('-template')) {
  console.error(`Invalid ${kind} id "${id}". Example: ${spec.example}`);
  process.exit(1);
}
const target = spec.target(id);
const from = path.join(ROOT, spec.template);
const to = path.join(ROOT, target);
if (fs.existsSync(to)) {
  console.error(`${target} already exists; not overwriting.`);
  process.exit(1);
}

fs.cpSync(from, to, { recursive: true });
for (const file of fs.readdirSync(to, { recursive: true })) {
  const p = path.join(to, file);
  if (!p.endsWith('.md') || !fs.statSync(p).isFile()) continue;
  let text = fs.readFileSync(p, 'utf8');
  for (const [a, b] of Object.entries(spec.replace)) text = text.split(a).join(b);
  fs.writeFileSync(p, text);
}
console.log(`Created ${target}/ from ${spec.template}/`);
if (kind === 'product') console.log('Next: add the product (with folder and knowledge_dir) to config/marketing-config.yaml and knowledge/products/README.md, and its sources to config/sources.yaml.');
if (kind === 'campaign') console.log('Next: fill campaign-brief.md and add the campaign to campaigns/README.md.');
