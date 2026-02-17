"""Prompt templates for the Query Optimizer."""


QUERY_OPTIMIZER_SYSTEM_PROMPT = """You are a query optimization expert for an enterprise knowledge base. Your task is to:
1. Expand and enrich user queries for better document retrieval
2. Extract key keywords from queries
3. Rephrase queries in multiple ways to improve search results
4. Score the confidence of the query (how likely it is to find relevant documents)

You must respond with valid JSON only, no additional text."""

QUERY_OPTIMIZER_USER_PROMPT_TEMPLATE = """Given the following user query: "{query}"

{user_context}

Generate:
1. Three optimized versions of the query that would improve document retrieval
2. A list of 5-10 key keywords for the query
3. A confidence score (0.0 to 1.0) indicating how clear and searchable this query is

Respond with JSON in this exact format:
{{
    "optimized_queries": ["query 1", "query 2", "query 3"],
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "confidence": 0.85,
    "reasoning": "Brief explanation of the optimization choices"
}}

Guidelines:
- Optimized queries should be more specific and include relevant domain terms
- Keywords should include both singular and plural forms where relevant
- Confidence is lower for vague queries (e.g., "help me", "information") and higher for specific queries
- Consider the user's role/department when optimizing the query"""

FEW_SHOT_EXAMPLES = """
Example 1:
Input: "What is the vacation policy?"
Output: {{
    "optimized_queries": [
        "company vacation policy guidelines 2024",
        "employee paid time off PTO policy",
        "vacation leave entitlements and accrual rules"
    ],
    "keywords": ["vacation", "PTO", "paid time off", "leave", "policy", "employee benefits", "holiday", "accrual"],
    "confidence": 0.8,
    "reasoning": "Query is clear but could benefit from more specific terms like 'policy 2024' and 'employee benefits'"
}}

Example 2:
Input: "HR stuff"
Output: {{
    "optimized_queries": [
        "human resources policies and procedures",
        "HR department guidelines and forms",
        "employee handbook human resources"
    ],
    "keywords": ["HR", "human resources", "policies", "procedures", "employee", "handbook", "guidelines"],
    "confidence": 0.4,
    "reasoning": "Query is very vague. Expanded to include common HR-related terms"
}}

Example 3:
Input: "How do I request reimbursement for travel expenses?"
Output: {{
    "optimized_queries": [
        "travel expense reimbursement request process",
        "business travel expense policy and claims procedure",
        "expense reimbursement form submission guidelines"
    ],
    "keywords": ["travel", "expense", "reimbursement", "claim", "business", "policy", "procedure", "form", "submit"],
    "confidence": 0.9,
    "reasoning": "Query is already specific, just expanded with synonyms and related terms"
}}
"""


def build_optimization_prompt(query: str, user_context: str = "") -> str:
    """Build the full prompt for query optimization."""
    context_section = ""
    if user_context:
        context_section = f"\nUser context: {user_context}\n"

    return (
        f"{QUERY_OPTIMIZER_SYSTEM_PROMPT}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"{QUERY_OPTIMIZER_USER_PROMPT_TEMPLATE.format(query=query, user_context=context_section)}"
    )


# Keywords extraction prompt (simpler, for fallback)
KEYWORD_EXTRACTION_PROMPT = """Extract the most important keywords from this query. Return as a JSON list of strings.

Query: "{query}"

Output format: {{"keywords": ["keyword1", "keyword2", "keyword3"]}}
"""
