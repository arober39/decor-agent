### 1. Install LaunchDarkly Python SDKs

```bash
cd decor-agent
source venv/bin/activate
pip install launchdarkly-server-sdk launchdarkly-server-sdk-ai
```

Then update `requirements.txt`:

```
launchdarkly-server-sdk
launchdarkly-server-sdk-ai
```
### Configure LD MCP server for Claude Code
  "mcpServers": {
    "LaunchDarkly": {
      "command": "npx",
      "args": [
        "-y",
        "--package",
        "@launchdarkly/mcp-server",
        "--",
        "mcp",
        "start",
        "--api-key",
        "api-68b5ade4-eccb-4d5d-8f6b-45ceb695d51a"
      ]
    }
  },

  "mcpServers": {
    "LaunchDarkly": {
      "command": "npx",
      "args": [
        "-y", "--package", "@launchdarkly/mcp-server", "--", "mcp", "start",
        "--api-key", "api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      ]
    }
  }

### 2. Install the LaunchDarkly agent skills
# This clones launchdarkly/agent-skills into a temp dir, copies skills
# into ./.claude/skills/ (because no -g), then cleans up the temp clone.
npx --yes skills add launchdarkly/agent-skills \
  --full-depth --skill '*' --agent claude-code -y

### 3. run project
python3 server.py

### 4. create launchdarkly project and feature flag
do this in natrual lanugage in claudeo code desktop

### 4. Create a LaunchDarkly project for the demo

Create a standard LaunchDarkly project. There is no distinct "AI Config project" type — a single LD project holds your feature flags, AI Configs, segments, and metrics together.

**UI path:** LaunchDarkly → Projects → New project.

- Project name: `decor-agent-demo`
- Environments: `production` (the only one you'll demo against — keeps things simple)

Copy the **server-side SDK key** for `production` from the environment detail page; you'll paste it in step 6.

**5. Create each AI Config:**

## Phase 3 — Variations + targeting (6 min)

This is the headline phase. Two personalities, same question, different answers — targeted by user segment.

