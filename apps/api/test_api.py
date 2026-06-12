"""
API Tests for Mantle DeFAI Trader
Run with: pytest test_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from main import app, cache

client = TestClient(app)

class TestHealthEndpoints:
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
    
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data

class TestSentimentEndpoints:
    def test_get_latest_sentiment(self):
        response = client.get("/api/sentiment/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
    
    def test_post_sentiment_analyze(self):
        response = client.post("/api/sentiment/analyze", json={
            "timeframe": "1h",
            "limit": 20,
            "force_refresh": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "sentiment_index" in data["data"]
        assert "bullish_count" in data["data"]
    
    def test_sentiment_invalid_timeframe(self):
        response = client.post("/api/sentiment/analyze", json={
            "timeframe": "invalid"
        })
        assert response.status_code == 422

class TestMantleEndpoints:
    def test_get_block(self):
        response = client.get("/api/mantle/block")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "number" in data["data"]
    
    def test_get_gas(self):
        response = client.get("/api/mantle/gas")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "gwei" in data["data"]
    
    def test_get_network(self):
        response = client.get("/api/mantle/network")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

class TestSwapEndpoints:
    def test_swap_quote(self):
        response = client.post("/api/swap/quote", json={
            "token_in": "MNT",
            "token_out": "USDC",
            "amount_in": "1000000000000000000",
            "slippage": 0.005
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "expected_output" in data["data"]
    
    def test_swap_quote_invalid_token(self):
        response = client.post("/api/swap/quote", json={
            "token_in": "INVALID",
            "token_out": "USDC",
            "amount_in": "1000"
        })
        assert response.status_code == 400

class TestCacheEndpoints:
    def test_cache_stats(self):
        response = client.get("/api/cache/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cache_entries" in data["data"]
    
    def test_cache_invalidate(self):
        response = client.post("/api/cache/invalidate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
