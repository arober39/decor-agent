# Controlling coding agents is a tool-call problem

A coding agent is not a chatbot. It has tools. The failure that matters is not a sloppy sentence. It is a DELETE, a write, a migrate, aimed at a target the agent did not re-check.

That is a control problem. Control sits in front of the tool, or it does not exist.

I built a pause in front of a collection delete after a public write-up of an agent that wiped a shared vector database. The diagnosis was right. A local test cluster was on the wrong schema. The port it used had been a tunnel to shared-dev the entire session. Minutes earlier it had already issued a read-only query on that port, filed the number away as local, and never looked again. A tired human at 11pm still hesitates before typing DELETE against something that might be shared. The agent had the same information and none of the hesitation.

The lab write-up is elsewhere. What follows is what that build forced into the open.

## You cannot control a coding agent from the prompt

Read-only in the system prompt is an instruction. Read-only in the key is a control. Shared environments out of the working session is a control. A sentence that says “be careful with production” is not.

Prompts are cheap to ignore under a confident plan. Tools are not. If the agent can call DELETE, the prompt is already downstream of the decision you care about.

## The expensive miss is identity

Agents are already good at the part that incident got right. They can see a broken schema and propose a rebuild. The miss was not intelligence. It was identity. Intended local-test. Actual shared cluster on a localhost port.

Once the port is trusted, a good plan executes as if the world still matches the words in the prompt. Control has to resolve the target before the verb, every time, including when the agent just used that port for something harmless.

## A second completion is not a gate

The usual move is LLM-as-judge: another model writes a verdict in prose, and a human or a regex tries to read it. You cannot threshold a paragraph. You cannot fail closed on a vibe. You cannot pin “be wise” across deploys.

A judge that belongs in front of a tool call returns a type. Yes-or-no as a probability. A choice from a closed list. A confidence you can compare to a number. That still is not permission. Typed output cannot return gibberish. It can still pick the wrong valid option. Code has to map those scores onto allow, confirm, or block. I used a System One model for those scores, [Jev](https://www.typesafe.ai/), and I pinned the version. The host kept the last word.

If the judge is down, destructive or shared work still confirms. The policy does not disappear because a model timed out.

## Confirm the target, not the delete

A human who is asked “delete this collection?” and sees `localhost:6334` will approve it for the same reason the agent ran it. The address looks local.

A human who is asked to type `shared-dev-tunnel` will flinch. The operating model is the name, not the yes. Approval is a host path. The model does not get a tool called `approve`.

## Policy lives outside the agent

A flag that can only be on or off makes a poor pause. You need a mode that records the decision without stopping the command, a mode that enforces, and a default that does not fail open when the flag service is unreachable.

That is runtime control. The check can tighten without a deploy. The judge’s questions and version can move without a deploy. Watching and enforcing are different variations of the same JSON, not a boolean you flip on Friday.

Roll the change out. Shadow first, live second. Instrument the no that actually fires. A shared delete that resolves to confirm will not show up on a block metric. Sample size is part of control too. A handful of context keys is not a guarded rollout, even when the pause is correct.

## The log is the accountability

Reasoning will keep getting cheaper. A coherent story about why that port was fine will always be available after the fact. The useful artifact is the row that says which environment it actually had, which policy it evaluated, whether the judge agreed, and whether anything stopped it.

A span on the check, a decision log, a metric on escalate versus override. That is not decoration. That is how you prove the gate ran.

## The gates are still the product

In a software factory, execution is the commodity. The coding agent is an execution station. The harness is which tools it may call. The operating model is who can say no, and to what name. Observability is the chain you can replay.

LLM-as-judge puts the operating model back inside a completion. Prompt-only safety puts it inside a paragraph the worker can ignore. Control for coding agents is the same work we already know how to do for releases. Put it in front of the tool call. Version it. Roll it out. Log it.

The plan can be brilliant. The cluster still has to be the one you thought it was.
