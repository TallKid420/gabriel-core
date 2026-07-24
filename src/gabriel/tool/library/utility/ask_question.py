"""ask_question — surface a question to the human in the loop.

This tool is a no-op from an execution standpoint: it returns a structured
payload that the agent runtime MUST surface to the user and wait for a reply
before continuing the workflow.
"""

from __future__ import annotations
from langchain_core.tools import tool


@tool
async def ask_question(question: str, context: str = "") -> dict:
    """Pause the workflow and ask the user a question.

    The agent runtime must detect this response type and halt execution until
    a human reply is received.  The reply should be re-injected into the
    agent's conversation context.

    Args:
        question: The question to present to the user.
        context:  Optional additional context explaining why the question
                  is being asked.

    Returns:
        ``{"type": "human_input_required", "question": ..., "context": ...}``.
    """
    return {
        "type": "human_input_required",
        "question": question,
        "context": context,
    }
