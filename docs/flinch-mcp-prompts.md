# LaunchDarkly MCP prompts for the agent flinch

These are the prompts used in a LaunchDarkly MCP chat to create `flinch-policy` and `flinch-jev`. They are not the body of the post. Jev is an evaluation model. Do not create an AI Config that uses it as a chat or agent model. Do not run `repro_flinch_baseline.py --execute`.

## Step 1: `flinch-policy`

```text
Create the LaunchDarkly resources for Decora’s **agent flinch** (step 1). Do not write application feature code beyond what is needed to evaluate the flag. Do not create a Jev AI Config in agent/chat mode. Jev is an evaluation model; it is not a completion model.

**Account / project**
- Use existing project key `decor-agent-ai` (name: Decor Agent AI) if it exists. Create it only if missing.
- I am Alexis Roberson, owner. Do not invent a maintainer team (I have no teams).
- Reuse `LD_SDK_KEY` / production (or whatever env that SDK key belongs to). Do not rotate keys unless required.

**Flag to create**
- Key: `flinch-policy`
- Name: Flinch policy
- Kind: **multivariate JSON** (not boolean). Pass a `variations` array or LaunchDarkly will silently create a boolean flag.
- Temporary: **false**
- Tags: `flinch`, `guardrails`, `qdrant`
- Description: JSON policy for destructive Qdrant/agent actions. `mode` is shadow | live. `destructive.local` / `destructive.shared` are allow | confirm | block. Shared destructive work must never be allow. Off variation is fail-closed.

**Variation 0 — `fail-closed` (this is the off variation AND the SDK default)**

{
  "mode": "live",
  "on_ld_error": "confirm",
  "destructive": {
    "local": "confirm",
    "shared": "block"
  }
}

**Variation 1 — `shadow`**

{
  "mode": "shadow",
  "on_ld_error": "confirm",
  "destructive": {
    "local": "allow",
    "shared": "confirm"
  }
}

**Variation 2 — `live`**

{
  "mode": "live",
  "on_ld_error": "confirm",
  "destructive": {
    "local": "allow",
    "shared": "confirm"
  }
}

**Targeting**
- Set **off variation** to `fail-closed`.
- Turn targeting **ON** in the environment that matches `LD_SDK_KEY`.
- Serve **`shadow`** to everyone for now (log-only later; we are not enforcing yet).
- Add a rule you can describe in the flag comments/description: if we later target by context attribute `qdrant_sensitivity` = `shared` and the action is destructive, the served policy must use `destructive.shared: confirm` (never allow). The `live` variation already encodes that. Do not serve a variation that sets `destructive.shared` to `allow`.

**Do not**
- Create an AI Config that uses Jev as a chat/agent model.
- Put Jev questions on this flag yet (that is a later JSON config bag).
- Toggle unrelated flags.
- Call Qdrant or run `repro_flinch_baseline.py --execute`.

**When done, report**
- Project key, flag key, variation keys
- Which environment is ON and which variation it serves
- Off variation
- Link to the flag in the LaunchDarkly UI
- Confirmation that `get-flag` shows three JSON variations and offVariation is fail-closed
```

## Step 2: `flinch-jev`

```text
Create the LaunchDarkly **config bag** for Decora’s Jev pin (step 2). This is a JSON feature flag, not an AI Config and not a chat/agent model. Jev is TypeSafe’s evaluation model. Do not create an AI Config. Do not call TypeSafe or Qdrant. Do not run `repro_flinch_baseline.py --execute`. Do not change `flinch-policy`.

**Project**
- Project key: `decor-agent-ai` (already exists). Do not create another project.
- I am Alexis Roberson, owner, no teams. Maintainer: me (`get-member-self`). Do not invent a maintainer team.
- Environment: **production** (this is the env whose SDK key the app uses). Leave **test** targeting OFF unless you also set its off variation to the pinned variation.

**Flag**
- Key: `flinch-jev`
- Name: Flinch Jev
- Kind: **multivariate JSON**. You **must** pass a `variations` array or LaunchDarkly will silently create a boolean flag.
- Temporary: **false**
- Tags: `flinch`, `jev`, `typesafe`
- Description: Config bag for the Jev check. `model` must be a pinned TypeSafe id (`jev-1.13.0`), never served as `jev-latest` in production. `questions` is filled in a later step. This flag is not a completion/agent prompt.

**Variation 0 — `pinned` (off variation AND production fallthrough)**

{
  "model": "jev-1.13.0",
  "choice_confidence_min": 0.72,
  "questions": {}
}

**Variation 1 — `preview` (do not serve in production)**

{
  "model": "jev-latest",
  "choice_confidence_min": 0.72,
  "questions": {}
}

**Targeting**
- Off variation: **`pinned`** (index 0) in production and test.
- Production: targeting **ON**, default rule / fallthrough serve **`pinned`** (index 0) to everyone. Do **not** serve `preview`.
- Test: targeting **OFF**, off variation `pinned`.

**Do not**
- Put Noul/Choice question text on this flag yet (step 3).
- Add Jev as a custom model on an AI Config.
- Toggle or edit `flinch-policy`.
- Rotate SDK keys.

**When done, report**
- Project key, flag key, variation names and JSON
- Production: on/off, fallthrough variation, off variation
- Test: on/off, off variation
- `get-flag` confirmation that kind is multivariate JSON with two variations
- Link to the flag in the LaunchDarkly UI
```
