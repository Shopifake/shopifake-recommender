"""Routes for the FAQ chatbot that answers common questions."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from src.config import settings
from src.models.faq import FaqRequest, FaqResponse
from src.services.clients.decoder_client import DecoderDependency

router = APIRouter(prefix="/faq", tags=["faq"])
logger = logging.getLogger(__name__)

FAQ_CONTENT_FILE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "faq_content.txt"
)


def _load_faq_content() -> str:
    """Load the FAQ content from the text file.

    Returns:
        The FAQ content as a string, with comment lines removed.

    Raises:
        FileNotFoundError: If the FAQ content file does not exist.
    """
    faq_file_exists = FAQ_CONTENT_FILE_PATH.exists()

    if not faq_file_exists:
        raise FileNotFoundError(
            f"FAQ content file not found at: {FAQ_CONTENT_FILE_PATH}"
        )

    raw_content = FAQ_CONTENT_FILE_PATH.read_text(encoding="utf-8")

    # Filter out comment lines (starting with #) and empty lines
    content_lines = []
    for line in raw_content.splitlines():
        line_is_comment = line.strip().startswith("#")
        line_is_empty = not line.strip()

        if not line_is_comment and not line_is_empty:
            content_lines.append(line)

    return "\n".join(content_lines)


def _build_system_prompt(faq_content: str) -> str:
    """Build the system prompt that includes the FAQ content.

    Args:
        faq_content: The FAQ questions and answers to include.

    Returns:
        A formatted system prompt string.
    """
    system_prompt_template = """You are a helpful FAQ assistant for Shopifake, an e-commerce platform.
Your role is to answer user questions based ONLY on the information provided in the FAQ below.

INSTRUCTIONS:
- Answer questions clearly and concisely.
- If the question is not covered by the FAQ, politely explain that you cannot help with that specific question and suggest contacting support.
- Be friendly and professional.
- Answer in the same language as the user's question.

FAQ CONTENT:
{faq_content}

Remember: Only use information from the FAQ above to answer questions."""

    formatted_system_prompt = system_prompt_template.format(faq_content=faq_content)
    return formatted_system_prompt


def _format_conversation_history(request: FaqRequest) -> str:
    """Format the conversation history into a prompt-friendly string.

    Args:
        request: The FAQ request containing the conversation history.

    Returns:
        A formatted string representing the conversation history.
    """
    history_has_entries = len(request.conversation_history) > 0

    if not history_has_entries:
        return ""
    formatted_entries = []
    for entry in request.conversation_history:
        role_label = "User" if entry.role == "user" else "Assistant"
        formatted_entry = f"{role_label}: {entry.content}"
        formatted_entries.append(formatted_entry)

    conversation_lines = "\n".join(formatted_entries)
    header = "PREVIOUS CONVERSATION:\n"
    trailing_newlines = "\n\n"

    return header + conversation_lines + trailing_newlines


def _build_full_prompt(
    system_prompt: str, conversation_context: str, user_message: str
) -> str:
    """Assemble the complete prompt for the decoder.

    Args:
        system_prompt: The system instructions and FAQ content.
        conversation_context: The formatted conversation history.
        user_message: The current user question.

    Returns:
        The complete prompt string to send to the decoder.
    """
    prompt_parts = [
        system_prompt,
        "\n\n",
        conversation_context,
        f"User: {user_message}\n\n",
        "Assistant:",
    ]
    return "".join(prompt_parts)


@router.post(
    "/answer",
    response_model=FaqResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a FAQ question",
    description="Process a user question and return an answer based on the FAQ content.",
)
async def answer_faq_question(
    payload: FaqRequest,
    decoder: DecoderDependency,
) -> FaqResponse:
    """Process a FAQ question and return an answer.

    The endpoint loads the FAQ content, builds a prompt with the conversation
    history, and uses the decoder (LLM) to generate an appropriate response.

    Args:
        payload: The request containing the user's question and conversation history.
        decoder: The decoder client for generating responses.

    Returns:
        A FaqResponse containing the generated answer.

    Raises:
        HTTPException: If the decoder is not available (503) or FAQ content is missing (500).
    """
    decoder_is_available = settings.decoder_enabled and decoder is not None

    if not decoder_is_available:
        logger.warning("FAQ answer requested but decoder is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Decoder is not configured in this environment",
        )

    try:
        faq_content = _load_faq_content()
    except FileNotFoundError as error:
        logger.error("FAQ content file not found: %s", error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FAQ content is not available",
        ) from error

    system_prompt = _build_system_prompt(faq_content)
    conversation_context = _format_conversation_history(payload)
    full_prompt = _build_full_prompt(
        system_prompt, conversation_context, payload.message
    )

    logger.info(
        "Processing FAQ question",
        extra={
            "message_preview": payload.message[:100],
            "history_length": len(payload.conversation_history),
        },
    )

    answer = await decoder.decode(full_prompt)

    logger.info(
        "FAQ answer generated",
        extra={
            "answer_preview": answer[:200] if answer else "",
            "answer_length": len(answer) if answer else 0,
        },
    )

    return FaqResponse(answer=answer)
