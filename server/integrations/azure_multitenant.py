"""
Multi-tenant Azure Blob Storage wrapper
Provides tenant isolation for medical reports
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from fastapi import UploadFile

from server.core.tenant_context import get_current_tenant

logger = logging.getLogger(__name__)


class MultiTenantAzureBlobClient:
    """Azure Blob Storage client with multi-tenant support"""
    
    def __init__(self, connection_string: str, container_name: str):
        """
        Initialize Azure Blob Storage client
        
        Args:
            connection_string: Azure Storage connection string
            container_name: Container name for storing reports
        """
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING environment variable not set")
        
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Create container if it doesn't exist
        try:
            self.container_client.create_container()
            logger.info(f"Created container: {container_name}")
        except Exception:
            logger.info(f"Container already exists: {container_name}")
    
    async def upload_report(
        self,
        tenant_id: str,
        file: UploadFile,
        parsed_data: dict
    ) -> str:
        """
        Upload medical report with tenant isolation
        
        Args:
            tenant_id: Tenant identifier
            file: PDF file to upload
            parsed_data: Parsed medical data from Gemini
        
        Returns:
            report_id: Unique identifier for the report (blob path)
        """
        try:
            self._assert_tenant_scope(tenant_id)
            # Create tenant-specific blob path
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_name = file.filename.replace(" ", "_")
            blob_name = f"{tenant_id}/{timestamp}_{file_name}"
            
            # Get blob client
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Read file content
            file_content = await file.read()
            
            # Upload PDF file
            blob_client.upload_blob(file_content, overwrite=True)
            
            # Set metadata
            metadata = {
                "tenant_id": tenant_id,
                "file_name": file.filename,
                "upload_date": datetime.utcnow().isoformat(),
                "content_type": file.content_type or "application/pdf",
                "file_size_bytes": str(len(file_content))
            }
            blob_client.set_blob_metadata(metadata)
            
            # Upload parsed data as separate JSON blob
            parsed_blob_name = f"{blob_name}.json"
            parsed_blob_client = self.container_client.get_blob_client(parsed_blob_name)
            parsed_blob_client.upload_blob(
                json.dumps(parsed_data, indent=2),
                overwrite=True
            )
            
            logger.info(f"Uploaded report for tenant {tenant_id}: {blob_name}")
            return blob_name
            
        except Exception as e:
            logger.error(f"Error uploading report: {str(e)}")
            raise
    
    async def list_reports(
        self,
        tenant_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[dict]:
        """
        List all reports for specific tenant
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of reports to return
            offset: Number of reports to skip
        
        Returns:
            List of report metadata
        """
        try:
            self._assert_tenant_scope(tenant_id)
            reports = []
            
            # List blobs with tenant prefix (security isolation)
            blob_list = self.container_client.list_blobs(
                name_starts_with=f"{tenant_id}/"
            )
            
            count = 0
            skipped = 0
            
            for blob in blob_list:
                # Skip JSON files (parsed data)
                if blob.name.endswith('.json'):
                    continue
                
                # Skip offset items
                if skipped < offset:
                    skipped += 1
                    continue
                
                # Stop at limit
                if count >= limit:
                    break
                
                # Get metadata
                blob_client = self.container_client.get_blob_client(blob.name)
                properties = blob_client.get_blob_properties()
                metadata = properties.metadata or {}
                
                reports.append({
                    "report_id": blob.name,
                    "file_name": metadata.get("file_name", blob.name.split('/')[-1]),
                    "upload_date": metadata.get("upload_date"),
                    "size_bytes": blob.size,
                    "tenant_id": tenant_id
                })
                
                count += 1
            
            logger.info(f"Listed {len(reports)} reports for tenant {tenant_id}")
            return reports
            
        except Exception as e:
            logger.error(f"Error listing reports: {str(e)}")
            raise
    
    async def get_report(self, report_id: str, tenant_id: str) -> dict:
        """
        Get specific report with parsed data
        
        Args:
            report_id: Report identifier (blob path)
            tenant_id: Tenant identifier for security check
        
        Returns:
            Report data with metadata and parsed content
        
        Raises:
            Exception: If report not found or access denied
        """
        try:
            self._assert_tenant_scope(tenant_id)
            # Security check: ensure report belongs to tenant
            if not report_id.startswith(f"{tenant_id}/"):
                raise Exception("Access denied: Report does not belong to this tenant")
            
            # Get PDF blob
            blob_client = self.container_client.get_blob_client(report_id)
            
            if not blob_client.exists():
                raise Exception("Report not found")
            
            # Get properties and metadata
            properties = blob_client.get_blob_properties()
            metadata = properties.metadata or {}
            
            # Get parsed data
            parsed_blob_name = f"{report_id}.json"
            parsed_blob_client = self.container_client.get_blob_client(parsed_blob_name)
            
            parsed_data = {}
            if parsed_blob_client.exists():
                parsed_content = parsed_blob_client.download_blob().readall()
                parsed_data = json.loads(parsed_content)
            
            logger.info(f"Retrieved report {report_id} for tenant {tenant_id}")
            
            return {
                "report_id": report_id,
                "tenant_id": metadata.get("tenant_id"),
                "file_name": metadata.get("file_name"),
                "upload_date": metadata.get("upload_date"),
                "size_bytes": properties.size,
                "parsed_data": parsed_data
            }
            
        except Exception as e:
            logger.error(f"Error getting report: {str(e)}")
            raise
    
    async def delete_report(self, report_id: str, tenant_id: str):
        """
        Delete report and its parsed data
        
        Args:
            report_id: Report identifier (blob path)
            tenant_id: Tenant identifier for security check
        
        Raises:
            Exception: If access denied
        """
        try:
            self._assert_tenant_scope(tenant_id)
            # Security check
            if not report_id.startswith(f"{tenant_id}/"):
                raise Exception("Access denied: Report does not belong to this tenant")
            
            # Delete PDF blob
            blob_client = self.container_client.get_blob_client(report_id)
            if blob_client.exists():
                blob_client.delete_blob()
            
            # Delete parsed JSON blob
            parsed_blob_name = f"{report_id}.json"
            parsed_blob_client = self.container_client.get_blob_client(parsed_blob_name)
            if parsed_blob_client.exists():
                parsed_blob_client.delete_blob()
            
            logger.info(f"Deleted report {report_id} for tenant {tenant_id}")
            
        except Exception as e:
            logger.error(f"Error deleting report: {str(e)}")
            raise

    @staticmethod
    def _assert_tenant_scope(tenant_id: str) -> None:
        """Ensure the tenant context matches the requested tenant."""
        current_tenant = get_current_tenant()
        if current_tenant is not None and current_tenant != tenant_id:
            raise Exception("Tenant context mismatch detected.")
