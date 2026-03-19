#!/usr/bin/env node

// Always inject ultrathink + ultrawork mode on every prompt
const output = {
  continue: true,
  additionalContext: `<think-mode>

**ULTRATHINK MODE ENABLED** - Extended reasoning activated.

You are now in deep thinking mode. Take your time to:
1. Thoroughly analyze the problem from multiple angles
2. Consider edge cases and potential issues
3. Think through the implications of each approach
4. Reason step-by-step before acting

Use your extended thinking capabilities to provide the most thorough and well-reasoned response.

</think-mode>

---

[MAGIC KEYWORD: ULTRAWORK]
`
};

console.log(JSON.stringify(output));
