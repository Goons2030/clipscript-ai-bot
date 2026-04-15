"""Shared HTTP client for inter-service communication"""
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ServiceClient:
    """Client for calling other services"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def post(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict]:
        """POST request to service"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Service request failed: {e}")
            return None
    
    def get(self, endpoint: str) -> Optional[Dict]:
        """GET request to service"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Service request failed: {e}")
            return None
