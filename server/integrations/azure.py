"""
Azure Blob Storage integration module
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)


class AzureBlobStorage:
    """Azure Blob Storage client for report persistence"""

    def __init__(self, connection_string: str, container_name: str):
        """
        Initialize Azure Blob Storage client

        Args:
            connection_string: Azure Storage connection string
            container_name: Container name for storing reports
        """
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        self.container_client = None
        self._ensure_container_exists()

    def _ensure_container_exists(self) -> None:
        """Create container if it doesn't exist"""
        try:
            self.container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            try:
                self.container_client.get_container_properties()
                logger.info(f"Connected to container: {self.container_name}")
            except Exception:
                logger.info(f"Creating container: {self.container_name}")
                self.container_client = self.blob_service_client.create_container(
                    self.container_name
                )
        except Exception as e:
            logger.error(f"Error ensuring container exists: {str(e)}")
            raise

    def save(
        self, report_data: Dict[str, Any], original_filename: str, report_id: str
    ) -> str:
        """
        Save report to Azure Blob Storage

        Args:
            report_data: Parsed report data
            original_filename: Original PDF filename
            report_id: Unique report identifier

        Returns:
            Blob name/path
        """
        try:
            # Safely extract patient name with fallback
            patient_info = report_data.get("patient_info") or {}
            patient_name = patient_info.get("name") or "unknown"
            # Ensure patient_name is a string before calling replace
            if patient_name:
                patient_name = str(patient_name).replace(" ", "_")
            else:
                patient_name = "unknown"
                
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"reports/{patient_name}_{timestamp}_{report_id}.json"

            # Prepare blob metadata
            metadata = {
                "reportId": report_id,
                "fileName": original_filename,
                "uploadedAt": datetime.utcnow().isoformat(),
                "dataVersion": "1.0",
            }

            # Upload to blob
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.upload_blob(
                json.dumps(report_data, indent=2), overwrite=True, metadata=metadata
            )

            logger.info(f"Report saved to blob: {blob_name}")
            return blob_name
        except Exception as e:
            logger.error(f"Error saving report to blob storage: {str(e)}")
            raise

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve report from Azure Blob Storage

        Args:
            report_id: Unique report identifier

        Returns:
            Report data or None if not found
        """
        try:
            blob_list = self.container_client.list_blobs(name_starts_with="reports/")

            for blob in blob_list:
                if report_id in blob.name:
                    blob_client = self.container_client.get_blob_client(blob.name)
                    blob_data = blob_client.download_blob().readall()
                    report = json.loads(blob_data)
                    return report

            logger.warning(f"Report not found: {report_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving report from blob storage: {str(e)}")
            raise

    def list_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List all reports from Azure Blob Storage

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of report summaries
        """
        try:
            reports = []
            blob_list = self.container_client.list_blobs(name_starts_with="reports/")

            for blob in blob_list:
                try:
                    blob_client = self.container_client.get_blob_client(blob.name)
                    blob_data = blob_client.download_blob().readall()
                    report = json.loads(blob_data)
                    report["blobName"] = blob.name
                    reports.append(report)

                    if limit and len(reports) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"Error loading blob {blob.name}: {str(e)}")
                    continue

            # Sort by upload time (descending)
            reports.sort(
                key=lambda x: x.get("uploadedAt", ""), reverse=True
            )
            logger.info(f"Retrieved {len(reports)} reports from blob storage")
            return reports
        except Exception as e:
            logger.error(f"Error listing reports from blob storage: {str(e)}")
            raise

    def delete(self, report_id: str) -> bool:
        """
        Delete report from Azure Blob Storage

        Args:
            report_id: Unique report identifier

        Returns:
            True if deleted successfully
        """
        try:
            blob_list = self.container_client.list_blobs(name_starts_with="reports/")

            for blob in blob_list:
                if report_id in blob.name:
                    blob_client = self.container_client.get_blob_client(blob.name)
                    blob_data = blob_client.download_blob().readall()
                    report = json.loads(blob_data)

                    if report.get("reportId") == report_id or report_id in blob.name:
                        blob_client.delete_blob()
                        logger.info(f"Report deleted: {report_id}")
                        return True

            logger.warning(f"Report not found for deletion: {report_id}")
            return False
        except Exception as e:
            logger.error(f"Error deleting report from blob storage: {str(e)}")
            raise

    def search(
        self,
        patient_name: Optional[str] = None,
        report_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search reports by criteria

        Args:
            patient_name: Patient name to search for
            report_date: Report date to filter by

        Returns:
            List of matching reports
        """
        try:
            all_reports = self.list_all()
            filtered_reports = []

            for report in all_reports:
                matches = True

                if patient_name:
                    report_patient = (
                        report.get("patient_info", {})
                        .get("name", "")
                        .lower()
                    )
                    if patient_name.lower() not in report_patient:
                        matches = False

                if report_date:
                    report_date_value = (
                        report.get("report_info", {})
                        .get("date", "")
                    )
                    if report_date not in report_date_value:
                        matches = False

                if matches:
                    filtered_reports.append(report)

            logger.info(f"Search found {len(filtered_reports)} matching reports")
            return filtered_reports
        except Exception as e:
            logger.error(f"Error searching reports: {str(e)}")
            raise
