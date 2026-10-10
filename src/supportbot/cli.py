"""Terminal chat with the support bot.

    python -m supportbot.cli            # chat
    python -m supportbot.cli --debug    # also show search query, scores and tokens
"""

from __future__ import annotations

import argparse

from .chatbot import ChatSession, SupportBot


def main() -> None:
    parser = argparse.ArgumentParser(description="Lumio Pay support assistant (RAG demo)")
    parser.add_argument("--debug", action="store_true", help="show retrieval details for each turn")
    args = parser.parse_args()

    print("Loading knowledge base...")
    session = ChatSession(SupportBot())
    print("Lumio Pay virtual assistant. Type 'exit' to quit, 'reset' to start a new conversation.\n")

    while True:
        try:
            message = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.strip().lower() in {"exit", "quit"}:
            break
        if message.strip().lower() == "reset":
            session.reset()
            print("(conversation cleared)\n")
            continue

        response = session.send(message)
        print(f"\nBot: {response.answer}")
        if response.sources:
            cited = ", ".join(f"{c.source} > {c.section}" for c in response.sources)
            print(f"     Sources: {cited}")
        if args.debug:
            print(
                f"     [status={response.status} reason={response.reason or '-'} "
                f"needs_human={response.needs_human} top_score={response.top_score} "
                f"query={response.search_query!r} latency={response.latency_ms}ms "
                f"tokens={response.usage.input_tokens}in/{response.usage.output_tokens}out]"
            )
        print()


if __name__ == "__main__":
    main()
