"""
Simple ATP Agent - Best Practices Example

This example demonstrates the framework-agnostic ATP Python SDK.
It shows best practices for using the new core/adapters architecture.

Architecture:
    - Uses atp.core for all protocol logic (framework-agnostic)
    - No framework dependencies (no A2A, LangChain, etc.)
    - Simple FastAPI server for JSON-RPC challenge endpoint
    - Direct use of ATP Exchange client

Key Features:
    1. Register agent with ATP Exchange
    2. Create proofs for query-response interactions
    3. Store full proofs locally (privacy-preserving)
    4. Commit proof sketches (hashes only) to exchange
    5. Handle challenge requests from other agents

Usage:
    1. Set environment variables:
       export ATP_API_KEY="your-api-key"
       export ATP_EXCHANGE_URL="http://localhost:8080"

    2. Run the agent:
       python examples/simple_atp_agent.py

    3. Test query-response:
        curl -X POST http://localhost:8100/query \\
            -H "Content-Type: application/json" \\
            -d '{"question": "What is 2+2?"}'
        curl -X POST http://localhost:8100/query -H "Content-Type: application/json" -d '{"question": "What is 2+2?"}'
            {"task_id":"cfa76b21-2c2d-4f26-8f4b-da4e47f6acb9","answer":"4","proof_committed":true}

    4. Test challenge:
        curl -X POST http://localhost:8100/ \\
            -H "Content-Type: application/json" \\
            -d '{"jsonrpc": "2.0", "method": "atp.challenge", "params": {"task_id": "..."}, "id": 1}'
        curl -X POST http://localhost:8100/ -H "Content-Type: application/json" \\
            -d '{"jsonrpc": "2.0", "method": "atp.challenge", "params": {"task_id": "cfa76b21-2c2d-4f26-8f4b-da4e47f6acb9"}, "id": 1}'
            {
                "jsonrpc":"2.0",
                "result":{
                    "proof_data":{
                        "atp_url":"http://localhost:8080",
                        "system_id":"774be9e6967f60e8877ac113322f99a38b63673d0f428f38e43eabb92b0e53cc",
                        "task_id":"cfa76b21-2c2d-4f26-8f4b-da4e47f6acb9",
                        "query":"What is 2+2?",
                        "query_hash":"52cb6b5e4a038af1756708f98afb718a08c75b87b2f03dbee4dd9c8139c15c5e",
                        "response":"4",
                        "response_hash":"4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
                        "timestamp":"2026-01-28T17:45:05.083323+00:00",
                        "trust_level":"Verified",
                        "dependencies":[]
                    },
                    "created_at":"2026-01-28T17:45:05.083323+00:00",
                    "expires_at":"2026-01-28T18:45:05.083323+00:00"
                },
                "error":null,
                "id":1
            }
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel

from atp.core import (
    ATPClient,
    ATPConfig,
    Capability,
    Ontology,
    SQLiteProofStore,
    atp_task,
)
from atp.core.logging import get_logger

logger = get_logger(__name__)

# ===================================================================
# Configuration
# ===================================================================

ATP_API_KEY = os.getenv("ATP_API_KEY", "demo-key")
ATP_EXCHANGE_URL = os.getenv("ATP_EXCHANGE_URL", "http://localhost:8080")
AGENT_NAME = "simple-atp-agent"
AGENT_URL = "http://localhost:8100"
AGENT_TYPE = "agent"

# ===================================================================
# Initialize ATP Components
# ===================================================================

# Create ATP configuration
config = ATPConfig(
    api_key=ATP_API_KEY,
    exchange_url=ATP_EXCHANGE_URL,
    proof_ttl_seconds=3600,  # Proofs expire after 1 hour
)

# Create local proof storage (privacy-preserving, survives restarts)
proof_store = SQLiteProofStore(config=config)

# Create ATP client (for exchange communication)
atp_client = ATPClient(config=config)

# Track our system_id after registration
system_id: str | None = None

# ===================================================================
# ATP v0.2.0 Task Classification
#
# Declare what type of work this agent performs so the Exchange can
# track and surface task-type analytics.  Use your O*NET SOC code and
# the relevant capability slugs from the ATP ontology.
# ===================================================================
AGENT_CLASSIFICATION = Capability(
    description="General question-answering agent",
    ontology=Ontology(
        ontology_uri="https://agenttrustprotocol.org/ontology/v0.2.0",
        # O*NET SOC code — 15-2051.00 = Data Scientists
        # Replace with the code that best matches your agent's role.
        occupation="15-2051.00",
        capabilities=["question-answering"],
        work_activities=["4.A.4.a.1"],
    ),
)

# ===================================================================
# FastAPI Application
# ===================================================================

app = FastAPI(title="Simple ATP Agent")


# Request/Response models
class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    task_id: str
    answer: str


class ChallengeRequest(BaseModel):
    """JSON-RPC 2.0 challenge request"""

    jsonrpc: str = "2.0"
    method: str
    params: dict
    id: int | str


class ChallengeResponse(BaseModel):
    """JSON-RPC 2.0 challenge response"""

    jsonrpc: str = "2.0"
    result: dict | None = None
    error: dict | None = None
    id: int | str


# ===================================================================
# Agent Logic (Simple Q&A)
# ===================================================================


def answer_question(question: str) -> str:
    """
    Simple Q&A logic (replace with your AI model).

    In a real agent, this would call an LLM, search system, etc.
    """
    # Simple demo responses
    if "2+2" in question or "2 + 2" in question:
        return "4"
    elif "capital" in question.lower() and "france" in question.lower():
        return "Paris"
    elif "hello" in question.lower():
        return "Hello! How can I help you?"
    else:
        return f"I received your question: '{question}'. This is a demo response."


# ===================================================================
# ATP Integration (Best Practices)
# ===================================================================


async def handle_query_with_atp(question: str) -> tuple[str, str]:
    """
    Handle query with ATP proof creation and commitment.

    Uses atp_task utility for automatic handling of:
    - atp_task_id generation (ensures consistent naming)
    - Proof creation and local storage
    - Commit to exchange (hashes only)

    This is the recommended pattern for ATP integration!
    The agent developer only needs to:
    1. Call this function with the question
    2. Get back atp_task_id to return to client

    Returns:
        tuple: (atp_task_id, answer, atp_committed)
    """
    # Use atp_task context manager - handles ATP lifecycle automatically!
    # Pass classification so the Exchange knows what type of work this task is.
    async with atp_task(
        atp_client,
        proof_store,
        query=question,
        classification=AGENT_CLASSIFICATION,
    ) as task:
        # Agent just focuses on answering the question
        answer = answer_question(task.query)

        # Tell ATP what the response is - it handles the rest!
        task.set_response(answer)

        # task.atp_task_id is automatically generated
        # Proof is automatically created and committed on context exit

    # Return the atp_task_id and result
    return task.atp_task_id, answer


# ===================================================================
# HTTP Endpoints
# ===================================================================


@app.on_event("startup")
async def startup():
    """Register agent with ATP Exchange on startup"""
    global system_id

    try:
        registration = await atp_client.register_system(
            name=AGENT_NAME,
            system_type=AGENT_TYPE,
        )
        system_id = registration.system_id
        logger.info(
            "agent_registered",
            system_id=system_id,
            agent_name=AGENT_NAME,
            agent_url=AGENT_URL,
        )
    except Exception as e:
        logger.warning(
            "registration_failed",
            error=str(e),
            mode="offline",
        )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Query endpoint - demonstrates ATP proof creation.

    Example:
        curl -X POST http://localhost:8100/query \\
          -H "Content-Type: application/json" \\
          -d '{"question": "What is 2+2?"}'
    """
    task_id, answer = await handle_query_with_atp(request.question)

    return QueryResponse(task_id=task_id, answer=answer)


@app.post("/", response_model=ChallengeResponse)
async def challenge(request: ChallengeRequest):
    """
    JSON-RPC 2.0 endpoint - handles ATP challenge requests.

    Another agent can challenge this agent to prove a previous interaction.
    This endpoint returns the full proof from local storage.

    Example:
        curl -X POST http://localhost:8100/ \\
          -H "Content-Type: application/json" \\
          -d '{
            "jsonrpc": "2.0",
            "method": "atp.challenge",
            "params": {"task_id": "abc123"},
            "id": 1
          }'
    """
    # Validate JSON-RPC request
    if request.jsonrpc != "2.0":
        return ChallengeResponse(
            id=request.id,
            error={
                "code": -32600,
                "message": "Invalid Request - jsonrpc must be '2.0'",
            },
        )

    if request.method not in ("atp.challenge", "challenge"):
        return ChallengeResponse(
            id=request.id,
            error={"code": -32601, "message": f"Method '{request.method}' not found"},
        )

    # Extract task_id from ATP v0.2.0 nested structure
    atp_payload = request.params.get("atp_payload")
    if not atp_payload:
        # Fallback to old flat structure for backward compatibility
        task_id = request.params.get("task_id")
        challenger = request.params.get("challenger")
    else:
        # ATP v0.2.0: Extract from nested structure
        task_data = atp_payload.get("task", {})
        task_id = task_data.get("task_id")
        challenger_identity = task_data.get("identity", {})
        # Convert to old format for logging
        challenger = {
            "system_id": challenger_identity.get("system_id", "unknown"),
            "atp_url": challenger_identity.get("atp_exchange_url", "unknown"),
        }

    if not task_id:
        return ChallengeResponse(
            id=request.id,
            error={"code": -32602, "message": "Missing required parameter: task_id"},
        )

    # Log challenger identity
    if challenger:
        challenger_id = challenger.get("system_id", "unknown")
        challenger_url = challenger.get("atp_url", "unknown")
        logger.info(
            "challenge_received",
            task_id=task_id,
            challenger_id=challenger_id,
            challenger_url=challenger_url,
        )
        # Agents can optionally validate challenger against ATP Exchange here
    else:
        logger.warning("anonymous_challenge_rejected", task_id=task_id)
        return ChallengeResponse(
            id=request.id,
            error={"code": -32602, "message": "Missing required parameter: challenger"},
        )

    # Retrieve proof from local storage
    try:
        stored_proof = await proof_store.get(task_id)

        if not stored_proof:
            return ChallengeResponse(
                id=request.id,
                error={
                    "code": -32000,
                    "message": f"Proof not found for task_id: {task_id}",
                },
            )

        # Return full proof (includes query & response) as StoredProof
        return ChallengeResponse(
            id=request.id,
            result=stored_proof.model_dump(mode="json"),
        )

    except Exception as e:
        return ChallengeResponse(
            id=request.id,
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
        )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent": AGENT_NAME,
        "atp_enabled": True,
        "registered": system_id is not None,
        "system_id": system_id,
        "exchange_url": ATP_EXCHANGE_URL,
    }


# ===================================================================
# Main
# ===================================================================


def main():
    """Run the agent"""
    import uvicorn

    logger.info(
        "agent_starting",
        agent_name=AGENT_NAME,
        agent_url=AGENT_URL,
        exchange_url=ATP_EXCHANGE_URL,
        endpoints={
            "query": "POST /query",
            "challenge": "POST /",
            "health": "GET /health",
        },
        features=[
            "framework-agnostic",
            "privacy-preserving",
            "atp-compliant",
        ],
    )

    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")  # bind loopback; widen deliberately for deployment


if __name__ == "__main__":
    main()
