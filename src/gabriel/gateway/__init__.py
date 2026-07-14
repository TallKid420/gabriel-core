"""Gabriel Gateway — the AI Runtime layer (Phase 3).

The Gateway orchestrates LLM calls on behalf of agents. It owns *no*
persistent business data: conversations, messages, and agents are Universal
Resources managed by their own slices (Phase 2). The Gateway consumes them to
assemble prompts, streams model output, executes runtime tools requested by
the model, and persists the resulting turns back through the Phase 2
services.

Sub-packages / modules
----------------------
providers/   LLM provider abstraction (protocol, registry, Ollama).
prompt.py    Prompt assembly (system prompt + history + injected context).
tools.py     Runtime tool framework (interface, registry, built-ins).
sessions.py  Ephemeral chat session tracking.
service.py   ChatRuntimeService — end-to-end streaming orchestration.
"""
