# Cringewiki repository instructions

Cringewiki is a server-backed social fork of the open Hexrelatum spatial wiki.
It adds local accounts, authored articles, axis votes and conserving influence
while retaining Hexrelatum's relative six-coordinate navigation.

## Boundaries

- Keep code and bundled seed content public and safe to redistribute. Never
  commit credentials, password hashes, live user records, private company
  knowledge or production database snapshots.
- Treat the six positive base coordinates from 1 through 10 as source data. Three-dimensional
  positions and colors are derived views, never replacements for the six stored
  values.
- Keep projection and color algorithms versioned and explainable. Current
  preview formulas are provisional until the owner approves a stable format.
- The home article is an ordinary concept selected as the initial route. It may
  have any valid coordinates and becomes local `0 · 0 · 0` only while viewed.
- Markdown links are directed citations in source content and bidirectional
  navigation edges in the rendered map.
- Use only Python's standard library in the initial server. Passwords must use
  `hashlib.scrypt` with per-user random salts; sessions remain server-side and
  every mutating API route requires CSRF validation. Never expose password
  hashes, session-token hashes or CSRF secrets through logs, fixtures or APIs.
- Coordinate votes add one unit to exactly one selected pole per user and point.
  A replacement vote moves that unit; it never duplicates it.
- Influence is conserved: each registered user contributes one unit total.
  Cyclic user support must converge and must never create mass.
- SQLite is the only initial database. Keep its boundary explicit so a later
  PostgreSQL implementation can replace persistence without changing the
  browser protocol. No production credentials belong here.

## Dependencies

The initial server and browser have no third-party runtime dependencies. Do not
add any without documenting the reason, license and security/reproducibility
impact.

## Validation

Run from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q server tests
node --check web/app.js
node --check web/form.js
git diff --check
```
