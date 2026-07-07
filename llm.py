"""
llm.py — one place that builds the chat model.

Every agent that needs to "think" imports get_llm() from here. Keeping it in
one spot means you can swap providers (Groq -> Claude) by editing ONE function,
not every agent.
"""

from langchain_groq import ChatGroq

import config


def get_llm(temperature: float = 0.0):
    """Return the shared chat model.

    temperature=0.0 makes output as deterministic as possible — good for
    extraction/parsing where we want the same answer every time.

    To switch to Claude later:
      1. add ANTHROPIC_API_KEY to .env
      2. pip install langchain-anthropic
      3. swap the two lines below for:
           from langchain_anthropic import ChatAnthropic
           return ChatAnthropic(model="claude-opus-4-8", temperature=temperature)
    LangChain gives both models the same .invoke() interface, so no agent code
    changes.
    """
    config.require("GROQ_API_KEY")   # fail loudly & early if the key is missing
    return ChatGroq(
        model="llama-3.3-70b-versatile",   # a capable, free Groq model
        temperature=temperature,
    )
