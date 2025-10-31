import json
from typing import List, Dict, Any
from pathlib import Path

from app.core.llm import generate_text
from app.services.doc_parser import extract_text_from_docx


PLACEHOLDER_DETECTION_PROMPT = """You are analyzing a legal document draft to identify ALL dynamic placeholders that need to be filled in.

IMPORTANT: Look for placeholders in these formats:
- [TEXT IN BRACKETS] like [Company Name], [Investor Name], [Date of Safe]
- $[_____________] or [_____________] for amounts or blanks
- Any text in square brackets [ ]
- Any underscores or blanks meant to be filled: _____ or _____________
- DD/MM/YYYY, MM/DD/YYYY or similar date placeholders
- "TBD", "To Be Determined", or similar text indicating a value to be filled

A placeholder is ANY piece of text that varies per case/instance, such as:
- Names (person names, company names, party names)
- Dates (effective dates, expiry dates, birth dates)
- Amounts (money, percentages, quantities)
- Addresses (physical addresses, email addresses)
- Boolean choices (yes/no clauses, optional sections)
- Enum choices (predefined lists like "Option A, Option B, Option C")

For EACH placeholder you identify, provide:
- name: A short, descriptive identifier (e.g., "company_name", "investor_name", "purchase_amount", "date_of_safe")
- description: A human-readable description of what this field represents
- type: One of: text, date, number, party_name, address, money, boolean, enum
- required: true if this field must be filled, false if optional
- source_excerpt: The EXACT text from the document where this placeholder appears (preserve brackets, underscores, etc.)
- paragraph_index: The paragraph number (0-indexed) where this appears
- char_start: Character position in the paragraph where this starts (0-indexed)
- char_end: Character position in the paragraph where this ends (0-indexed)

Return ONLY a valid JSON array of placeholder objects. Do not include any explanatory text before or after the JSON.
The JSON must be valid and parseable.

Document text:
{document_text}

JSON array:
"""


def detect_placeholders(file_path: Path) -> List[Dict[str, Any]]:
    """Detect placeholders in a .docx file using Gemini."""
    import logging
    logger = logging.getLogger(__name__)
    
    full_text, paragraphs = extract_text_from_docx(file_path)
    logger.info(f"Extracted {len(full_text)} chars from document, {len(paragraphs)} paragraphs")
    
    # Use more text (Gemini 1.5 Flash can handle larger contexts)
    # Take first ~15000 chars to ensure we capture most of the document
    truncated_text = full_text[:15000] if len(full_text) > 15000 else full_text
    if len(full_text) > 15000:
        logger.warning(f"Document text truncated from {len(full_text)} to {len(truncated_text)} chars")
    
    prompt = PLACEHOLDER_DETECTION_PROMPT.format(document_text=truncated_text)
    logger.info("Sending placeholder detection request to Gemini...")
    
    response_text = generate_text(prompt)
    if not response_text:
        logger.error("Gemini returned empty response")
        return []
    
    logger.info(f"Received response from Gemini: {len(response_text)} chars")
    logger.debug(f"Response preview: {response_text[:500]}")
    
    # Try to extract JSON from response (might have markdown code blocks)
    response_text = response_text.strip()
    
    # Handle markdown code blocks
    if response_text.startswith("```json"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
        response_text = response_text.strip()
    elif response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
        response_text = response_text.strip()
    
    # Try to find JSON array in the response (in case there's extra text)
    import re
    json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group(0)
    
    try:
        placeholders = json.loads(response_text)
        if not isinstance(placeholders, list):
            logger.error(f"Gemini response is not a list: {type(placeholders)}")
            return []
        
        logger.info(f"Successfully parsed {len(placeholders)} placeholders from Gemini response")
        
        # Validate and normalize each placeholder
        validated = []
        for idx, p in enumerate(placeholders):
            if isinstance(p, dict) and "name" in p:
                # Find paragraph and char positions if not provided
                para_idx = p.get("paragraph_index")
                if para_idx is None:
                    # Try to find the paragraph containing the source_excerpt
                    source = p.get("source_excerpt", "")
                    for para_idx, (_, para_text) in enumerate(paragraphs):
                        if source in para_text:
                            char_start = para_text.find(source)
                            char_end = char_start + len(source) if char_start >= 0 else None
                            break
                    else:
                        para_idx = 0
                        char_start = None
                        char_end = None
                else:
                    char_start = p.get("char_start")
                    char_end = p.get("char_end")
                
                validated.append({
                    "name": p.get("name", ""),
                    "description": p.get("description"),
                    "type": p.get("type", "text"),
                    "required": p.get("required", True),
                    "source_excerpt": p.get("source_excerpt", ""),
                    "paragraph_index": para_idx,
                    "char_start": char_start,
                    "char_end": char_end,
                    "order_index": idx,  # Use detection order as default
                })
            else:
                logger.warning(f"Skipping invalid placeholder entry: {p}")
        
        logger.info(f"Validated {len(validated)} placeholders")
        return validated
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        logger.error(f"Response text (first 500 chars): {response_text[:500]}")
        logger.error(f"Response text (last 500 chars): {response_text[-500:] if len(response_text) > 500 else response_text}")
        return []

