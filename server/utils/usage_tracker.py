"""
Usage tracking for billing and analytics.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class UsageTracker:
    """Track API usage per tenant for billing and analytics."""
    
    def __init__(self, usage_file: str = None):
        if usage_file is None:
            # Default path relative to this file
            base_dir = Path(__file__).parent.parent
            usage_file = base_dir / "data" / "usage.json"
        
        self.usage_file = Path(usage_file)
        self.usage: Dict[str, dict] = {}
        self._load_usage()
    
    def _load_usage(self):
        """Load usage data from JSON file"""
        try:
            if self.usage_file.exists():
                with open(self.usage_file, "r", encoding="utf-8") as file_handle:
                    self.usage = json.load(file_handle)
            else:
                self.usage_file.parent.mkdir(parents=True, exist_ok=True)
                self._save_usage()
        except Exception as exc:
            logger.exception("Failed to load usage data from %s", self.usage_file)
            self.usage = {}
    
    def _save_usage(self):
        """Save usage data to JSON file"""
        try:
            with open(self.usage_file, "w", encoding="utf-8") as file_handle:
                json.dump(self.usage, file_handle, indent=2)
        except Exception as exc:
            logger.exception("Failed to persist usage data to %s", self.usage_file)
            raise
    
    def _init_tenant_usage(self, tenant_id: str):
        """Initialize usage structure for new tenant"""
        if tenant_id not in self.usage:
            self.usage[tenant_id] = {
                "total_uploads": 0,
                "total_storage_mb": 0.0,
                "total_api_calls": 0,
                "total_reports_generated": 0,
                "last_activity": None,
                "monthly_usage": {},
                "endpoint_counters": {},
            }
    
    def track_upload(self, tenant_id: str, file_size_mb: float):
        """Track PDF upload"""
        self._init_tenant_usage(tenant_id)
        
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        # Update totals
        self.usage[tenant_id]["total_uploads"] += 1
        self.usage[tenant_id]["total_storage_mb"] += file_size_mb
        self.usage[tenant_id]["last_activity"] = datetime.utcnow().isoformat()
        
        # Update monthly usage
        if current_month not in self.usage[tenant_id]["monthly_usage"]:
            self.usage[tenant_id]["monthly_usage"][current_month] = {
                "uploads": 0,
                "storage_mb": 0.0,
                "api_calls": 0,
                "reports_generated": 0
            }
        
        self.usage[tenant_id]["monthly_usage"][current_month]["uploads"] += 1
        self.usage[tenant_id]["monthly_usage"][current_month]["storage_mb"] += file_size_mb
        
        self._save_usage()
    
    def track_api_call(self, tenant_id: str, endpoint: str = "general"):
        """Track general API call"""
        self._init_tenant_usage(tenant_id)
        
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        self.usage[tenant_id]["total_api_calls"] += 1
        self.usage[tenant_id]["last_activity"] = datetime.utcnow().isoformat()
        counters = self.usage[tenant_id]["endpoint_counters"]
        counters[endpoint] = counters.get(endpoint, 0) + 1
        
        # Update monthly
        if current_month not in self.usage[tenant_id]["monthly_usage"]:
            self.usage[tenant_id]["monthly_usage"][current_month] = {
                "uploads": 0,
                "storage_mb": 0.0,
                "api_calls": 0,
                "reports_generated": 0
            }
        
        self.usage[tenant_id]["monthly_usage"][current_month]["api_calls"] += 1
        
        self._save_usage()
    
    def track_report_generation(self, tenant_id: str):
        """Track report generation request"""
        self._init_tenant_usage(tenant_id)
        
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        self.usage[tenant_id]["total_reports_generated"] += 1
        
        if current_month in self.usage[tenant_id]["monthly_usage"]:
            self.usage[tenant_id]["monthly_usage"][current_month]["reports_generated"] += 1
        else:
            self.usage[tenant_id]["monthly_usage"][current_month] = {
                "uploads": 0,
                "storage_mb": 0.0,
                "api_calls": 0,
                "reports_generated": 1
            }
        
        self._save_usage()
    
    def get_usage(self, tenant_id: str) -> dict:
        """Get usage stats for tenant"""
        return self.usage.get(tenant_id, {
            "total_uploads": 0,
            "total_storage_mb": 0.0,
            "total_api_calls": 0,
            "total_reports_generated": 0,
            "last_activity": None,
            "monthly_usage": {},
            "endpoint_counters": {},
        })
    
    def get_monthly_usage(self, tenant_id: str, month: str = None) -> dict:
        """Get usage for specific month"""
        if month is None:
            month = datetime.utcnow().strftime("%Y-%m")
        
        usage = self.get_usage(tenant_id)
        return usage.get("monthly_usage", {}).get(month, {
            "uploads": 0,
            "storage_mb": 0.0,
            "api_calls": 0,
            "reports_generated": 0
        })


# Global singleton instance
usage_tracker = UsageTracker()
