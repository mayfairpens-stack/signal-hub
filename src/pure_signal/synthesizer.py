"""
AI-powered content synthesis using Claude API — Pure Signal persona.
"""

import logging
from datetime import datetime
from typing import Optional
import anthropic

logger = logging.getLogger(__name__)


class DigestSynthesizer:
    """
    Synthesizes content from multiple AI researchers into a coherent,
    TTS-optimized daily digest using Claude.
    """

    SYSTEM_PROMPT = """You are an expert AI researcher and science communicator creating a daily audio digest about frontier AI progress. Your audience is intelligent professionals building expertise in AI—they want depth, not dumbed-down summaries.

Your task is to synthesize the provided content into an engaging, narrative digest optimized for text-to-speech delivery.

CRITICAL RULES:

1. THEMATIC GROUPING: Analyze all content and identify themes multiple people are discussing. Group people together by theme. Show how different experts converge on insights or approach problems differently. Only present someone standalone if their content doesn't fit with others.

2. TTS OPTIMIZATION:
   - Short, punchy sentences (15-20 words max)
   - Vary sentence length for rhythm
   - Use em dashes (—) for natural pauses
   - Spell out acronyms first time: "retrieval augmented generation—or RAG"
   - Write numbers as words: "five" not "5"
   - Natural transitions: "Here's what's interesting..." "This connects to..."

3. INLINE DEFINITIONS: Integrate brief technical explanations smoothly:
   - "quantization—compressing models to use less memory—is enabling..."
   - Don't explain everything, just concepts where a quick definition adds clarity

4. CONTENT FOCUS:
   - Lead with main arguments and findings
   - Include supporting reasoning inline
   - Omit metadata (where posted, URLs, titles)
   - Get directly into substantive content
   - Show connections between different researchers' takes

5. STRUCTURE:
   - Opening hook that captures attention
   - Thematic sections (60-90 seconds each when read aloud)
   - Paragraph breaks for natural pauses
   - Closing thought tying themes together

6. VOICE:
   - Knowledgeable friend briefing a colleague
   - Conversational but substantive
   - Show enthusiasm without hyperbole
   - Explain why things matter, not just what happened

EXCLUDE from the digest:
- Funding/investment news
- Hiring/leadership changes
- Pure regulatory news
- Product launches without new capabilities
- Surface-level commentary

FORMAT YOUR OUTPUT AS:
---
**PURE SIGNAL**
[Date]

[Opening hook]

**[THEME 1: Descriptive Title]**

[Narrative content weaving together perspectives]

**[THEME 2: Descriptive Title]**

[Narrative content]

[Closing thought]
---"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8000,
        temperature: float = 0.7
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _format_content_for_synthesis(self, items: list) -> str:
        by_person = {}
        for item in items:
            if item.person_id not in by_person:
                by_person[item.person_id] = {'name': item.person_name, 'items': []}
            by_person[item.person_id]['items'].append(item)

        sections = []
        for person_id, data in by_person.items():
            person_section = f"\n## {data['name']}\n"
            for item in data['items']:
                person_section += f"\n### {item.title}\n"
                person_section += f"Source: {item.source_name}\n"
                person_section += f"Published: {item.published.strftime('%Y-%m-%d %H:%M UTC')}\n"
                person_section += f"\n{item.content}\n"
            sections.append(person_section)

        return "\n---\n".join(sections)

    def synthesize(self, items: list, date: Optional[datetime] = None) -> str:
        if not items:
            logger.info("No content to synthesize")
            return ""

        if date is None:
            date = datetime.now()

        formatted_content = self._format_content_for_synthesis(items)
        people_count = len(set(item.person_id for item in items))
        logger.info(f"Synthesizing {len(items)} items from {people_count} people")

        user_prompt = f"""Today's date: {date.strftime('%B %d, %Y')}

Here is the content from the past 24 hours to synthesize into today's digest:

{formatted_content}

Create the daily digest following all the rules in your instructions. Remember:
- Group by themes, not individuals
- Optimize for text-to-speech
- Weave perspectives together narratively
- Keep sentences short and punchy
- Include smooth inline definitions for technical terms"""

        try:
            logger.info(f"Calling Claude API ({self.model})")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )
            digest = response.content[0].text
            logger.info(
                f"Pure Signal synthesis complete. "
                f"Input tokens: {response.usage.input_tokens}, "
                f"Output tokens: {response.usage.output_tokens}"
            )
            return digest
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise
