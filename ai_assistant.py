"""
AI-powered assistant for understanding user requests and suggesting services
Refactored to use new config and models
"""
import json
import logging
import requests
from typing import Dict

from config import get_config
from models import Language, Intent, AIResponse
from services_manager import get_services, get_service_info

logger = logging.getLogger(__name__)


def parse_user_request(
    user_query: str,
    max_suggestions: int = 5,
    user_language: Language = Language.DE
) -> AIResponse:
    """
    Parse user request and suggest relevant services using AI

    Args:
        user_query: The user's query text
        max_suggestions: Maximum number of service suggestions
        user_language: User's preferred language

    Returns:
        AIResponse with intent, suggested services, explanation, and answer
    """
    config = get_config()

    if not config.has_openai:
        logger.warning("OPENAI_API_KEY not set, using keyword matching fallback")
        return _fallback_keyword_matching(user_query, max_suggestions)

    # Get all available services
    services = get_services()

    # Build service catalog for AI context
    service_catalog = [
        {
            'id': s['id'],
            'name': s['name'],
            'maxQuantity': s.get('maxQuantity', 1)
        }
        for s in services
    ]

    # Language mapping for responses
    lang_names = {
        Language.DE: 'German',
        Language.EN: 'English',
        Language.RU: 'Russian'
    }
    response_lang = lang_names.get(user_language, 'German')

    system_prompt = f"""You are an AI assistant for Munich appointment booking system.
Your task is to understand user requests and suggest relevant services.

Available services:
{json.dumps(service_catalog, ensure_ascii=False)}

Analyze the user's request and respond in JSON format:
{{
    "intent": "service_search" or "information_request",
    "suggested_service_ids": [list of service IDs, max {max_suggestions}],
    "explanation": "Why these services were suggested",
    "answer": "Direct answer if information request"
}}

IMPORTANT - Matching Rules:
1. Search for PARTIAL WORDS in service names (case-insensitive)
   Example: "notfall" MUST find "Notfall-Hilfe Aufenthaltstitel"
2. Search in compound words with hyphens
3. A service matches if ANY word from the query appears in the service name
4. ALWAYS return matching service IDs when you find matches

Intent classification:
- If user asks for information (opening hours, documents, process): set intent to "information_request"
- If user wants to book an appointment: set intent to "service_search" and suggest matching services

CRITICAL: Respond with "explanation" and "answer" fields in {response_lang}.
"""

    try:
        headers = {
            'Authorization': f'Bearer {config.openai_api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': config.openai_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_query}
            ],
            'max_completion_tokens': 2000
        }

        # Only add response_format for models that support it
        if not config.openai_model.startswith('gpt-5'):
            payload['response_format'] = {'type': 'json_object'}

        logger.info(f"Sending AI request for query: {user_query[:50]}...")
        logger.debug(f"OpenAI request payload: {json.dumps(payload, ensure_ascii=False)}")

        response = requests.post(config.openai_api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()

        # Log the full API response structure for debugging
        logger.debug(f"Full API response: {json.dumps(result, ensure_ascii=False)[:500]}")

        choice = result['choices'][0]
        message = choice['message']
        finish_reason = choice.get('finish_reason', 'unknown')

        logger.info(f"Finish reason: {finish_reason}")

        # Check for refusal
        if 'refusal' in message and message['refusal']:
            logger.error(f"Model refused to respond: {message['refusal']}")
            return _fallback_keyword_matching(user_query, max_suggestions)

        content = message.get('content', '')

        if content is None or content == '':
            logger.warning(f"Model returned empty content. Message fields: {list(message.keys())}")
            logger.warning(f"Refusal: {message.get('refusal')}")
            logger.warning(f"Annotations: {message.get('annotations')}")
            logger.warning(f"Role: {message.get('role')}")
            # Try to get any other content field
            if 'text' in message:
                content = message['text']
            else:
                content = ""

        logger.info(f"AI raw response (length={len(content)}): {content[:200] if content else '(empty)'}")

        # Try to parse as JSON
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # If not JSON, try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                # Fallback: assume it's an information response
                logger.warning("Could not parse JSON, treating as information response")
                return AIResponse(
                    intent=Intent.INFORMATION_REQUEST,
                    suggested_services=[],
                    explanation="",
                    answer=content
                )

        logger.info(f"AI parsed intent: {parsed.get('intent')}, suggested {len(parsed.get('suggested_service_ids', []))} services")

        # Convert to typed response
        intent_str = parsed.get('intent', 'service_search')
        intent = Intent.INFORMATION_REQUEST if intent_str == 'information_request' else Intent.SERVICE_SEARCH

        return AIResponse(
            intent=intent,
            suggested_services=parsed.get('suggested_service_ids', [])[:max_suggestions],
            explanation=parsed.get('explanation', ''),
            answer=parsed.get('answer', '')
        )

    except requests.exceptions.HTTPError as e:
        logger.error(f"AI request failed: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        return _fallback_keyword_matching(user_query, max_suggestions)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Raw content was: {content if 'content' in locals() else 'not available'}")
        return _fallback_keyword_matching(user_query, max_suggestions)
    except Exception as e:
        logger.error(f"AI request failed: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        if 'result' in locals():
            logger.error(f"Full API response: {json.dumps(result, ensure_ascii=False)}")
        return _fallback_keyword_matching(user_query, max_suggestions)


def _fallback_keyword_matching(user_query: str, max_suggestions: int = 5) -> AIResponse:
    """Fallback keyword-based matching when AI is unavailable"""
    query_lower = user_query.lower()
    services = get_services()

    # Keyword to service mapping
    keywords = {
        'aufenthalt': ['Aufenthaltstitel', 'Duldung', 'eAT', 'Notfall'],
        'residence': ['Aufenthaltstitel', 'Duldung', 'eAT', 'Notfall'],
        'permit': ['Aufenthaltstitel', 'eAT', 'Notfall'],
        'fiktion': ['Aufenthaltstitel', 'Notfall'],
        'fiktionsbescheinigung': ['Aufenthaltstitel', 'Notfall'],
        'pass': ['Pass', 'Reisepass'],
        'passport': ['Pass', 'Reisepass'],
        'ausweis': ['Personalausweis', 'eID'],
        'id': ['Personalausweis', 'eID'],
        'fahrzeug': ['Fahrzeug', 'Kfz', 'Zulassung'],
        'auto': ['Fahrzeug', 'Kfz', 'Zulassung'],
        'car': ['Fahrzeug', 'Kfz', 'Zulassung'],
        'vehicle': ['Fahrzeug', 'Kfz', 'Zulassung'],
        'führerschein': ['Führerschein'],
        'license': ['Führerschein'],
        'wohnung': ['Wohnsitz', 'Melde'],
        'umzug': ['Wohnsitz', 'Melde', 'Ummeldung'],
        'registration': ['Wohnsitz', 'Melde'],
        'address': ['Wohnsitz', 'Melde', 'Adress'],
        'gewerbe': ['Gewerbe'],
        'firma': ['Gewerbe'],
        'business': ['Gewerbe'],
        'heirat': ['Eheschließung'],
        'hochzeit': ['Eheschließung'],
        'marriage': ['Eheschließung'],
        'kind': ['Kind', 'Familie', 'Unterhaltsvorschuss'],
        'child': ['Kind', 'Familie'],
        'rente': ['Rente'],
        'pension': ['Rente'],
        'parken': ['Park'],
        'parking': ['Park'],
        'notfall': ['Notfall'],
        'emergency': ['Notfall'],
        'schnell': ['Notfall'],
        'urgent': ['Notfall'],
        'dringend': ['Notfall']
    }

    # Score each service
    scored_services = []
    for service in services:
        score = 0
        service_name_lower = service['name'].lower()

        # Check if query words appear in service name (direct match is very strong)
        for word in query_lower.split():
            if len(word) > 2:
                if word in service_name_lower:
                    score += 30

        # Check keyword matches
        for keyword, patterns in keywords.items():
            if keyword in query_lower:
                for pattern in patterns:
                    if pattern.lower() in service_name_lower:
                        score += 20

        if score > 0:
            scored_services.append((service['id'], score))

    # Sort by score and take top suggestions
    scored_services.sort(key=lambda x: x[1], reverse=True)
    suggested_ids = [sid for sid, _ in scored_services[:max_suggestions]]

    explanation = "Based on keywords in your query, these services were found." if suggested_ids else ""

    return AIResponse(
        intent=Intent.SERVICE_SEARCH,
        suggested_services=suggested_ids,
        explanation=explanation,
        answer=''
    )


def get_official_information(query: str, user_language: Language = Language.DE) -> str | None:
    """
    Fetch official information from Munich website using AI to extract relevant content

    Args:
        query: User's information query
        user_language: User's preferred language

    Returns:
        Answer string or None if unavailable
    """
    config = get_config()

    if not config.has_openai:
        return None

    # Language mapping
    lang_names = {
        Language.DE: 'German',
        Language.EN: 'English',
        Language.RU: 'Russian'
    }
    response_lang = lang_names.get(user_language, 'German')

    system_prompt = f"""You are a helpful information assistant for Munich citizen services.

Answer questions about:
- Appointment scheduling and booking process
- Required documents for various services
- Opening hours of offices
- Administrative procedures and workflows
- Office locations and contact information
- General guidance for common services (residence permits, vehicle registration, etc.)

INSTRUCTIONS:
1. Be helpful and provide useful guidance based on general knowledge of German administrative processes
2. For Munich-specific details (exact addresses, current hours), recommend calling 115 or visiting stadt.muenchen.de
3. Don't refuse to help - provide general guidance even if you don't have exact Munich-specific details
4. Be concise and practical

CRITICAL: Respond in {response_lang}."""

    try:
        headers = {
            'Authorization': f'Bearer {config.openai_api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': config.openai_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': query}
            ],
            'max_completion_tokens': 2000
        }

        logger.info(f"Fetching official info for: {query[:50]}...")
        logger.debug(f"OpenAI request payload: {json.dumps(payload, ensure_ascii=False)}")

        response = requests.post(config.openai_api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        answer = result['choices'][0]['message']['content']

        logger.info("Official information retrieved successfully")
        return answer

    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to get official information: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to get official information: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        return None


def enhance_service_info(service_id: int, user_language: Language = Language.DE) -> str | None:
    """
    Get enhanced information about a specific service using AI

    Args:
        service_id: Service ID to get info for
        user_language: User's preferred language

    Returns:
        Enhanced service description or None
    """
    service = get_service_info(service_id)
    if not service:
        return None

    config = get_config()

    if not config.has_openai:
        return None

    # Language mapping
    lang_names = {
        Language.DE: 'German',
        Language.EN: 'English',
        Language.RU: 'Russian'
    }
    response_lang = lang_names.get(user_language, 'German')

    system_prompt = f"""You are an assistant for Munich citizen services.
Briefly explain what this service is, who needs it, and what documents are typically required.
Keep the answer to 2-3 sentences.

CRITICAL: Respond in {response_lang}."""

    try:
        headers = {
            'Authorization': f'Bearer {config.openai_api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': config.openai_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Dienst: {service['name']}"}
            ],
            'max_completion_tokens': 800
        }

        logger.debug(f"OpenAI request payload: {json.dumps(payload, ensure_ascii=False)}")

        response = requests.post(config.openai_api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content']

    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to enhance service info: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to enhance service info: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        return None
