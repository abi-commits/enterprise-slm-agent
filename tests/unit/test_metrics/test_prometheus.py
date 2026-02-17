"""Tests for Prometheus metrics."""

import pytest
from unittest.mock import patch, MagicMock

from services.api import prometheus


class TestPrometheusMetrics:
    """Test cases for Prometheus metrics."""

    def test_total_requests_metric_exists(self):
        """Test that total_requests metric exists."""
        assert prometheus.total_requests is not None

    def test_llm_escalations_metric_exists(self):
        """Test that llm_escalations metric exists."""
        assert prometheus.llm_escalations is not None

    def test_auth_failures_metric_exists(self):
        """Test that auth_failures metric exists."""
        assert prometheus.auth_failures is not None

    def test_query_latency_seconds_metric_exists(self):
        """Test that query_latency_seconds metric exists."""
        assert prometheus.query_latency_seconds is not None

    def test_token_usage_metric_exists(self):
        """Test that token_usage metric exists."""
        assert prometheus.token_usage is not None

    def test_response_time_ms_metric_exists(self):
        """Test that response_time_ms metric exists."""
        assert prometheus.response_time_ms is not None

    def test_active_users_metric_exists(self):
        """Test that active_users metric exists."""
        assert prometheus.active_users is not None

    def test_cost_accumulated_metric_exists(self):
        """Test that cost_accumulated_usd metric exists."""
        assert prometheus.cost_accumulated_usd is not None

    def test_query_confidence_metric_exists(self):
        """Test that query_confidence metric exists."""
        assert prometheus.query_confidence is not None


class TestUpdateMetricsOnRequest:
    """Test cases for update_metrics_on_request function."""

    @patch.object(prometheus.total_requests, "labels")
    @patch.object(prometheus.response_time_ms, "observe")
    def test_update_metrics_on_request(self, mock_observe, mock_labels):
        """Test updating metrics on request."""
        mock_counter = MagicMock()
        mock_labels.return_value = mock_counter
        
        prometheus.update_metrics_on_request(
            user_id="user-123",
            branch_taken="direct",
            response_time_ms_val=250.0,
        )
        
        mock_counter.inc.assert_called_once()
        mock_observe.assert_called_once_with(0.25)


class TestUpdateLlamaEscalation:
    """Test cases for update_llm_escalation function."""

    @patch.object(prometheus.llm_escalations, "labels")
    def test_update_llm_escalation(self, mock_labels):
        """Test updating LLM escalation counter."""
        mock_counter = MagicMock()
        mock_labels.return_value = mock_counter
        
        prometheus.update_llm_escalation(
            user_id="user-123",
            reason="low_confidence",
        )
        
        mock_counter.inc.assert_called_once()


class TestUpdateTokenUsage:
    """Test cases for update_token_usage function."""

    @patch.object(prometheus.token_usage, "labels")
    def test_update_token_usage(self, mock_labels):
        """Test updating token usage histogram."""
        mock_histogram = MagicMock()
        mock_labels.return_value = mock_histogram
        
        prometheus.update_token_usage(
            model_type="slm",
            tokens=100,
        )
        
        mock_histogram.observe.assert_called_once_with(100)


class TestUpdateServiceLatency:
    """Test cases for update_service_latency function."""

    @patch.object(prometheus.query_latency_seconds, "labels")
    def test_update_service_latency(self, mock_labels):
        """Test updating service latency histogram."""
        mock_histogram = MagicMock()
        mock_labels.return_value = mock_histogram
        
        prometheus.update_service_latency(
            service="optimizer",
            latency_seconds=0.1,
        )
        
        mock_histogram.observe.assert_called_once_with(0.1)


class TestUpdateActiveUsers:
    """Test cases for update_active_users function."""

    @patch.object(prometheus.active_users, "set")
    def test_update_active_users(self, mock_set):
        """Test updating active users gauge."""
        prometheus.update_active_users(count=10)
        
        mock_set.assert_called_once_with(10)


class TestUpdateAccumulatedCost:
    """Test cases for update_accumulated_cost function."""

    @patch.object(prometheus.cost_accumulated_usd, "set")
    def test_update_accumulated_cost(self, mock_set):
        """Test updating accumulated cost gauge."""
        prometheus.update_accumulated_cost(cost_usd=1.50)
        
        mock_set.assert_called_once_with(1.50)


class TestUpdateQueryConfidence:
    """Test cases for update_query_confidence function."""

    @patch.object(prometheus.query_confidence, "labels")
    def test_update_query_confidence(self, mock_labels):
        """Test updating query confidence gauge."""
        mock_gauge = MagicMock()
        mock_labels.return_value = mock_gauge
        
        prometheus.update_query_confidence(
            user_id="user-123",
            confidence=0.85,
        )
        
        mock_gauge.set.assert_called_once_with(0.85)


class TestUpdateEscalationRate:
    """Test cases for update_escalation_rate function."""

    @patch.object(prometheus.escalation_rate, "set")
    def test_update_escalation_rate(self, mock_set):
        """Test updating escalation rate gauge."""
        prometheus.update_escalation_rate(rate=15.5)
        
        mock_set.assert_called_once_with(15.5)


class TestUpdateAvgServiceLatency:
    """Test cases for update_avg_service_latency function."""

    @patch.object(prometheus.avg_latency_per_service, "labels")
    def test_update_avg_service_latency(self, mock_labels):
        """Test updating average service latency gauge."""
        mock_gauge = MagicMock()
        mock_labels.return_value = mock_gauge
        
        prometheus.update_avg_service_latency(
            service="search",
            latency_seconds=0.05,
        )
        
        mock_gauge.set.assert_called_once_with(0.05)


class TestUpdateTokensUsedToday:
    """Test cases for update_tokens_used_today function."""

    @patch.object(prometheus.tokens_used_today, "labels")
    def test_update_tokens_used_today(self, mock_labels):
        """Test updating tokens used today gauge."""
        mock_gauge = MagicMock()
        mock_labels.return_value = mock_gauge
        
        prometheus.update_tokens_used_today(
            model_type="slm",
            tokens=5000,
        )
        
        mock_gauge.set.assert_called_once_with(5000)


class TestUpdateCostSaved:
    """Test cases for update_cost_saved function."""

    @patch.object(prometheus.cost_saved_vs_llm_only, "set")
    def test_update_cost_saved(self, mock_set):
        """Test updating cost saved gauge."""
        prometheus.update_cost_saved(cost_saved_usd=0.50)
        
        mock_set.assert_called_once_with(0.50)


class TestRecordAuthFailure:
    """Test cases for record_auth_failure function."""

    @patch.object(prometheus.auth_failures, "labels")
    def test_record_auth_failure(self, mock_labels):
        """Test recording authentication failure."""
        mock_counter = MagicMock()
        mock_labels.return_value = mock_counter
        
        prometheus.record_auth_failure(reason="invalid_credentials")
        
        mock_counter.inc.assert_called_once()
