from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger("browser_use")


def _find_config() -> dict:
    cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    if cfg.exists():
        return json.loads(cfg.read_text())
    return {}


def _build_llm_client() -> dict | None:
    cfg = _find_config()
    provider = cfg.get("llm_provider", "ollama")
    llm_url = cfg.get("llm_url", "http://localhost:11434")
    llm_model = cfg.get("llm_model", "llama3.2")
    api_key = cfg.get("llm_api_key", "not-needed")

    base = llm_url.rstrip("/") + "/v1"

    if provider == "nvidia_nim":
        from browser_use.llm.openai.chat import ChatOpenAI

        model = llm_model.replace("nvidia/", "").replace("meta/", "")
        return {
            "client": ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base,
            ),
            "model": model,
        }

    if provider == "openai":
        from browser_use.llm.openai.chat import ChatOpenAI

        return {
            "client": ChatOpenAI(
                model=llm_model,
                api_key=api_key,
                base_url=base,
            ),
            "model": llm_model,
        }

    if provider in ("ollama", "openrouter"):
        from browser_use.llm.litellm.chat import ChatLiteLLM

        return {
            "client": ChatLiteLLM(
                model=f"openai/{llm_model}",
                api_base=base,
                api_key=api_key,
                num_retries=2,
            ),
            "model": llm_model,
        }

    from browser_use.llm.openai.chat import ChatOpenAI

    return {
        "client": ChatOpenAI(
            model=llm_model,
            api_key=api_key,
            base_url=base,
        ),
        "model": llm_model,
    }


def run_browser_use_task(
    task: str,
    timeout: int = 180,
    headless: bool = True,
    max_steps: int = 30,
    use_vision: bool = False,
) -> str:
    start = time.time()
    logger.info("browser-use task: %.80s", task)

    try:
        llm_info = _build_llm_client()
        if llm_info is None:
            return "No LLM client configured for browser-use."
        llm = llm_info["client"]
        model = llm_info["model"]

        from browser_use import Agent, BrowserSession

        browser = BrowserSession(
            headless=headless,
        )

        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=use_vision,
            max_failures=3,
            max_actions_per_step=5,
            use_thinking=True,
            max_steps=max_steps * 7,  # internal step budget
            generate_gif=False,
            step_timeout=timeout,
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            history = loop.run_until_complete(
                asyncio.wait_for(agent.run(max_steps=max_steps), timeout=timeout)
            )
        finally:
            loop.close()

        elapsed = time.time() - start
        result = history.final_result()
        if result:
            text = result.strip()
        else:
            text = str(history)
            if not text or text == "None":
                text = "Task completed but no result returned."

        logger.info("browser-use done in %.1fs: %.100s", elapsed, text)
        return text

    except asyncio.TimeoutError:
        logger.warning("browser-use timed out after %ds", timeout)
        return f"Task timed out after {timeout} seconds."
    except ImportError as e:
        logger.error("browser-use import error: %s", e)
        return f"browser-use library not available: {e}"
    except Exception as e:
        logger.exception("browser-use error")
        return f"browser-use error: {e}"
