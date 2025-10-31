from typing import List, Dict, Any, Optional, Tuple
import json
import re
from app.core.llm import generate_text
from app.models.domain import Placeholder, Answer

def get_field_examples(field_type: str, field_name: str) -> str:
    """Get 1-2 examples for a field type."""
    examples_map = {
        "text": [
            "Acme Corporation",
            "John Smith",
        ],
        "party_name": [
            "TechStart Inc.",
            "Jane Doe, Esq.",
        ],
        "company_name": [
            "Innovation Labs LLC",
            "Global Systems Corp",
        ],
        "date": [
            "January 15, 2024",
            "12/31/2024",
        ],
        "money": [
            "$50,000.00",
            "100000",
        ],
        "number": [
            "25",
            "1,500",
        ],
        "address": [
            "123 Main Street, New York, NY 10001",
            "456 Business Park, Suite 200, San Francisco, CA 94105",
        ],
        "boolean": [
            "Yes",
            "No",
        ],
        "enum": [
            "Option A",
            "Option B",
        ],
    }
    
    # Try to get examples based on type
    examples = examples_map.get(field_type.lower(), examples_map.get("text", []))
    
    # Also check if field name gives hints
    name_lower = field_name.lower()
    if "company" in name_lower or "corporation" in name_lower:
        examples = examples_map.get("company_name", examples)
    elif "date" in name_lower:
        examples = examples_map.get("date", examples)
    elif "amount" in name_lower or "money" in name_lower or "price" in name_lower:
        examples = examples_map.get("money", examples)
    elif "address" in name_lower:
        examples = examples_map.get("address", examples)
    
    # Return 1-2 examples
    return ", ".join(examples[:2])


AGENT_ANALYSIS_PROMPT = """You are an intelligent agent analyzing a user's message in a conversational document-filling context.

CURRENT TASK:
We are filling out a legal document field by field. The user is in a conversational flow.

CURRENT FIELD BEING FILLED:
- Name: {placeholder_name}
- Description: {placeholder_description}
- Type: {placeholder_type}
- Appears in document as: "{source_excerpt}"

EXAMPLES for this field type:
{field_examples}

NEXT FIELD (if current is accepted):
{next_field_info}

CONTEXT:
Fields already completed (user can edit these by mentioning the field name):
{previous_answers}

Recent conversation (last 8 messages):
{conversation_history}

CURRENT USER MESSAGE: "{user_message}"

YOUR MISSION:
Analyze this message deeply and determine:

1. **INTENT**: What is the user really trying to communicate?
   - ANSWER: Providing information to fill the current field
   - QUESTION: Asking for clarification/help
   - CORRECTION: Fixing a previous answer (e.g., "change company name to X" or "the date should be Y")
   - EDIT_FIELD: User is trying to edit a previously filled field by mentioning its name (e.g., "change the company name" or "update investor name")
   - UNCLEAR: Ambiguous or incomplete response
   - IRRELEVANT: Not related to the current field

2. **FIELD EDIT DETECTION**: Check if user is trying to edit a previously filled field.
   - Look for patterns like: "change [field_name]", "edit [field_name]", "update [field_name]", "fix [field_name]"
   - Check previous_answers to find matching field names
   - If user mentions a field name from previous_answers, this is EDIT_FIELD intent

3. **VALUE EXTRACTION**: If the user provided an answer, extract the ACTUAL VALUE.
   - Look for the substantive information, even if embedded in conversational text
   - Clean up the value (normalize dates, numbers, names)
   - Examples:
     * "My company is called TechCorp Inc" → extract: "TechCorp Inc"
     * "It's $50,000" → extract: "50000" or "50000.00"
     * "January 15, 2024" → extract: "2024-01-15"
     * "Yeah, that's correct" → might be confirming previous answer
     * "I think it's around 100k" → extract: "100000"

4. **VALIDATION**: Is the extracted/normalized value appropriate?
   - Does it match the field type ({placeholder_type})?
   - Is it reasonable in a legal document context?
   - Is it complete enough to use?

5. **SHOULD ACCEPT**: Should we accept this as the answer and move forward?
   - Only accept if: clear intent=ANSWER or EDIT_FIELD, valid value extracted, appropriate for field type
   - Don't accept if: unclear, wrong type, incomplete, or user is asking questions

6. **ASSISTANT RESPONSE**: Generate a natural, helpful response:
   - ALWAYS include 1-2 examples when asking for a new field (use the examples provided above)
   - Format: "I need the [field name]. For example: [example1] or [example2]. What would you like to use?"
   - If accepting: Warmly confirm the value you understood, then NATURALLY transition to asking about the next field (if available). Make it feel like a smooth conversation flow.
   - If unclear: Ask SPECIFIC clarifying questions with examples (not generic "please provide")
   - If wrong type: Explain what's needed with examples from the field_examples above
   - If question: Answer helpfully, then guide back to collecting the value with examples
   - If EDIT_FIELD: Acknowledge the edit request and ask for the new value

IMPORTANT:
- Be intelligent and contextual - understand conversational nuances
- Extract values from natural language, not just exact formats
- Don't be overly strict - "yes" for a boolean, "TechCorp" for company name is fine
- Be agentic - make intelligent decisions based on context
- ALWAYS provide examples when asking for a field value

Return your analysis as JSON:
{{
  "intent": "ANSWER|QUESTION|CORRECTION|EDIT_FIELD|UNCLEAR|IRRELEVANT",
  "target_field": "field name if intent is EDIT_FIELD, null otherwise",
  "extracted_value": "the cleaned/normalized value if intent is ANSWER or EDIT_FIELD, null otherwise",
  "is_valid": true/false,
  "should_accept": true/false,
  "reasoning": "brief explanation of your analysis",
  "assistant_message": "your natural conversational response to the user (MUST include examples when asking for a new field)"
}}

Respond ONLY with valid JSON, no other text.
"""


def generate_chat_message(
    placeholder: Placeholder,
    user_message: str,
    previous_answers: List[Dict[str, str]],
    existing_answer: Optional[Answer] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    next_placeholder: Optional[Placeholder] = None,
) -> tuple[str, bool, Optional[str], Optional[str]]:
    """
    Generate assistant message and determine if answer is accepted using LLM agent analysis.
    Returns (assistant_message, answer_accepted, extracted_value, target_field_name).
    
    Args:
        conversation_history: List of previous messages in format [{"role": "user|assistant", "content": "..."}]
    
    Returns:
        tuple: (assistant_message, answer_accepted, extracted_value, target_field_name)
        - target_field_name: If user wants to edit a different field, this is the field name
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Format previous answers for context (with field names for editing)
    prev_context = "\n".join([
        f"- {p['name'].replace('_', ' ').title()}: {p['value']}" for p in previous_answers
    ]) or "No fields have been filled yet."
    
    # Format conversation history (last 8 messages for better context)
    history_text = ""
    if conversation_history:
        recent = conversation_history[-8:]  # Last 8 messages
        history_text = "\n".join([
            f"{msg['role'].capitalize()}: {msg['content']}" 
            for msg in recent
        ])
    else:
        history_text = "This is the start of the conversation."
    
    # Add existing answer context if present
    if existing_answer:
        history_text += f"\n\nNote: There was a previous answer for this field: '{existing_answer.value}'"
    
    # Format next field info if available
    next_field_info = "No next field - this is the last one." if not next_placeholder else (
        f"- Name: {next_placeholder.name.replace('_', ' ').title()}\n"
        f"- Description: {next_placeholder.description or f'A {next_placeholder.type} field'}\n"
        f"- Type: {next_placeholder.type}"
    )
    
    # Get examples for this field type
    field_examples = get_field_examples(placeholder.type, placeholder.name)
    
    # Use LLM agent to analyze the message
    prompt = AGENT_ANALYSIS_PROMPT.format(
        placeholder_name=placeholder.name.replace("_", " ").title(),
        placeholder_description=placeholder.description or f"A {placeholder.type} field",
        placeholder_type=placeholder.type,
        source_excerpt=placeholder.source_excerpt or "[field]",
        field_examples=field_examples,
        next_field_info=next_field_info,
        previous_answers=prev_context,
        conversation_history=history_text,
        user_message=user_message
    )
    
    analysis_text = generate_text(prompt)
    if not analysis_text:
        logger.warning("LLM returned empty analysis")
        # Fallback response
        assistant_msg = f"I need a value for {placeholder.name.replace('_', ' ')}. {placeholder.description or 'Please provide the information.'}"
        return assistant_msg, False, None
    
    # Try to parse JSON from response
    analysis_text = analysis_text.strip()
    
    # Handle markdown code blocks
    if analysis_text.startswith("```json"):
        lines = analysis_text.split("\n")
        analysis_text = "\n".join(lines[1:-1]) if len(lines) > 2 else analysis_text
        analysis_text = analysis_text.strip()
    elif analysis_text.startswith("```"):
        lines = analysis_text.split("\n")
        analysis_text = "\n".join(lines[1:-1]) if len(lines) > 2 else analysis_text
        analysis_text = analysis_text.strip()
    
    # Try to find JSON object in response
    json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
    if json_match:
        analysis_text = json_match.group(0)
    
    try:
        analysis = json.loads(analysis_text)
        
        intent = analysis.get("intent", "").upper()
        extracted_value = analysis.get("extracted_value")
        target_field = analysis.get("target_field")
        is_valid = analysis.get("is_valid", False)
        should_accept = analysis.get("should_accept", False)
        assistant_msg = analysis.get("assistant_message", "")
        reasoning = analysis.get("reasoning", "")
        
        logger.info(f"Agent analysis - Intent: {intent}, Target Field: {target_field}, Valid: {is_valid}, Accept: {should_accept}, Reasoning: {reasoning}")
        
        # Final validation logic
        answer_accepted = False
        final_value = None
        
        if intent in ["ANSWER", "CORRECTION", "EDIT_FIELD"]:
            # User is trying to provide an answer
            if should_accept and is_valid:
                candidate_value = None
                
                if extracted_value and extracted_value.lower() not in ["null", "none", ""]:
                    candidate_value = str(extracted_value).strip()
                elif user_message.strip():
                    candidate_value = user_message.strip()
                
                # Validate that we're not using a field name/description as the value
                if candidate_value:
                    value_lower = candidate_value.lower()
                    placeholder_name_lower = placeholder.name.lower().replace("_", " ")
                    placeholder_desc_lower = (placeholder.description or "").lower()
                    
                    # Reject if it looks like a field name rather than actual value
                    is_field_name = (
                        value_lower == placeholder_name_lower or
                        value_lower == f"the {placeholder_name_lower}" or
                        value_lower == placeholder_desc_lower or
                        (value_lower.startswith("the ") and placeholder_name_lower in value_lower)
                    )
                    
                    if not is_field_name:
                        answer_accepted = True
                        final_value = candidate_value
                        logger.info(f"Accepting answer: {final_value}")
                    else:
                        logger.warning(f"Rejected field name as value: {candidate_value}")
                        # If extracted value was a field name, try to extract from original message
                        # Look for actual content in user_message that isn't the field name
                        user_clean = user_message.strip()
                        # Try to find the actual value - remove field name patterns
                        for pattern in [f"the {placeholder_name_lower}", placeholder_name_lower, placeholder_desc_lower]:
                            if pattern in user_clean.lower():
                                # Remove the pattern and try to get what's left
                                parts = user_clean.lower().split(pattern)
                                for part in parts:
                                    if part.strip() and part.strip() not in ["is", ":", "="]:
                                        final_value = part.strip()
                                        answer_accepted = True
                                        logger.info(f"Extracted value from user message after filtering field name: {final_value}")
                                        break
                                break
                        if not answer_accepted:
                            # Last resort: use original message if it's longer/different
                            if len(user_clean) > len(candidate_value):
                                final_value = user_clean
                                answer_accepted = True
                                logger.info(f"Using original message as value: {final_value}")
        
        # Ensure we have a valid assistant message
        if not assistant_msg or len(assistant_msg.strip()) < 5:
            # Generate fallback message with examples
            field_examples = get_field_examples(placeholder.type, placeholder.name)
            examples_text = f" For example: {field_examples}." if field_examples else ""
            
            if intent == "QUESTION":
                assistant_msg = f"I understand you have a question. {placeholder.description or 'Could you provide the value for this field?'}{examples_text}"
            elif intent == "UNCLEAR":
                assistant_msg = f"I need more clarity. For {placeholder.name.replace('_', ' ')}, I need: {placeholder.description or 'a value'}.{examples_text}"
            elif intent == "EDIT_FIELD":
                assistant_msg = f"I understand you want to edit {target_field or 'a field'}. What should the new value be?{examples_text}"
            else:
                assistant_msg = f"I need a value for {placeholder.name.replace('_', ' ')}. {placeholder.description or 'Please provide the information.'}{examples_text}"
        
        return assistant_msg, answer_accepted, final_value, target_field
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM analysis as JSON: {e}")
        logger.error(f"Response was: {analysis_text[:500]}")
        
        # Fallback: Use LLM to generate response and basic intent detection
        fallback_prompt = f"""User message: "{user_message}"
        
Current field: {placeholder.name} ({placeholder.type})
Context: {placeholder.description or 'A field in a legal document'}

Is the user providing an answer? Respond with just "YES" or "NO":"""
        
        intent_check = generate_text(fallback_prompt)
        is_answer = intent_check and "YES" in intent_check.upper()
        
        response_prompt = f"""Generate a natural conversational response. User said: "{user_message}"
        
We're collecting: {placeholder.name} - {placeholder.description or placeholder.type}

Keep it short and helpful:"""
        
        field_examples = get_field_examples(placeholder.type, placeholder.name)
        examples_text = f" For example: {field_examples}." if field_examples else ""
        assistant_msg = generate_text(response_prompt) or f"I need a value for {placeholder.name.replace('_', ' ')}.{examples_text}"
        
        answer_accepted = is_answer and len(user_message.strip()) > 1
        
        return assistant_msg, answer_accepted, user_message.strip() if answer_accepted else None, None

