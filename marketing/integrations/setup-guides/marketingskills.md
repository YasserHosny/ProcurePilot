# Setup guide: upstream marketing skills

**Source:** https://github.com/coreyhaines31/marketingskills (MIT, Corey Haines; licence copy in
`../marketingskills/LICENSE`).

## How it is installed

The upstream README offers eight install options. This project uses **Option 4, "Clone and Copy"**, adapted to the
folder Claude Code reads for project skills (`.claude/skills/`, as the README itself notes for Claude Code):

- `config/upstream-skills.yaml` lists the selected skills and pins one commit (`ref`).
- `scripts/sync-upstream-skills.mjs` fetches that commit with `git`, copies each selected skill folder unchanged
  into `.claude/skills/<name>/`, copies the licence, and writes `../marketingskills/upstream-lock.json` with the
  commit, the upstream version and a sha256 for every file.
- No npm package from the upstream and no upstream script is executed. (`npx skills add` and the `/plugin`
  marketplace are the alternatives; they install the whole set or need an interactive session, and are harder to pin.)

Installed 2026-10-27: 24 skills, commit `17772c7a80b7b8c7a47af30f648374cd8bd8adc5`, upstream version 2.13.5.

## How Claude Code finds them

Per the Claude Code skills documentation (fetched 2026-10-27):

- Started **in `marketing/`**: `.claude/skills/` is the project skill folder and every skill loads at startup.
- Started **at the repo root**: `marketing/.claude/skills/` is a nested skill folder. Its skills load the
  first time Claude reads or edits a file inside `marketing/`, and stay loaded for the session. Opening
  `marketing/CLAUDE.md` is enough. `/add-dir marketing` also loads them.
- Skills are listed by their `description`; the model picks them for matching tasks, or call one directly with
  `/<name>` (e.g. `/copywriting`).

## Shared context

Every upstream skill first reads `.agents/product-marketing.md` (relative to where Claude Code was started). In
this project that file is `marketing/.agents/product-marketing.md`, a summary derived from `knowledge/`. When
working from the parent workspace, point the skill at that path (CLAUDE.md says so).

## Updating

```bash
npm install                                   # once, installs the YAML parser used by the scripts
npm run skills:sync -- --ref main --dry-run   # see what the latest upstream would change
npm run skills:sync -- --ref main             # install it, then copy the printed commit into config ref
npm test                                      # validator: frontmatter, lock hashes, links, rules
```

Review the upstream `VERSIONS.md` for renamed or removed skills before updating, and read the diff of any skill
the Marketing OS relies on. Add or remove a skill by editing `skills:` in `config/upstream-skills.yaml` and
syncing; the script removes only skills it installed itself.

## Rules

- Never edit upstream skill files in place (the validator reports a hash mismatch). Put Iron Systems rules in
  `CLAUDE.md` or the four custom skills, which take precedence.
- Some upstream skills mention paid ads, outreach or generation tools. Those parts are outside the current scope
  unless the owner asks.
- Some upstream skills reference skills that are not installed (listed under `not_installed`). That is expected.
