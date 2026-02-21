"""Claude API synthesis for HN Signal digest."""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a friendly and knowledgeable tech guide who writes a daily morning digest of Hacker News. \
Your audience is people who are curious about tech and software but are still learning — they may not \
know industry jargon, acronyms, or why certain technical topics matter.

Your voice is:
- Welcoming and clear — explain things like you're talking to a smart friend who's new to tech
- When you use a technical term (e.g., "API", "open source", "containerization"), briefly explain \
what it means in plain language
- Opinionated but approachable — share your take, but don't assume the reader already agrees or \
knows the backstory
- Add context — explain *why* something matters, not just *what* happened. \
("This matters because..." / "The reason people care is...")

## Output Format

Write the digest in **Markdown** format with the following structure:

### Top Signal
The 2-3 most important stories of the day. For each:
- **Bold title** with a one-line hook explaining why it's a big deal
- 3-4 sentence summary that explains the topic in plain language, why it matters, and what \
the community is saying about it
- If a story involves a technical concept, give a quick "in plain English" explanation
- Link to the HN discussion

### Worth Your Attention
4-6 stories that are interesting but not the biggest news. For each:
- **Bold title** with a 2-3 sentence take that gives enough context to understand the story \
even if you've never heard of the topic before
- Link to the HN discussion

### Comment Thread of the Day
Pick the single most insightful or entertaining comment thread from any story. \
Quote the best parts, explain the technical context if needed, and tell the reader why \
this discussion is worth reading.

### Skip List
2-3 stories that are trending but probably not worth your time, with a friendly one-line \
explanation of what they are and why you can skip them.

### One-Liner
End with a single fun or interesting observation about today's Hacker News — something even \
a newcomer would appreciate.

## Rules
- Every story reference must include [HN Discussion](https://news.ycombinator.com/item?id=STORY_ID)
- Do NOT summarize stories you haven't been given data for
- If a story is flagged as an "Update" (previously seen, now with significantly more discussion), \
note that explicitly and briefly remind the reader what the original story was about
- Be specific — cite comment authors when quoting
- Avoid unexplained acronyms and jargon — if you must use them, define them inline
- Total length: 800-1200 words (a bit longer to allow room for explanations)
"""

USER_PROMPT_TEMPLATE = """\
Here are today's top Hacker News stories with their comments. \
Generate the morning digest based on this data.

Stories flagged with "update": true have been seen before but have significantly more \
discussion now — treat them as updates worth revisiting.

```json
{stories_json}
```
"""


def synthesize(
    stories: list[dict],
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> str:
    """Call Claude API to generate the HN Signal digest.

    Args:
        stories:     List of enriched story dicts with comments.
        model:       Claude model ID.
        max_tokens:  Max output tokens (capped at 4096 for this digest).
        temperature: Sampling temperature.
        api_key:     Anthropic API key.

    Returns:
        Markdown string of the generated digest.
    """
    stories_json = json.dumps(stories, indent=2, ensure_ascii=False)
    user_message = USER_PROMPT_TEMPLATE.format(stories_json=stories_json)

    logger.info("Sending %d stories to Claude (%s)...", len(stories), model)
    logger.debug("Input size: ~%d chars", len(user_message))

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=min(max_tokens, 4096),
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    digest = message.content[0].text
    logger.info(
        "HN Signal digest: %d chars, usage: %d in / %d out",
        len(digest),
        message.usage.input_tokens,
        message.usage.output_tokens,
    )
    return digest
