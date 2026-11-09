import google.generativeai as genai

from services.errors import ProviderError, EMPTY

from config import (
    GEMINI_API_KEY,
    MODEL,
    MAX_TOKENS,
    TEMPERATURE,
)

# REST transport: the default gRPC transport can retry network failures
# indefinitely and ignore the request timeout.
genai.configure(
    api_key=GEMINI_API_KEY,
    transport="rest"
)

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)


# gemini-2.5-flash "thinks" before answering, and those hidden tokens count
# against max_output_tokens. Measured: with a 400-token cap a 3-sentence answer
# used 395 thinking tokens and was cut off after 16 visible ones
# (finish_reason=MAX_TOKENS). This SDK can't turn thinking off, so the cap gets
# headroom. It's only a ceiling: short answers don't take longer.
THINKING_HEADROOM = 2048


def generate(
    prompt,
    max_tokens=None,
    temperature=None,
    images=None
):

    generation_config = genai.types.GenerationConfig(

        temperature=(
            temperature
            if temperature is not None
            else TEMPERATURE
        ),

        max_output_tokens=(
            max_tokens
            if max_tokens is not None
            else MAX_TOKENS
        ) + THINKING_HEADROOM

    )

    try:

        # Images ([{"mime", "data"}]) are sent as inline parts after the text.
        contents = [prompt] + [
            {"mime_type": image["mime"], "data": image["data"]} for image in images or []
        ]

        response = model.generate_content(

            contents if images else prompt,

            generation_config=generation_config,

            # Without a timeout the gRPC client keeps retrying network
            # failures and blocks the request indefinitely.
            request_options={"timeout": 45}

        )

        if not hasattr(response, "text"):

            raise Exception(
                "Gemini returned an empty response."
            )

        text = response.text

        if text is None:

            raise Exception(
                "Gemini returned None."
            )

        text = text.strip()

        if text == "":

            raise Exception(
                "Gemini returned a blank response."
            )

        # Never pass on an answer that was cut off mid-sentence; let the
        # router try the next provider instead.
        candidates = getattr(response, "candidates", None) or []
        reason = getattr(getattr(candidates[0], "finish_reason", None), "name", "") if candidates else ""
        if reason == "MAX_TOKENS":
            raise ProviderError(EMPTY, "Gemini response was truncated (MAX_TOKENS).")

        return text

    except ProviderError:
        raise
