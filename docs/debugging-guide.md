# Your first debugging session

## Start without an API key

1. Follow the [quick start](../README.md#quick-start).
2. Open **Scenarios** and create **Handoff Failure** with mock agents.
3. Pause replay and select Blue’s action at turn 16 in **Recorded History**.
4. Read **Local observation**, **Explicit plan**, and **Selected action** in the inspector. Compare these with the rejected collection in **Why this action?**.
5. Inspect Blue’s messages and retrieved memories. Follow a source link into **Focused provenance** and choose **Upstream** to trace the report’s origin.
6. Return to turn 8 and inspect Red’s collection. Then inspect Blue’s turn-10 observation. The report describes a resource that another agent has already removed.
7. Create **Verified Handoff** with mock agents. Blue requests a correction at turn 10. Use **Compare** to inspect both recordings. The default mock policies finish in 31 and 28 turns, with one and zero rejected actions respectively.

These turn numbers belong to the deterministic mock demonstration. Live recordings can differ. Use the investigation guide’s evidence bookmarks to locate corresponding events in a live run.

## Read the views correctly

**Global View** shows the world after the selected action. An agent perspective shows its latest recorded observation, which can precede that action. The inspector labels the decision context **Before action**. A resource can therefore appear in the agent view and be absent from the global view immediately after successful collection.

**Recent messages** contains newly delivered messages for that decision. An older message may still be available through retrieved memory even when this section is empty.

**Memory** exposes creation and retrieval history. **Possibly stale** is a debugger assessment against a global snapshot; it is not information secretly supplied to the agent.

**Why this action?** connects the saved context, plan, action, and result. The graph follows explicit references. Click an event to change the selected turn and agent. Increase reference depth gradually; large graphs omit events after their display limit.

## Investigate a live decision

For a run created with LangChain, expand **Exact submitted context**, **Exact system instructions**, and **Validated response and settings** under the recorded model request. Check whether an incorrect action followed missing information, contradictory information, or failure to follow a supplied rule.

Start at a rejected action and inspect earlier decisions too. A valid move toward an empty destination can reveal the problem before collection fails. Compare current observation, previous plan, and retrieved memories rather than relying only on error events.

The [live case study](debugging-case-study.md) provides concrete event IDs from a measured pilot. Those full recordings are not bundled. Generate your own runs to investigate new outcomes, then compare one policy change at a time. Replay never applies a fix or resumes execution from the selected point.
