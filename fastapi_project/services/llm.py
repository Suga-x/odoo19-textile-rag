import os
import time
import re
from litellm import completion
from dotenv import load_dotenv
import ollama

load_dotenv()

class LLMService:

    @staticmethod
    def _call_gemini_with_retry(model: str, messages: list, temperature: float = 0.2, timeout: int = 15, max_retries: int = 2) -> str:
        """
        Call Gemini via LiteLLM with automatic retry on rate-limit (429) errors.
        Respects the 'retry_delay' seconds from the API response.
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait = 2 ** attempt  # exponential backoff: 2s, 4s
                    print(f" [LLM RETRY] Attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s...")
                    time.sleep(wait)

                response = completion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=timeout
                )
                return response.choices[0].message.content

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                # Check if this is a rate-limit / quota error that might be retryable
                if any(kw in error_str for kw in ["quota", "rate_limit", "resource_exhausted", "429", "retry_delay"]):
                    # Try to extract retry_delay from the error message
                    retry_match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e), re.IGNORECASE)
                    if retry_match and attempt < max_retries:
                        delay = int(retry_match.group(1))
                        print(f" [LLM RATE LIMITED] Quota exceeded. Waiting {delay}s as suggested by API...")
                        time.sleep(delay)
                        continue
                    # If we see a retry_delay but no match, still try exponential backoff
                    if "retry_delay" in error_str and attempt < max_retries:
                        time.sleep(5)
                        continue
                # For non-retryable errors, break immediately
                print(f" [LLM GEMINI ERROR] {str(e)}")
                break

        # If all retries exhausted, re-raise the last exception
        raise last_exception

    @staticmethod
    def generate_rag_answer_history(question: str, retrieved_sop: str, history: list[dict[str, str]]) -> str:
        ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()

        # Build strict system instruction
        system_instruction = (
            "You are a Quality Management System Expert at a textile dyeing factory.\n"
            "Your task is to answer operator questions tactically, concisely, and in an easy-to-understand manner.\n\n"

            "OUTPUT FORMAT RULES (ABSOLUTE & STRICT):\n"
            "1. MUST use pure HTML format for all text decoration.\n"
            "2. Use <b>...</b> tags to bold titles, important points, temperature parameters, percentage values, or document codes.\n"
            "3. Use <ul> and <li> tags if the answer is a sequence of steps or a list of solutions.\n"
            "4. Use <br/><br/> tags to provide line breaks between paragraphs.\n"
            "5. STRICTLY FORBIDDEN to use Markdown like asterisks (**Explanation:** or **Bold Text**). Replace all bold markdown formatting with <b> tags.\n"
            "6. STRICTLY FORBIDDEN to wrap the answer in markdown code blocks like ```html ... ```.\n"
            "7. If the reference document contains an SOP number or specific instruction, mention it clearly.\n\n"

            "SOP REFERENCE DOCUMENT:\n"
            f"{retrieved_sop}"
        )
        messages_payload = [
            {'role': 'system', 'content': system_instruction}
        ]

        for msg in history[-4:]:
            role = "user" if msg["role"] == "Operator" else "assistant"
            messages_payload.append({'role': role, 'content': msg["content"]})

        messages_payload.append({'role': 'user', 'content': f"Operator Question: {question}"})
        try:
            if ai_provider == "gemini":
                print(" [LLM ROUTER] Attempting to contact Google Gemini API with history context...")
                return LLMService._call_gemini_with_retry(
                    model="gemini/gemini-2.0-flash",
                    messages=messages_payload
                )

        except Exception as e:
            print(f" [LLM FALLBACK] Gemini failed: {str(e)}. Redirecting to local Ollama...")

        # Fallback: Execute Local Ollama (Qwen) via native ollama library
        try:
            print("[LLM ROUTER] Running local Ollama (qwen2.5-coder:14b) with history context via ollama library...")
            # Build a simple prompt from messages
            system_content = messages_payload[0]["content"] if messages_payload else ""
            user_content = messages_payload[-1]["content"] if len(messages_payload) > 1 else question
            full_prompt = f"{system_content}\n\n{user_content}"
            response = ollama.generate(model="qwen2.5-coder:14b", prompt=full_prompt)
            return response["response"]

        except Exception as local_err:
            print(f" [LLM FATAL] Local Ollama also failed: {str(local_err)}")
            return (
                "<b>AI System Experiencing Disruption:</b> Connection to the AI brain (Gemini & Ollama) is lost. "
                "However, based on the database search, related SOP documents were found. Please contact the factory IT team."
            )

    @staticmethod
    def generate_rag_answer(question: str, retrieved_sop: str) -> str:
        ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()

        # Build strict system instruction
        system_instruction = (
            "You are a Quality Management System Expert at a textile dyeing factory.\n"
            "Your task is to answer operator questions tactically, concisely, and in an easy-to-understand manner.\n\n"

            "OUTPUT FORMAT RULES (ABSOLUTE & STRICT):\n"
            "1. MUST use pure HTML format for all text decoration.\n"
            "2. Use <b>...</b> tags to bold titles, important points, temperature parameters, percentage values, or document codes.\n"
            "3. Use <ul> and <li> tags if the answer is a sequence of steps or a list of solutions.\n"
            "4. Use <br/><br/> tags to provide line breaks between paragraphs.\n"
            "5. STRICTLY FORBIDDEN to use Markdown like asterisks (**Explanation:** or **Bold Text**). Replace all bold markdown formatting with <b> tags.\n"
            "6. STRICTLY FORBIDDEN to wrap the answer in markdown code blocks like ```html ... ```.\n"
            "7. If the reference document contains an SOP number or specific instruction, mention it clearly.\n\n"

            "CORRECT OUTPUT EXAMPLE:\n"
            "<b>Possible Cause:</b> Polyester fabric is wrinkled.<br/><br/>\n"
            "<b>Solution based on SOP-DYE-005:</b>\n"
            "<ul>\n"
            "  <li>Reduce temperature to <b>90°C</b> for 30 minutes.</li>\n"
            "</ul><br/>\n"
            "<b>Explanation:</b> This process aims to distribute color molecules evenly.\n\n"

            "SOP REFERENCE DOCUMENT:\n"
            f"{retrieved_sop}"
        )

        # Defense logic with try-except coupling
        try:
            if ai_provider == "gemini":
                print(" [LLM ROUTER] Attempting to contact Google Gemini API...")
                return LLMService._call_gemini_with_retry(
                    model="gemini/gemini-2.0-flash",
                    messages=[
                        {'role': 'system', 'content': system_instruction},
                        {'role': 'user', 'content': f"Operator Question: {question}"}
                    ]
                )

        except Exception as e:
            print(f" [LLM FALLBACK] Gemini failed: {str(e)}. Redirecting to local Ollama...")

        # Fallback: Execute Local Ollama (Qwen) via native ollama library
        try:
            print("[LLM ROUTER] Running local Ollama (qwen2.5-coder:14b) via ollama library...")
            full_prompt = f"{system_instruction}\n\nOperator Question: {question}"
            response = ollama.generate(model="qwen2.5-coder:14b", prompt=full_prompt)
            return response["response"]

        except Exception as local_err:
            print(f" [LLM FATAL] Local Ollama also failed: {str(local_err)}")
            return (
                "<b>AI System Experiencing Disruption:</b> Connection to the AI brain (Gemini & Ollama) is lost. "
                "However, based on the database search, related SOP documents were found. Please contact the factory IT team."
            )

    @staticmethod
    def generate_from_context_list(query: str, context_list: list[dict]) -> str:
        """
        Generate an answer from a list of retrieved document contexts.

        Args:
            query: The original user question.
            context_list: List of retrieved documents with 'text' and 'metadata' keys.

        Returns:
            A string containing the LLM-generated answer.
        """
        context_parts = []
        for i, doc in enumerate(context_list):
            sop_code = doc.get("metadata", {}).get("sop_code", "UNKNOWN")
            division = doc.get("metadata", {}).get("division", "UNKNOWN")
            text = doc.get("text", "")
            context_parts.append(
                f"[Document {i+1}] SOP Code: {sop_code} | Division: {division}\n{text}"
            )

        consolidated_context = "\n\n---\n\n".join(context_parts)

        return LLMService.generate_rag_answer(
            question=query,
            retrieved_sop=consolidated_context
        )
