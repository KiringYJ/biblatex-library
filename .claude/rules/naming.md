# File & Directory Naming Convention

**0. No abbreviations — spell names out in full.**

Use `validate`, not `val`. Use `normalize`, not `norm`. Use `identifier`, not `id` (when naming files).
The only exception is `cli` (universally understood in the Python ecosystem).

Two rules govern singular vs plural:

**1. Source files and module directories use singular.**

These name a *concept*, not a collection.

```
src/biblib/validate.py        # not validates.py
src/biblib/convert/            # not converts/
src/biblib/template.py         # not templates.py
```

**2. Data/collection directories use plural.**

These *hold multiple items* of the same kind.

```
tests/fixtures/
data/
csl/samples/
```

**Quick test:** "Is this a module/concept?" -> singular. "Does this hold N files of the same type?" -> plural.

**3. Use underscores, not hyphens, in Python file names.**

All Python file names use `snake_case` (underscores) to stay consistent with Python conventions. Hyphens are reserved for non-Python contexts (e.g., LaTeX style names like `yj-standard`, date components).

```
src/biblib/add_entries.py       # not add-entries.py
tests/test_normalize.py         # not test-normalize.py
```
