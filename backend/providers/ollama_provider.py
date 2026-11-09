import requests

from config import (
    OLLAMA_URL,
    MAX_TOKENS,
    TEMPERATURE,
)
from services.errors import ProviderError, TIMEOUT, CONNECTION, SERVER, EMPTY, UNKNOWN

MODEL = "deepseek-r1:8b"


def generate(
    prompt,
    max_tokens=None,
    temperature=None
):

    try:

        response = requests.post(

            f"{OLLAMA_URL}/api/generate",

            json={

                "model": MODEL,

                "prompt": prompt,

                "stream": False,

                "options": {

                    "temperature":
                        temperature
                        if temperature is not None
                        else TEMPERATURE,

                    "num_predict":
                        max_tokens
                        if max_tokens is not None
                        else MAX_TOKENS

                }

            },

            timeout=120

        )

        response.raise_for_status()

        data = response.json()

        text = data.get("response")

        if text is None:
            raise ProviderError(EMPTY, "Ollama returned no response.")

        text = text.strip()

        if text == "":
            raise ProviderError(EMPTY, "Ollama returned an empty response.")

        return text

    except ProviderError:
        raise

    except requests.exceptions.Timeout:
        raise ProviderError(TIMEOUT, "Ollama request timed out after 120s.")

    except requests.exceptions.ConnectionError as e:
        raise ProviderError(CONNECTION, f"Ollama unreachable: {e}")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status is not None and status >= 500:
            raise ProviderError(SERVER, f"Ollama HTTP {status}")
        raise ProviderError(UNKNOWN, f"Ollama HTTP error: {e}")

    except Exception as e:
        raise ProviderError(UNKNOWN, f"Ollama unexpected error: {e}")
