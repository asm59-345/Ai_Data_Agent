import os
from dotenv import load_dotenv

load_dotenv()


def pick_llm(level: str = "medium"):
    """
    Intelligently picks and initializes an LLM instance based on available API keys
    and required task complexity.
    Tested and verified with Google Gemini (gemini-flash-latest).
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    # Priority 1: Google Gemini (Active & Verified)
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=gemini_key,
                temperature=0,
            )
        except Exception as e:
            print(f"[pick_llm] Gemini init warning: {e}")

    # Priority 2: Direct OpenAI
    if openai_key:
        from langchain_openai import ChatOpenAI
        lvl = level.lower().strip()
        model_name = "gpt-4o" if lvl in ["high", "claude"] else "gpt-4o-mini"
        return ChatOpenAI(
            model=model_name,
            api_key=openai_key,
            temperature=0,
        )

    # Priority 3: Anthropic
    if anthropic_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model_name="claude-3-5-sonnet-20241022",
            anthropic_api_key=anthropic_key,
            temperature=0,
        )

    # Priority 4: OpenRouter
    if openrouter_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.environ.get("LLM_MODEL_MEDIUM", "openai/gpt-4o-mini"),
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )

    raise ValueError(
        "No working LLM API key detected! Please check GEMINI_API_KEY, OPENAI_API_KEY, "
        "or ANTHROPIC_API_KEY in your .env file."
    )


if __name__ == "__main__":
    llm = pick_llm("medium")
    print("Testing pick_llm:")
    print(llm.invoke("Hi").content)