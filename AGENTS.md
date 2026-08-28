# Hexrelatum repository instructions

Hexrelatum is a lore-neutral, self-contained, Git-native spatial wiki. The
repository contains the open static reader, the reference local indexer, the
public index format, and the wiki that documents and demonstrates the engine.

## Boundaries

- Keep `wiki/` public and safe to redistribute. Never add hidden Geno-Dice lore,
  credentials, user records, wallet data, private company knowledge, or private
  repository history.
- Treat the six positive article coordinates as source data. Three-dimensional
  positions and colors are derived views, never replacements for the six stored
  values.
- Keep projection and color algorithms versioned and explainable. Current
  preview formulas are provisional until the owner approves a stable format.
- The home article is an ordinary concept selected as the initial route. It may
  have any valid coordinates and becomes local `0 · 0 · 0` only while viewed.
- Markdown links are directed citations in source content and bidirectional
  navigation edges in the rendered map.
- Do not add authentication, social weights, subscriptions, ratings, lore axes,
  PostgreSQL, runtime Git credentials, or private connectors to the public
  reference implementation without a separate approved change.
- External indexers and connectors must integrate through the public index
  contract. Do not make private data or services dependencies of the public
  build.

## Dependencies

The reference indexer uses only the Python standard library. The browser reader
uses no package manager and no runtime CDN. Do not add dependencies without
documenting the reason, license, reproducibility impact, and offline fallback.

## Validation

Run from the repository root:

```powershell
python tools/build_index.py --check
python -m unittest discover -s tests -v
python -m compileall -q tools tests
node --check web/app.js
git diff --check
```
