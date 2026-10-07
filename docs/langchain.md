# LangChain integration

Install `backend/requirements-langchain.txt` and configure `backend/.env` as described in the [README](../README.md#optional-live-models).

Grid simulations use LangChain for each agent decision. The workflow recorder below also supports applications outside the grid.

## LangChain workflow recording

Select **Workflows** in the app toolbar to inspect workflows outside the grid.
The **Stale inventory recovery** example reads an outdated report, fails a local reservation, checks current inventory, and reserves an alternative.
Tools mutate only a local fixture. No purchase or external reservation occurs.
The workflow controls recovery. Its model summarizes the recorded result.

- **Deterministic** uses a LangChain model fixture and makes no API calls.
- **Live model summary** makes one model call using `backend/.env`.

The history records callback arrival order. Each invocation has its own ID and parent ID, including concurrent calls.
Select **Next failure** to inspect a failed tool call, or select an event to inspect its input and recorded output.
**Inspect parent** follows the recorded invocation relationship.
State appears only when the application explicitly records it, such as the example's `inventory_before` and `inventory_after` events.
Nesting is execution evidence, not proof of decision causality.

To record another Python LangChain workflow, install `backend/requirements-langchain.txt` and run with `backend` on your Python path:

```python
from app.integrations.langchain_recorder import AgentLensRecorder

recorder = AgentLensRecorder("My workflow")
try:
    result = chain.invoke(inputs, config={"callbacks": [recorder]})
finally:
    recorder.save()
```

Use `await chain.ainvoke(...)` for asynchronous workflows with the same callback configuration.
Create a new recorder for each execution and save after its child calls finish.
Pass the callback configuration into nested model, tool, and runnable calls.
The recorder supports chains, chat/completion models, tools, retrievers, and explicit custom events.
Use LangChain's `dispatch_custom_event` to record application-specific handoffs, memory writes, or state changes.
The adapter does not infer these from ordinary model text.

Records use a separate workflow schema in `data/workflows`, which Git ignores.
`GET /workflows` lists recordings. `GET /workflows/{id}` reads one complete recording.
`POST /workflows/demo` with `{"mode":"demo"}` or `{"mode":"live"}` executes the bounded example.
Saved replay never executes the workflow again.

Inputs and outputs are stored locally. SDK metadata, exception bodies, and message reasoning blocks are excluded.
Known API keys and sensitive field names are redacted. Arbitrary private text is not automatically removed.
Pass `redact_values=("private-value",)` when additional exact values must be removed.
Text, collection, and nesting limits produce explicit truncation markers.
Unsupported Python objects receive a type placeholder instead of their `repr`.
Token streaming, durable checkpoints, arbitrary trace import, and resuming execution are not implemented.

From `backend`, generate an example without the UI:

```sh
../.venv/bin/python -m app.workflows.reservation
# Optional: make one live model call.
../.venv/bin/python -m app.workflows.reservation --mode live
```

