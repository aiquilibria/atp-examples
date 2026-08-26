# ATP Examples

Runnable examples for the [Agent Trust Protocol](https://agenttrustprotocol.org)
([spec v0.2](https://agenttrustprotocol.org/spec/v0.2)) using the official
[Python SDK](https://github.com/aiquilibria/atp-python).

## Contents

| Example | What it shows |
|---------|---------------|
| [`core/simple_atp_agent.py`](core/simple_atp_agent.py) | A minimal ATP-compliant agent: registration, `atp_task` proof lifecycle, Proof Sketch commits, and a JSON-RPC `atp.challenge` endpoint served with FastAPI. |
| [`core/verifying_agent.py`](core/verifying_agent.py) | An agent acting as a Challenger: retrieving the committed sketch, challenging the executor, and verifying proof integrity. |

## Setup

```bash
uv sync
cp .env.example .env   # then fill in your Exchange API key
```

See [`core/README.md`](core/README.md) for a step-by-step walkthrough and the
spec-compliance notes for each example.

## License

[Apache 2.0](./LICENSE) — Copyright © 2026 AIquilibria
