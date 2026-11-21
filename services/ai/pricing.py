"""Per-token list prices used for cost estimates (USD per 1M tokens). Checked 2026-11-21.
Gemini 2.5 Flash: ai.google.dev/gemini-api/docs/pricing (paid tier, text) — $0.30 in / $2.50 out.
Groq Llama 3.3 70B Versatile: groq.com pricing — $0.59 in / $0.79 out.
Local Ollama and the rules fallback have no per-token charge."""

PRICES = {"gemini": (0.30, 2.50), "groq": (0.59, 0.79), "ollama": (0.0, 0.0), "rules": (0.0, 0.0)}
SOURCE_NOTE = ("Gemini 2.5 Flash $0.30/$2.50 and Groq Llama 3.3 70B $0.59/$0.79 per 1M input/output tokens "
               "(list prices checked 2026-11-21).")


def cost_usd(provider, tokens_in, tokens_out):
    pin, pout = PRICES.get(provider, (0.0, 0.0))
    return (tokens_in * pin + tokens_out * pout) / 1_000_000
