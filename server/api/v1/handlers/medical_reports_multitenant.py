"""
Tenant-scoped medical report endpoints.
"""

from __future__ import annotations
from fastapi import (
    APIRouter, UploadFile, File, Depends, HTTPException, status, Query, BackgroundTasks, Request
)
import time
import io
import logging
import zipfile
from typing import List, Optional
import asyncio
import httpx

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from bson import ObjectId
from pydantic import BaseModel
from server.config.settings import get_settings
from server.integrations.azure_multitenant import MultiTenantAzureBlobClient
from server.integrations.mongodb import MongoDBClient
from server.integrations.gemini import GeminiParser
from server.middleware.auth import (
    AuthenticatedTenant,
    resolve_tenant,
)
from server.models.tenant import tenant_manager
from server.utils.usage_tracker import usage_tracker
from server.utils.confidence_calculator import calculate_confidence

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Medical Reports"])


def _get_gemini_client() -> GeminiParser:
    """Return a cached Gemini client instance."""
    if not hasattr(_get_gemini_client, "_client"):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini integration is not configured.",
            )
        _get_gemini_client._client = GeminiParser(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
    return _get_gemini_client._client  # type: ignore[attr-defined]


def _get_storage_client() -> MultiTenantAzureBlobClient:
    """Return a cached storage client instance."""
    if not hasattr(_get_storage_client, "_client"):
        settings = get_settings()
        if not settings.azure_connection_string:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Azure storage is not configured.",
            )
        _get_storage_client._client = MultiTenantAzureBlobClient(
            connection_string=settings.azure_connection_string,
            container_name=settings.azure_container_name,
        )
    return _get_storage_client._client  # type: ignore[attr-defined]

class ReportStatus(BaseModel):
    report_id: str
    status: str  # "pending", "completed", "failed"
    message: Optional[str] = None
    parsed_data: Optional[dict] = None

@router.post(
    "aync/tenants/{tenant_id}/projects/{project_id}/reports",
    summary="Upload medical report(s) for project",
    description="Upload one or more PDF medical reports for a specific project. Files are parsed using the project's assigned AI model.",
)
async def upload_report(
    tenant_id: str,
    project_id: str,
    file: List[UploadFile] = File(..., description="PDF medical report(s) or ZIP file containing PDFs"),
    webhook_url: Optional[str] = Query(None, description="Optional webhook URL to POST parsed report when ready (used when waitForParsedResponse=false)"),
    background_tasks: BackgroundTasks = None,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    db = await MongoDBClient.get_database()
    projects_collection = db["projects"]
    ai_models_collection = db["ai_models"]
    parsed_reports_collection = db["parsed_reports"]
    

    # Verify project
    project = await projects_collection.find_one({"project_id": project_id, "tenant_id": tenant_id})
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found for tenant '{tenant_id}'")
    if not project.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Project '{project_id}' is not active.")

    # Check tenant status (active)
    tenant = await db["tenants"].find_one({"tenant_id": tenant_id})
    if not tenant or not tenant.get("active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tenant '{tenant_id}' is not active.")

    ai_model_id = project.get("ai_model_id")
    if not ai_model_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Project '{project_id}' has not activeted please contact contact@yira.ai")

    ai_model = await ai_models_collection.find_one({"model_id": ai_model_id, "tenant_id": tenant_id})
    if not ai_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AI model '{ai_model_id}' not found")

    settings = get_settings()
    selected_model = ai_model.get("model_name")
    print("Using Gemini model:", selected_model)
    gemini_client = GeminiParser(api_key=settings.gemini_api_key, model=selected_model)

    # File handling (same as before)
    pdf_files = []
    total_size_mb = 0.0
    for uploaded_file in file:
        file_bytes = await uploaded_file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)
        total_size_mb += file_size_mb
        is_zip = (uploaded_file.filename and uploaded_file.filename.lower().endswith('.zip')) or (
            uploaded_file.content_type and 'zip' in uploaded_file.content_type.lower()
        )
        if is_zip:
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_ref:
                    for zip_info in zip_ref.namelist():
                        if '__MACOSX' in zip_info or zip_info.endswith('/'):
                            continue
                        if zip_info.lower().endswith('.pdf'):
                            pdf_bytes = zip_ref.read(zip_info)
                            pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
                            pdf_files.append({'filename': zip_info, 'bytes': pdf_bytes, 'size_mb': pdf_size_mb})
            except zipfile.BadZipFile:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File '{uploaded_file.filename}' is not a valid ZIP file.")
        else:
            if uploaded_file.content_type and uploaded_file.content_type.lower() != "application/pdf":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Only PDF and ZIP files are supported. Got: {uploaded_file.content_type}")
            pdf_files.append({'filename': uploaded_file.filename or 'document.pdf', 'bytes': file_bytes, 'size_mb': file_size_mb})

    if not pdf_files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No PDF files found in the uploaded file(s).")

    # Generate unique reportId
    report_object_id = ObjectId()
    report_id = str(report_object_id)
    usage_tracker.track_upload(tenant_id, total_size_mb)

    async def do_parsing_and_save(job_id,update_record=False):
        parse_start_time = time.time()
        consolidated_data = None
        parsed_results = []
        # Parse files (same as before)
        if len(pdf_files) > 1:
            try:
                consolidated_data = gemini_client.parse_multiple_pdfs(pdf_files)
                if consolidated_data:
                    parsed_results = [{'filename': pdf['filename'], 'data': consolidated_data} for pdf in pdf_files]
            except Exception as exc:
                consolidated_data = None
        if not consolidated_data:
            parsed_results = []
            for pdf_file in pdf_files:
                try:
                    parsed_data = gemini_client.parse_pdf(pdf_file['bytes'], pdf_file['filename'])
                    if parsed_data:
                        parsed_results.append({'filename': pdf_file['filename'], 'data': parsed_data})
                except Exception as exc:
                    continue
            if not parsed_results:
                failed_doc = {"status": "failed", "message": "Failed to parse any of the uploaded PDF files."}
                await parsed_reports_collection.update_one(
                    {"report_id": report_id},
                    {"$set": failed_doc}
                )
                # send webhook failure if requested
                if webhook_url:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            response = await client.post(webhook_url, json={
                                "tenant_id": tenant_id,
                                "project_id": project_id,
                                "job_id": job_id,
                                "status": "failed",
                                "message": failed_doc["message"]
                            })
                            if response.status_code >= 200 and response.status_code < 300:
                                logger.info("Webhook delivered successfully to %s (status: %d)", webhook_url, response.status_code)
                                await parsed_reports_collection.update_one(
                                    {"report_id": report_id},
                                    {"$set": {"webhook_meta.delivered": True}}
                                )
                            else:
                                logger.warning("Webhook delivery failed to %s (status: %d)", webhook_url, response.status_code)
                    except Exception as e:
                        logger.warning("Failed to POST failure webhook to %s: %s", webhook_url, e)
                return
            consolidated_data = _merge_parsed_reports(parsed_results)
        parse_end_time = time.time()
        parsing_time_seconds = round(parse_end_time - parse_start_time, 2)
        first_file = file[0]
        blob_url = None

        clean_parsed_data = consolidated_data.copy() if isinstance(consolidated_data, dict) else {}
        gemini_confidence = clean_parsed_data.pop("confidence_score", None)
        gemini_confidence_summary = clean_parsed_data.pop("confidence_summary", None)
        validated_confidence, validated_summary, validation_details = calculate_confidence(
            parsed_data=clean_parsed_data or consolidated_data,
            gemini_confidence=gemini_confidence
        )
        parsed_report_doc = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "report_id": report_id,
            "blob_url": blob_url,
            "parsing_time_seconds": parsing_time_seconds,
            "confidence_score": validated_confidence,
            "confidence_summary": validated_summary,
            "total_size_mb": round(total_size_mb, 2),
            "files_processed": len(pdf_files),
            "successful_parses": len(parsed_results),
            "failed_parses": len(pdf_files) - len(parsed_results),
            "parsed_data": clean_parsed_data or consolidated_data,
            "status": "completed",
            "message": f"Successfully processed {len(parsed_results)} of {len(pdf_files)} PDF file(s) in {parsing_time_seconds}s.",
            "created_at": time.time(),
        }
        if update_record:
            await parsed_reports_collection.update_one(
                 {"_id": ObjectId(job_id)},
                 {"$set": parsed_report_doc}
            )
            # Ensure webhook_meta is not lost after update
            await parsed_reports_collection.update_one(
                {"_id": ObjectId(job_id)},
                {"$setOnInsert": {"webhook_meta": {
                    "delivered": False,
                    "status": "pending",
                    "webhook_url": webhook_url
                }}}
            )
        else:
            await parsed_reports_collection.insert_one(parsed_report_doc)

        # send webhook on success if provided
        if webhook_url:
            try:
                # fetch latest doc for completeness (or use parsed_report_doc)
                try:
                    latest_doc = await parsed_reports_collection.find_one({"_id": ObjectId(job_id)})
                    parsed_data_only = latest_doc.get("parsed_data")
                except Exception:
                    latest_doc = parsed_report_doc
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(webhook_url, json={
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "status": parsed_report_doc.get("status", "completed"),
                        "report": parsed_data_only
                    })
                    if response.status_code >= 200 and response.status_code < 300:
                        logger.info("Webhook delivered successfully to %s (status: %d)", webhook_url, response.status_code)
                        await parsed_reports_collection.update_one(
                            {"_id": ObjectId(job_id)},
                            {"$set": {"webhook_meta.delivered": True, "webhook_meta.status": "success", "webhook_meta.webhook_url": webhook_url}}
                        )
                    else:
                        logger.warning("Webhook delivery failed to %s (status: %d)", webhook_url, response.status_code)
                        await parsed_reports_collection.update_one(
                            {"_id": ObjectId(job_id)},
                            {"$set": {"webhook_meta.delivered": False, "webhook_meta.status": f"fail ({response.status_code})", "webhook_meta.webhook_url": webhook_url}}
                        )
            except Exception as e:
                logger.warning("Failed to POST success webhook to %s: %s", webhook_url, e)
                await parsed_reports_collection.update_one(
                    {"_id": ObjectId(job_id)},
                    {"$set": {"webhook_meta.delivered": False, "webhook_meta.status": f"fail ({str(e)[:100]})", "webhook_meta.webhook_url": webhook_url}}
                )

    # For async: Immediately persist with status "pending", then queue parsing
    result = await parsed_reports_collection.insert_one({
        "tenant_id": tenant_id,
        "project_id": project_id,
        "report_id": report_id,
        "status": "pending",
        "message": "Parsing queued",
        "created_at": time.time(),
        "webhook_meta": { 
            "delivered": False,
            "status": "pending",
            "webhook_url": webhook_url
        }
    })
    job_id = str(result.inserted_id)
    asyncio.create_task(do_parsing_and_save(job_id, update_record=True))
    return {"success": True, "job_id": job_id, "status": "pending", "message": "Parsing queued", "callback_url": webhook_url}



@router.get(
    "/job/status/{Job_id}",
    summary="Get report processing status (Job Status)",
    description="Fetch the current status of a report being processed asynchronously. Use report_id as the job ID.",
)
async def get_report_status(
    Job_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Get the processing status of a report by report_id (job_id).
    
    Returns:
    - status: "pending", "completed", or "failed"
    - message: Human-readable status message
    - parsing_time_seconds: Time taken to parse (if completed)
    - confidence_score: Confidence of parsed data (if completed)
    - files_processed: Number of files processed
    - webhook_delivered: Whether webhook was successfully delivered (if applicable)
    """
    db = await MongoDBClient.get_database()
    parsed_reports_collection = db["parsed_reports"]

    try:
        report = await parsed_reports_collection.find_one({"_id": ObjectId(Job_id)})

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{Job_id}' not found or access denied.",
            )

        # Build status response
        status_response = {
            "job_id": Job_id,
            "Parsing status": report.get("status", "unknown"),
            "message": report.get("message", ""),
            "created_at": report.get("created_at"),
            "weebhook_meta": report.get("webhook_meta", None),
        }

        return status_response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch report status '%s' for tenant %s: %s", Job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch report status at this time.",
        ) from exc


@router.get(
    "/tenants/{tenant_id}/reports",
    summary="List reports for tenant",
    description="Retrieve metadata for reports that belong to the tenant.",
)
async def list_reports(
    tenant_id: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of reports to return."),
    offset: int = Query(0, ge=0, description="Number of reports to skip from the start."),
    projectid: Optional[str] = Query(None, description="Filter reports by project id (query param: projectid)"),
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """List reports that belong to the authenticated tenant."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)
    usage_tracker.track_api_call(tenant_id, "list_reports")

    db = await MongoDBClient.get_database()
    parsed_reports_collection = db["parsed_reports"]

    try:
        # Build base filter scoped to tenant
        filter_query: dict = {"tenant_id": tenant_id}
        # Optional project filter
        if projectid:
            filter_query["project_id"] = projectid

        cursor = parsed_reports_collection.find(filter_query).skip(offset).limit(limit)
        reports = await cursor.to_list(length=limit)
        reports = [_serialize_mongodb_doc(report) for report in reports]
        total_reports = await parsed_reports_collection.count_documents(filter_query)
        return {
            "success": True,
            "tenant_id": tenant_id,
            "project_id": projectid,
            "limit": limit,
            "offset": offset,
            "total_reports": total_reports,
            "reports": reports,
        }
    except Exception as exc:
        logger.exception("Failed to list reports for tenant %s: %s", tenant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch reports at this time.",
        ) from exc


@router.get(
    "/tenants/{tenant_id}/reports/{report_id:path}",
    summary="Get report details",
    description="Retrieve a specific report and its parsed data for the tenant.",
)
async def get_report(
    tenant_id: str,
    report_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """Fetch report data for the authenticated tenant."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)
    usage_tracker.track_api_call(tenant_id, "get_report")

    db = await MongoDBClient.get_database()
    parsed_reports_collection = db["parsed_reports"]

    try:
        report = await parsed_reports_collection.find_one({"tenant_id": tenant_id, "report_id": report_id})
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found or access denied.",
            )
        return {
            "success": True, 
            "tenant_id": tenant_id, 
            "report": _serialize_mongodb_doc(report)
        }
    except Exception as exc:
        logger.exception("Failed to fetch report '%s' for tenant %s: %s", report_id, tenant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied.",
        ) from exc


@router.delete(
    "/tenants/{tenant_id}/reports/{report_id:path}",
    summary="Delete report",
    description="Delete a report and its parsed data for the tenant.",
)
async def delete_report(
    tenant_id: str,
    report_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """Delete a report belonging to the tenant."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)

    db = await MongoDBClient.get_database()
    parsed_reports_collection = db["parsed_reports"]
    storage_client = _get_storage_client()

    try:
        report = await parsed_reports_collection.find_one({"tenant_id": tenant_id, "report_id": report_id})
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found or already deleted.",
            )
        # Delete blob from Azure if blob_url exists
        blob_url = report.get("blob_url")
        if blob_url and hasattr(storage_client, "delete_blob_by_url"):
            try:
                await storage_client.delete_blob_by_url(blob_url)
            except Exception as exc:
                logger.warning("Failed to delete blob from Azure: %s", exc)
        # Delete metadata from MongoDB
        await parsed_reports_collection.delete_one({"tenant_id": tenant_id, "report_id": report_id})
        return {
            "success": True,
            "tenant_id": tenant_id,
            "message": f"Report '{report_id}' deleted successfully.",
        }
    except Exception as exc:
        logger.exception("Failed to delete report '%s' for tenant %s: %s", report_id, tenant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or already deleted.",
        ) from exc


@router.post(
    "/tenants/{tenant_id}/reports/{report_id:path}/generate",
    summary="Trigger report generation",
    description="Re-run parsing or generate a derived report.",
)
async def generate_report(
    tenant_id: str,
    report_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """Trigger report regeneration for the tenant."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)
    usage_tracker.track_report_generation(tenant_id)

    db = await MongoDBClient.get_database()
    parsed_reports_collection = db["parsed_reports"]

    try:
        report = await parsed_reports_collection.find_one({"tenant_id": tenant_id, "report_id": report_id})
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found or access denied.",
            )
        return {
            "success": True,
            "tenant_id": tenant_id,
            "report_id": report_id,
            "status": "processing",
            "message": "Report generation triggered.",
            "report": _serialize_mongodb_doc(report),
        }
    except Exception as exc:
        logger.exception(
            "Failed to trigger generation for report '%s' tenant %s: %s",
            report_id,
            tenant_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied.",
        ) from exc


@router.get(
    "/tenants/{tenant_id}/usage",
    summary="Get usage summary",
    description="Retrieve aggregated usage statistics for billing and analytics.",
)
async def get_usage(
    tenant_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """Return aggregate usage metrics for the tenant."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)
    usage = usage_tracker.get_usage(tenant_id)
    return {"success": True, "tenant_id": tenant_id, "usage": usage}


@router.get(
    "/tenants/{tenant_id}/usage/monthly",
    summary="Get monthly usage",
    description="Retrieve usage for a specific month with derived billing totals.",
)
async def get_monthly_usage(
    tenant_id: str,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format."),
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """Return monthly usage metrics and computed billing totals."""
    logger.debug("Tenant %s authenticated via %s", auth.tenant_id, auth.method)
    usage = usage_tracker.get_monthly_usage(tenant_id, month)

    # Example pricing model for demos
    price_per_upload = 0.50
    price_per_gb = 5.00
    price_per_generation = 0.25

    uploads = usage.get("uploads", 0)
    storage_gb = usage.get("storage_mb", 0.0) / 1024
    generations = usage.get("reports_generated", 0)

    total_cost = (uploads * price_per_upload) + (storage_gb * price_per_gb) + (generations * price_per_generation)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "month": month or "current",
        "usage": usage,
        "billing": {
            "uploads": round(uploads * price_per_upload, 2),
            "storage": round(storage_gb * price_per_gb, 2),
            "generations": round(generations * price_per_generation, 2),
            "total_usd": round(total_cost, 2),
        },
    }


def _merge_parsed_reports(parsed_results: List[dict]) -> dict:
    """
    Merge multiple parsed report results into a single consolidated report.
    
    Args:
        parsed_results: List of dicts with 'filename' and 'data' keys
        
    Returns:
        Consolidated report data with merged fields and batch_info
    """
    if not parsed_results:
        return {}
    
    if len(parsed_results) == 1:
        # Single report, no batch info needed
        result = parsed_results[0]['data'].copy()
        # Remove batch_info if it exists (added by parse_multiple_pdfs)
        result.pop('batch_info', None)
        return result
    
    # Start with first report as base
    consolidated = parsed_results[0]['data'].copy()
    # Remove batch_info - will be added at root level in response
    consolidated.pop('batch_info', None)
    
    # Array fields that should be merged by extending
    array_fields = ['medications', 'procedures', 'lab_results', 'imaging_findings', 'recommendations']
    
    # Merge data from remaining reports
    for result in parsed_results[1:]:
        data = result['data']
        filename = result['filename']
        
        # Merge array fields
        for field in array_fields:
            if field in data and data[field]:
                # Initialize field if not present or empty
                if field not in consolidated or not consolidated[field]:
                    consolidated[field] = []
                
                # Ensure it's a list before extending
                if not isinstance(consolidated[field], list):
                    consolidated[field] = [consolidated[field]] if consolidated[field] else []
                
                # Ensure source data is a list
                source_data = data[field] if isinstance(data[field], list) else [data[field]]
                
                # Add source_file attribution to each item
                for item in source_data:
                    if isinstance(item, dict):
                        item['source_file'] = filename
                
                consolidated[field].extend(source_data)
        
        # Merge diagnosis (can be string or list)
        if 'diagnosis' in data and data['diagnosis']:
            if 'diagnosis' not in consolidated or not consolidated['diagnosis']:
                consolidated['diagnosis'] = []
            
            # Normalize consolidated diagnosis to list
            if isinstance(consolidated['diagnosis'], str):
                consolidated['diagnosis'] = [consolidated['diagnosis']]
            elif not isinstance(consolidated['diagnosis'], list):
                consolidated['diagnosis'] = []
            
            # Normalize source diagnosis to list
            source_diagnosis = data['diagnosis']
            if isinstance(source_diagnosis, str):
                source_diagnosis = [source_diagnosis]
            elif not isinstance(source_diagnosis, list):
                source_diagnosis = [str(source_diagnosis)] if source_diagnosis else []
            
            # Merge without duplicates
            for diag in source_diagnosis:
                if diag and diag not in consolidated['diagnosis']:
                    consolidated['diagnosis'].append(diag)
        
        # Merge photo_comparison data
        if 'photo_comparison' in data and data['photo_comparison']:
            pc_data = data['photo_comparison']
            
            if 'photo_comparison' not in consolidated or not consolidated['photo_comparison']:
                consolidated['photo_comparison'] = {
                    'images_found': [],
                    'comparison_performed': False,
                    'similarity_percentage': None,
                    'comparison_details': None,
                    'notes': '',
                }
            
            # Merge images_found with offset for image numbers
            if 'images_found' in pc_data and pc_data['images_found']:
                existing_images = consolidated['photo_comparison'].get('images_found', [])
                offset = len(existing_images)
                
                for img in pc_data['images_found']:
                    new_img = img.copy()
                    new_img['image_number'] = img.get('image_number', 0) + offset
                    new_img['source_file'] = filename
                    existing_images.append(new_img)
                
                consolidated['photo_comparison']['images_found'] = existing_images
            
            # Update comparison fields if not already set
            if pc_data.get('comparison_performed') and not consolidated['photo_comparison'].get('comparison_performed'):
                consolidated['photo_comparison']['comparison_performed'] = True
            
            if pc_data.get('similarity_percentage') is not None and consolidated['photo_comparison'].get('similarity_percentage') is None:
                consolidated['photo_comparison']['similarity_percentage'] = pc_data['similarity_percentage']
            
            if pc_data.get('comparison_details') and not consolidated['photo_comparison'].get('comparison_details'):
                consolidated['photo_comparison']['comparison_details'] = pc_data['comparison_details']
            
            # Merge notes
            if pc_data.get('notes'):
                existing_notes = consolidated['photo_comparison'].get('notes', '')
                if existing_notes:
                    consolidated['photo_comparison']['notes'] = f"{existing_notes} | {pc_data['notes']}"
                else:
                    consolidated['photo_comparison']['notes'] = pc_data['notes']
    
    # After merging all photo comparisons, check if we have 2+ images but no comparison
    if consolidated.get('photo_comparison'):
        pc = consolidated['photo_comparison']
        images_count = len(pc.get('images_found', []))
        
        # If we have 2+ images but comparison wasn't performed, log warning
        if images_count >= 2 and not pc.get('comparison_performed'):
            logger.warning(
                "Photo comparison has %d images but comparison_performed=False. "
                "This may indicate Gemini didn't follow instructions.",
                images_count
            )
            # Force it to show that comparison should have been performed
            pc['notes'] = (pc.get('notes', '') + 
                          f" | WARNING: {images_count} images found but comparison not performed by AI.").strip()
    
    return consolidated
    
def _serialize_mongodb_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format."""
    if not doc:
        return doc
        
    result = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, dict):
            result[key] = _serialize_mongodb_doc(value)
        elif isinstance(value, list):
            result[key] = [
                _serialize_mongodb_doc(item) if isinstance(item, dict) else 
                str(item) if isinstance(item, ObjectId) else item 
                for item in value
            ]
        else:
            result[key] = value
    return result

@router.post(
    "/webhook/test",
    summary="Test webhook receiver",
    description="Receive webhook POSTs for testing — logs headers, URL, and payload and returns a simple acknowledgement.",
)
async def webhook_test(request: Request):
    """
    Simple webhook endpoint for testing incoming payloads.
    Logs URL, headers, and payload (attempts JSON decode, falls back to text/bytes).
    """
    try:
        # Capture request metadata
        url = str(request.url)
        headers = dict(request.headers)
        content_type = headers.get("content-type", "")
        payload = None

        # Attempt to parse the body
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                # fall back to raw body if JSON decode fails
                raw = await request.body()
                try:
                    payload = raw.decode("utf-8", errors="replace")
                except Exception:
                    payload = raw
        else:
            raw = await request.body()
            try:
                payload = raw.decode("utf-8", errors="replace")
            except Exception:
                payload = raw

        # ✅ Log full details
        logger.info("WEBHOOK TEST RECEIVED — URL: %s", url)
        logger.info("WEBHOOK TEST RECEIVED — Headers: %s", headers)
        logger.info("WEBHOOK TEST RECEIVED — Payload: %s", payload)

        return {
            "success": True,
            "received": True,
            "note": "Logged URL, headers, and payload on server",
            "url": url
        }

    except Exception as exc:
        logger.exception("Error handling webhook test: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook handler error"
        )
