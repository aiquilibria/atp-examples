"""
ATP Verifying Agent Example

Demonstrates how to build an agent that verifies the work of other ATP-compliant
agents using the challenge-response pattern.

The ATP SDK handles all proof verification transparently:
- ``ATPClient.challenge(verify=True)`` (the default) sends the challenge, parses
  the response, re-derives the hashes, and cross-checks them against the committed
  proof sketch on the ATP Exchange — all in one call.
- The verifying agent just acts on the boolean result; it never touches raw hashes
  or proof fields directly.

Usage:
    1. Start ``simple_atp_agent.py`` in another terminal
    2. Run this verifying agent:
       python examples/core/verifying_agent.py
"""

import asyncio
import os
from datetime import UTC, datetime

import httpx

from atp.core import (
    ATPClient,
    ATPConfig,
    DependencyEvaluation,
    SQLiteProofStore,
    atp_task,
)
from atp.core.logging import configure_logging, get_logger

configure_logging(level="INFO", use_json=False)
logger = get_logger(__name__)

ATP_API_KEY = os.getenv("ATP_API_KEY", "demo-key")
ATP_EXCHANGE_URL = os.getenv("ATP_EXCHANGE_URL", "http://localhost:8080")
TARGET_AGENT_URL = os.getenv("TARGET_AGENT_URL", "http://localhost:8100")


async def query_agent(agent_url: str, question: str) -> tuple[str, str]:
    """Query an ATP agent and return ``(task_id, answer)``."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{agent_url}/query",
            json={"question": question},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        task_id = data.get("task_id") or data.get("atp_task_id")
        answer = data.get("answer") or data.get("result")

        if not task_id:
            raise ValueError("Response missing atp_task_id/task_id")

        return task_id, answer


async def main() -> None:
    logger.info(
        "verifying_agent_starting",
        target_agent=TARGET_AGENT_URL,
        exchange_url=ATP_EXCHANGE_URL,
    )

    config = ATPConfig(api_key=ATP_API_KEY, exchange_url=ATP_EXCHANGE_URL)
    atp_client = ATPClient(config=config)
    proof_store = SQLiteProofStore(config=config)

    # Step 0: Register — required so the challenger identity is included in the
    # challenge request (ATP v0.2.0 accountability requirement).
    try:
        registration = await atp_client.register_system(name="verifying-agent", system_type="agent")
        logger.info("registration_success", system_id=registration.system_id)
    except Exception as e:
        logger.error("registration_failed", error=str(e))
        return

    # Step 1: Query the target agent.
    question = "What is 2+2?"
    logger.info("step_1_query", question=question)

    try:
        task_id, answer = await query_agent(TARGET_AGENT_URL, question)
        logger.info("query_success", answer=answer, task_id=task_id)
    except Exception as e:
        logger.error("query_failed", error=str(e))
        return

    # Initialise stored_proof so it is always defined even if the challenge block
    # raises before the assignment.
    stored_proof = None

    # Step 2: Challenge-and-verify.
    #
    # ``challenge(verify=True)`` (the default) does everything in one call:
    #   • Sends the JSON-RPC challenge with our identity to the target agent
    #   • Parses the returned StoredProof
    #   • Recomputes invocation_hash and outcome_hash from the proof content
    #   • Fetches the proof sketch committed to the ATP Exchange
    #   • Confirms the hashes match — proving the agent didn't fabricate the proof
    #
    # Nothing here needs to touch individual hash fields.
    verification_query = f"Verify that {TARGET_AGENT_URL} correctly answered: {question}"

    async with atp_task(atp_client, proof_store, query=verification_query) as verification_task:
        logger.info("step_2_challenge", task_id=task_id)

        exchange_verified = False
        message = "Unknown error"

        try:
            stored_proof, verified, message = await atp_client.challenge(
                agent_url=TARGET_AGENT_URL,
                task_id=task_id,
                # verify=True is the default; shown explicitly for clarity
                verify=True,
                # Pass the verifier's own task_id so the integrity assessment
                # is linked to a challengeable ATP proof of this verification work.
                assessor_task_id=verification_task.atp_task_id,
            )

            if verified:
                logger.info("verification_success", message=message)
                exchange_verified = True

                # Apply quality rubric: "What is 2+2?" → expected answer is "4".
                # The quality verdict is embedded in the dependency's evaluations list
                # and committed to the Exchange as part of this verifier's proof sketch —
                # no separate assessment API call is needed.
                quality_result = "passed" if answer.strip() == "4" else "failed"
                now = datetime.now(UTC)

                verification_task.add_dependent_proof(
                    stored_proof,
                    evaluations=[
                        DependencyEvaluation(
                            evaluation_type="integrity",
                            evaluation_result="verified",
                            evaluated_at=now,
                        ),
                        DependencyEvaluation(
                            evaluation_type="quality",
                            evaluation_result=quality_result,
                            evaluated_at=now,
                        ),
                    ],
                )
                logger.info(
                    "dependent_proof_added",
                    dependency_task_id=task_id,
                    quality_result=quality_result,
                )
            else:
                logger.error("verification_failed", message=message)

        except Exception as e:
            logger.error("challenge_failed", error=str(e))

        verification_task.set_response(
            f"Verification {'VERIFIED' if exchange_verified else 'FAILED'}: "
            f"{message if exchange_verified else 'Proof did not match ATP Exchange'}"
        )

    logger.info(
        "verification_complete",
        exchange_verified=exchange_verified,
        verifier_committed=verification_task._committed,
        status="SUCCESS" if exchange_verified else "FAILED",
    )


if __name__ == "__main__":
    asyncio.run(main())
