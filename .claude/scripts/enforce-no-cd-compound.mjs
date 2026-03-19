#!/usr/bin/env node

// PreToolUse:Bash hook — block compound `cd <path> && ...` commands.
// A standalone `cd <path>` is allowed (once at session start).
// Compound forms like `cd /foo && uv run pytest` violate the project rule.

import { readFileSync } from 'fs';

let input = '';
try {
  input = readFileSync(0, 'utf-8');
} catch {
  // stdin empty or unreadable — allow
  console.log(JSON.stringify({ continue: true }));
  process.exit(0);
}

let command = '';
try {
  const data = JSON.parse(input);
  command = data.input?.command || '';
} catch {
  console.log(JSON.stringify({ continue: true }));
  process.exit(0);
}

// Detect compound cd: `cd <path> &&` or `cd <path>;`
const compoundCd = /^\s*cd\s+[^\s;]+\s*(&&|;)/;
if (compoundCd.test(command)) {
  console.log(JSON.stringify({
    continue: false,
    reason: 'BLOCKED: Do not use `cd <path> && command`. The working directory persists between Bash calls. Run `cd <path>` once as a standalone call at the start, then use bare commands (e.g. `uv run pytest`, `git status`) in all subsequent calls.'
  }));
} else {
  console.log(JSON.stringify({ continue: true }));
}
