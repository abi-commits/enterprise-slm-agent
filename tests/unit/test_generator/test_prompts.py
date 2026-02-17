"""Tests for Generator Service prompts."""

import pytest

from services.inference.generator.prompts import (
    GENERATOR_SYSTEM_PROMPT as SYSTEM_PROMPT,
    CONTEXT_FORMAT_PROMPT,
    GENERATOR_FEW_SHOT_EXAMPLES as FEW_SHOT_EXAMPLES,
    TEMPLATE_PROMPT,
    format_context_documents,
    build_generation_prompt,
    build_template_prompt,
    extract_answer_from_response,
)


class TestSystemPrompt:
    """Test cases for system prompt."""

    def test_system_prompt_not_empty(self):
        """Test that system prompt is not empty."""
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_user_role_placeholder(self):
        """Test that system prompt contains user role placeholder."""
        assert "{user_role}" in SYSTEM_PROMPT


class TestContextFormatPrompt:
    """Test cases for context format prompt."""

    def test_context_format_prompt_not_empty(self):
        """Test that context format prompt is not empty."""
        assert len(CONTEXT_FORMAT_PROMPT) > 0

    def test_context_format_prompt_placeholders(self):
        """Test that context format prompt contains required placeholders."""
        assert "{context}" in CONTEXT_FORMAT_PROMPT
        assert "{question}" in CONTEXT_FORMAT_PROMPT


class TestFewShotExamples:
    """Test cases for few-shot examples."""

    def test_few_shot_examples_not_empty(self):
        """Test that few-shot examples is not empty."""
        assert len(FEW_SHOT_EXAMPLES) > 0


class TestTemplatePrompt:
    """Test cases for template prompt."""

    def test_template_prompt_not_empty(self):
        """Test that template prompt is not empty."""
        assert len(TEMPLATE_PROMPT) > 0

    def test_template_prompt_placeholders(self):
        """Test that template prompt contains required placeholders."""
        assert "{context}" in TEMPLATE_PROMPT
        assert "{question}" in TEMPLATE_PROMPT


class TestFormatContextDocuments:
    """Test cases for format_context_documents function."""

    def test_format_context_documents_empty(self):
        """Test formatting empty document list."""
        result = format_context_documents([])
        
        assert "No relevant documents found" in result

    def test_format_context_documents_single(self):
        """Test formatting single document."""
        documents = [
            {
                "content": "The vacation policy allows 15 days.",
                "source": "HR Handbook",
                "score": 0.95,
            }
        ]
        
        result = format_context_documents(documents)
        
        assert "Document 1" in result
        assert "HR Handbook" in result
        assert "The vacation policy allows 15 days" in result

    def test_format_context_documents_multiple(self):
        """Test formatting multiple documents."""
        documents = [
            {
                "content": "The vacation policy allows 15 days.",
                "source": "HR Handbook",
                "score": 0.95,
            },
            {
                "content": "PTO accrual happens monthly.",
                "source": "Employee Guide",
                "score": 0.85,
            },
        ]
        
        result = format_context_documents(documents)
        
        assert "Document 1" in result
        assert "Document 2" in result

    def test_format_context_documents_without_score(self):
        """Test formatting documents without score."""
        documents = [
            {
                "content": "Content here",
                "source": "Source",
            }
        ]
        
        result = format_context_documents(documents)
        
        assert "relevance:" not in result

    def test_format_context_documents_without_source(self):
        """Test formatting documents without source."""
        documents = [
            {
                "content": "Content here",
            }
        ]
        
        result = format_context_documents(documents)
        
        assert "Unknown source" in result


class TestBuildGenerationPrompt:
    """Test cases for build_generation_prompt function."""

    def test_build_generation_prompt_basic(self):
        """Test basic prompt building."""
        question = "What is the vacation policy?"
        documents = [
            {
                "content": "The vacation policy allows 15 days.",
                "source": "HR Handbook",
                "score": 0.95,
            }
        ]
        
        result = build_generation_prompt(
            question=question,
            documents=documents,
            user_role="HR",
        )
        
        assert question in result
        assert "HR Handbook" in result
        assert "HR" in result  # user_role should be substituted

    def test_build_generation_prompt_with_few_shot(self):
        """Test prompt building with few-shot examples."""
        question = "What is the vacation policy?"
        documents = [
            {
                "content": "The vacation policy allows 15 days.",
                "source": "HR Handbook",
                "score": 0.95,
            }
        ]
        
        result = build_generation_prompt(
            question=question,
            documents=documents,
            user_role="HR",
            include_few_shot=True,
        )
        
        assert "Example 1" in result
        assert "Example 2" in result


class TestBuildTemplatePrompt:
    """Test cases for build_template_prompt function."""

    def test_build_template_prompt(self):
        """Test template prompt building."""
        question = "What is the vacation policy?"
        documents = [
            {
                "content": "The vacation policy allows 15 days.",
                "source": "HR Handbook",
                "score": 0.95,
            }
        ]
        
        result = build_template_prompt(
            question=question,
            documents=documents,
        )
        
        assert question in result
        assert "HR Handbook" in result
        assert "Answer:" in result


class TestExtractAnswerFromResponse:
    """Test cases for extract_answer_from_response function."""

    def test_extract_answer_strips_whitespace(self):
        """Test that answer extraction strips whitespace."""
        response = "  Some answer  "
        
        result = extract_answer_from_response(response)
        
        assert result == "Some answer"

    def test_extract_answer_removes_prefix_answer(self):
        """Test removing 'Answer:' prefix."""
        response = "Answer: The vacation policy allows 15 days."
        
        result = extract_answer_from_response(response)
        
        assert result == "The vacation policy allows 15 days."

    def test_extract_answer_removes_prefix_the_answer_is(self):
        """Test removing 'The answer is:' prefix."""
        response = "The answer is: 15 days."
        
        result = extract_answer_from_response(response)
        
        assert result == "15 days."

    def test_extract_answer_removes_prefix_based_on_context(self):
        """Test removing 'Based on the context:' prefix."""
        response = "Based on the context: The policy allows 15 days."
        
        result = extract_answer_from_response(response)
        
        assert result == "The policy allows 15 days."

    def test_extract_answer_removes_prefix_heres_answer(self):
        """Test removing 'Here's the answer:' prefix."""
        response = "Here's the answer: The vacation policy allows 15 days."
        
        result = extract_answer_from_response(response)
        
        assert result == "The vacation policy allows 15 days."

    def test_extract_answer_case_insensitive(self):
        """Test that prefix removal is case insensitive."""
        response = "ANSWER: Some answer"
        
        result = extract_answer_from_response(response)
        
        assert result == "Some answer"

    def test_extract_answer_no_prefix(self):
        """Test that answer without prefix stays unchanged."""
        response = "The vacation policy allows 15 days per year."
        
        result = extract_answer_from_response(response)
        
        assert result == "The vacation policy allows 15 days per year."
