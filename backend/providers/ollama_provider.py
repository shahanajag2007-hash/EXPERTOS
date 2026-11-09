import requests

from config import (
    OLLAMA_URL,
    MAX_TOKENS,
    TEMPERATURE,
)

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
            raise Exception(
                "Ollama returned no response."
            )

        text = text.strip()

        if text == "":
            raise Exception(
                "Ollama returned an empty response."
            )

        return text

    except Exception as e:

        raise Exception(
            f"Ollama Provider Error: {e}"
        )