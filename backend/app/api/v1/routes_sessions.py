from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import select, Session
import json

from app.core.db import get_session
from app.models.domain import SessionModel, Document, Placeholder, Answer
from app.services.conversation import generate_chat_message


router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    document_id: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    assistant: str
    progress: dict


@router.post("")
def create_session(
    req: CreateSessionRequest,
    session: Session = Depends(get_session),
):
    doc = session.get(Document, req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    s = SessionModel(document_id=req.document_id, state="pending")
    session.add(s)
    session.flush()
    return {"session_id": s.id, "document_id": s.document_id}


@router.get("/{session_id}")
def get_session_info(session_id: str, session: Session = Depends(get_session)):
    s = session.get(SessionModel, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": s.id,
        "document_id": s.document_id,
        "state": s.state,
        "started_at": s.started_at,
    }


@router.post("/{session_id}/chat")
def chat(
    session_id: str,
    req: ChatRequest,
    session: Session = Depends(get_session),
) -> ChatResponse:
    s = session.get(SessionModel, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get all placeholders for this document
    placeholders = session.exec(
        select(Placeholder).where(Placeholder.document_id == s.document_id).order_by(Placeholder.order_index)
    ).all()

    if not placeholders:
        return ChatResponse(
            assistant="No placeholders found for this document. Please upload and parse the document first.",
            progress={"filled": 0, "total": 0},
        )

    # Get existing answers
    answers = session.exec(
        select(Answer).where(Answer.session_id == session_id)
    ).all()
    answered_map = {a.placeholder_id: a for a in answers if a.value}
    answered_ids = set(answered_map.keys())

    # Build previous answers context (needed for edit detection)
    prev_answers = []
    for p in placeholders:
        if p.id in answered_map:
            prev_answers.append({
                "name": p.name,
                "value": answered_map[p.id].value or "",
            })

    # Check if user message contains edit intent BEFORE checking if all fields are filled
    # This allows editing even when all fields are completed
    conversation_history_for_edit_check = [{"role": "user", "content": req.message}]
    
    # Use a temporary placeholder to check for edit intent
    # We'll use the first placeholder just to check intent, then switch if needed
    temp_placeholder = placeholders[0] if placeholders else None
    
    # Quick check: does the message mention editing a field?
    message_lower = req.message.lower()
    edit_keywords = ["change", "edit", "update", "fix", "modify", "correct"]
    is_potential_edit = any(keyword in message_lower for keyword in edit_keywords) and len(prev_answers) > 0
    
    # Initialize target_field_from_message (will be set if edit intent detected)
    target_field_from_message = None
    if is_potential_edit and temp_placeholder:
        # Generate a chat message to detect edit intent
        try:
            _, _, _, detected_target = generate_chat_message(
                temp_placeholder,
                req.message,
                prev_answers,
                None,
                conversation_history_for_edit_check,
                None,
            )
            if detected_target:
                target_field_from_message = detected_target
        except:
            pass  # Fall through to normal flow

    # Find next unanswered placeholder (or the one being edited)
    current_placeholder = None
    if target_field_from_message:
        # Find the placeholder matching the target field name
        for p in placeholders:
            p_name_display = p.name.replace("_", " ").title().lower()
            target_name_lower = target_field_from_message.lower()
            
            if (p_name_display == target_name_lower or 
                p.name.lower() == target_name_lower or
                p.name.lower().replace("_", " ") == target_name_lower or
                target_name_lower in p_name_display or
                p_name_display in target_name_lower):
                current_placeholder = p
                break
    
    # If no target found or not editing, find next unanswered
    if not current_placeholder:
        for p in placeholders:
            if p.id not in answered_ids:
                current_placeholder = p
                break
    
    # Safety check: If current_placeholder already has an answer and we're not editing it, find next unanswered
    if current_placeholder and current_placeholder.id in answered_ids and not target_field_from_message:
        # This shouldn't happen, but if it does, skip to next unanswered
        for p in placeholders:
            if p.id not in answered_ids:
                current_placeholder = p
                break

    # If all fields are filled AND user is not trying to edit, then complete
    if not current_placeholder and not target_field_from_message:
        # Re-check if user wants to edit - maybe they mentioned a field name
        field_names_in_message = []
        for p in placeholders:
            p_name_variants = [
                p.name.lower(),
                p.name.replace("_", " ").lower(),
                p.name.replace("_", " ").title().lower(),
            ]
            for variant in p_name_variants:
                if variant in message_lower and len(variant) > 3:  # Avoid false matches on short words
                    field_names_in_message.append(p)
                    break
        
        if field_names_in_message:
            # User mentioned a field name, allow editing
            current_placeholder = field_names_in_message[0]
        else:
            # Truly all done
            if s.state != "completed":
                s.state = "completed"
                session.add(s)
            return ChatResponse(
                assistant="Excellent! All placeholders have been filled. You can now render and download the completed document. If you'd like to edit any field, just say 'change [field name]'.",
                progress={"filled": len(placeholders), "total": len(placeholders)},
            )

    # Update session state if needed (allow editing even if completed)
    if s.state == "pending":
        s.state = "in_progress"
        session.add(s)
    elif s.state == "completed" and current_placeholder:
        # If user is editing, switch back to in_progress
        s.state = "in_progress"
        session.add(s)

    # Check if there's an existing answer for current placeholder
    existing_answer = answered_map.get(current_placeholder.id)
    
    # If field already has an answer and user didn't explicitly ask to edit it, 
    # ask for confirmation to reuse or change
    if existing_answer and not (target_field_from_message or is_potential_edit):
        # Check if user's message is explicitly providing a new value or asking to change
        message_lower = req.message.lower()
        is_explicit_edit = any(phrase in message_lower for phrase in [
            "change", "edit", "update", "fix", "modify", "different", "new value", "instead"
        ])
        
        # Check if user confirms they want to keep existing value
        keep_confirmations = ["yes", "keep", "ok", "okay", "sure", "correct", "that's fine", "that's good", "that works"]
        wants_to_keep = any(confirm in message_lower for confirm in keep_confirmations)
        
        if wants_to_keep:
            # User wants to keep existing value, move to next field
            # Ensure answer is in database (it should already be, but double-check)
            if current_placeholder.id not in answered_ids:
                # Create answer if it doesn't exist
                keep_answer = Answer(
                    session_id=session_id,
                    placeholder_id=current_placeholder.id,
                    value=existing_answer.value,
                    source="user",
                )
                session.add(keep_answer)
            
            answered_ids.add(current_placeholder.id)
            session.commit()
            
            # Find next unanswered placeholder
            next_placeholder = None
            for p in placeholders:
                if p.id not in answered_ids:
                    next_placeholder = p
                    break
            
            if next_placeholder:
                from app.services.conversation import get_field_examples
                examples = get_field_examples(next_placeholder.type, next_placeholder.name)
                examples_text = f" For example: {examples}." if examples else ""
                field_name_display = next_placeholder.name.replace("_", " ").title()
                return ChatResponse(
                    assistant=f"Perfect! I'll keep '{existing_answer.value}' for {current_placeholder.name.replace('_', ' ').title()}. Now, what about {field_name_display}?{examples_text}",
                    progress={"filled": len(answered_ids), "total": len(placeholders)},
                )
            else:
                # All done
                return ChatResponse(
                    assistant=f"Perfect! I'll keep '{existing_answer.value}'. All placeholders have been filled. You can now render and download the completed document.",
                    progress={"filled": len(answered_ids), "total": len(placeholders)},
                )
        
        # If not explicitly editing and not confirming, ask if they want to reuse the existing value
        if not is_explicit_edit and len(existing_answer.value or "") > 0:
            from app.services.conversation import get_field_examples
            examples = get_field_examples(current_placeholder.type, current_placeholder.name)
            examples_text = f" For example: {examples}." if examples else ""
            field_name_display = current_placeholder.name.replace("_", " ").title()
            
            return ChatResponse(
                assistant=f"I already have '{existing_answer.value}' for {field_name_display}. Would you like to keep this value, or change it?{examples_text}",
                progress={"filled": len(answered_ids), "total": len(placeholders)},
            )

    # Find next placeholder for smooth transitions
    next_placeholder = None
    for p in placeholders:
        if p.id not in answered_ids and p.id != current_placeholder.id:
            next_placeholder = p
            break

    # Build conversation history from recent messages (stored in session metadata or from answers)
    # For now, we'll create a simple history from the current interaction
    # In production, you might store full chat history in a separate table
    conversation_history = []
    
    # Check if this is an initial greeting
    is_greeting = req.message.lower().strip() in ["hello", "hi", "hey", "start", "begin"]
    
    if existing_answer:
        # If there's an existing answer, add context about it
        conversation_history.append({
            "role": "assistant",
            "content": f"I currently have '{existing_answer.value}' for {current_placeholder.name}. Would you like to change it?"
        })
    
    # Add current user message to history
    conversation_history.append({
        "role": "user",
        "content": req.message
    })
    
    # For greetings, we want to generate a friendly initial question with examples
    if is_greeting and not existing_answer:
        # Use a greeting-friendly user message that will trigger a helpful response
        effective_message = f"Hello! I'm ready to help you fill out this document. Let's start with {current_placeholder.name.replace('_', ' ')}."
    else:
        effective_message = req.message

    # Generate chat message using agentic LLM analysis
    assistant_msg, answer_accepted, extracted_value, target_field_name = generate_chat_message(
        current_placeholder,
        effective_message,
        prev_answers,
        existing_answer,
        conversation_history,
        next_placeholder,
    )
    
    # For greetings, ensure the response includes examples
    if is_greeting and not existing_answer:
        from app.services.conversation import get_field_examples
        examples = get_field_examples(current_placeholder.type, current_placeholder.name)
        if examples and examples.lower() not in assistant_msg.lower():
            # Add examples if they're missing
            field_name_display = current_placeholder.name.replace("_", " ").title()
            assistant_msg = f"Hello! I'll help you fill out this document. Let's start with {field_name_display}. For example: {examples}. What would you like to use?"

    # Check if user wants to edit a different field (from LLM analysis or from message check)
    target_field_name = target_field_name or target_field_from_message
    
    if target_field_name:
        # Find the placeholder matching the target field name
        target_placeholder = None
        for p in placeholders:
            # Match by name (various formats)
            p_name_display = p.name.replace("_", " ").title().lower()
            target_name_lower = target_field_name.lower()
            
            if (p_name_display == target_name_lower or 
                p.name.lower() == target_name_lower or
                p.name.lower().replace("_", " ") == target_name_lower or
                target_name_lower in p_name_display or
                p_name_display in target_name_lower):
                target_placeholder = p
                break
        
        if target_placeholder:
            # Switch to editing this field
            current_placeholder = target_placeholder
            existing_answer = answered_map.get(target_placeholder.id)
            
            # If user provided a value, save it
            if answer_accepted and extracted_value:
                if existing_answer:
                    existing_answer.value = extracted_value
                    existing_answer.source = "user"
                    session.add(existing_answer)
                else:
                    new_answer = Answer(
                        session_id=session_id,
                        placeholder_id=target_placeholder.id,
                        value=extracted_value,
                        source="user",
                    )
                    session.add(new_answer)
                    answered_ids.add(target_placeholder.id)
                
                # Commit to save the answer
                session.commit()
                
                # Update progress calculation
                filled = len(answered_ids)
                total = len(placeholders)
                
                return ChatResponse(
                    assistant=assistant_msg,
                    progress={"filled": filled, "total": total},
                )
            else:
                # User wants to edit but hasn't provided new value yet
                # Use the assistant message generated (should already ask for new value)
                # If it doesn't, we'll add context
                if "what" not in assistant_msg.lower() and "value" not in assistant_msg.lower():
                    # Generate a simple prompt asking for the new value
                    from app.services.conversation import get_field_examples
                    examples = get_field_examples(target_placeholder.type, target_placeholder.name)
                    examples_text = f" For example: {examples}." if examples else ""
                    current_value = existing_answer.value if existing_answer else "nothing"
                    assistant_msg = f"I see you want to edit {target_field_name} (currently: '{current_value}'). What should the new value be?{examples_text}"
                else:
                    # The assistant message already asks for the value, just add context
                    assistant_msg = f"I see you want to edit {target_field_name}. " + assistant_msg
                
                # Commit session
                session.commit()
                
                # Update progress
                filled = len(answered_ids)
                total = len(placeholders)
                
                return ChatResponse(
                    assistant=assistant_msg,
                    progress={"filled": filled, "total": total},
                )
    
    # If answer is accepted for current field, save the extracted/normalized value
    elif answer_accepted and extracted_value:
        # Use the LLM-extracted value (cleaned and normalized) instead of raw message
        value = extracted_value
        
        # Update or create answer
        if existing_answer:
            existing_answer.value = value
            existing_answer.source = "user"
            session.add(existing_answer)
        else:
            new_answer = Answer(
                session_id=session_id,
                placeholder_id=current_placeholder.id,
                value=value,
                source="user",
            )
            session.add(new_answer)
        
        # Commit to save the answer immediately
        session.commit()
        
        # Update answered_ids to reflect the saved answer
        answered_ids.add(current_placeholder.id)
        
        # Find the next unanswered placeholder
        next_unanswered = None
        for p in placeholders:
            if p.id not in answered_ids:
                next_unanswered = p
                break
        
        # If assistant message doesn't already mention moving to next field, update it
        if next_unanswered and not any(word in assistant_msg.lower() for word in ["next", "now", next_unanswered.name.lower()]):
            from app.services.conversation import get_field_examples
            examples = get_field_examples(next_unanswered.type, next_unanswered.name)
            examples_text = f" For example: {examples}." if examples else ""
            field_name_display = next_unanswered.name.replace("_", " ").title()
            
            # Only add transition if the assistant message is short or doesn't already have transition
            if len(assistant_msg) < 100 or "next" not in assistant_msg.lower():
                assistant_msg = f"Perfect! I've saved '{value}' for {current_placeholder.name.replace('_', ' ').title()}. Now, what about {field_name_display}?{examples_text}"

    # Calculate progress
    filled = len(answered_ids)
    total = len(placeholders)

    return ChatResponse(
        assistant=assistant_msg,
        progress={"filled": filled, "total": total},
    )

