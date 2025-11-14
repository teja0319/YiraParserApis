## Asynchronous Report Parsing Architecture Refactoring

This document describes the refactored medical report parsing architecture that implements asynchronous job processing with background workers.

### Overview

The system has been redesigned to use a **job-based architecture** with the following workflow:

1. **Upload Phase**: Files are uploaded to blob storage immediately, creating a pending job
2. **Async Processing**: Background worker picks up pending jobs every 2 minutes
3. **Parsing Phase**: Files are downloaded from blob and parsed by the AI model
4. **Completion**: Job status is updated and optional webhooks are sent

### Architecture Changes

#### 1. New Components

##### `server/models/parsing_job.py`
Defines the job data model with the following key classes:

- **`JobStatus`**: Enum with states: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`
- **`ParsingJob`**: Main job schema containing:
  - Job metadata (tenant_id, project_id, report_id)
  - File information (blob URLs)
  - Status tracking
  - Retry configuration
  - Webhook delivery metadata
  - Parsing results and timestamps

##### `server/workers/parsing_worker.py`
Background worker service that:

- **Polls every 2 minutes** for pending jobs (configurable via `POLLING_INTERVAL_SECONDS`)
- **Processes up to 10 jobs per cycle** (configurable via `BATCH_SIZE`)
- **Downloads files from blob storage** using provided URLs
- **Parses using assigned AI model** (per-project model selection)
- **Implements retry logic** (max 3 retries by default, configurable)
- **Sends webhook callbacks** on success/failure
- **Handles errors gracefully** with detailed error logging

Key methods:
- `start()`: Begins the polling loop
- `_process_batch()`: Fetches and processes pending jobs
- `_process_job()`: Handles individual job lifecycle
- `_parse_files()`: Parses PDFs with fallback logic
- `_send_webhook()`: Delivers completion callbacks
- `_handle_job_failure()`: Manages retry logic and failure handling

#### 2. Modified Components

##### `server/integrations/azure_multitenant.py`
Added new methods for blob operations:

- **`upload_file_bytes()`**: Upload raw file bytes to blob storage
  - Returns full blob URL for later download
  - Stores metadata for tracking
  
- **`download_file_bytes()`**: Download file bytes from blob storage by URL
  - Validates tenant scoping
  - Extracts blob name from URL
  
- **`delete_blob_by_url()`**: Delete blob by URL with tenant validation

##### `server/integrations/mongodb.py`
Added indexes for parsing_jobs and parsed_reports collections:

```python
# parsing_jobs indexes
- tenant_id (ASCENDING)
- status (ASCENDING)
- status + created_at (for job queue queries)
- created_at (DESCENDING for ordering)
- retry_count (ASCENDING)

# parsed_reports indexes
- tenant_id (ASCENDING)
- project_id (ASCENDING)
- job_id (ASCENDING)
- created_at (DESCENDING)
```

##### `server/api/v1/handlers/medical_reports_multitenant.py`

**`upload_report()` endpoint** - REFACTORED:
```
OLD: Parse files synchronously, return after parsing complete
NEW: 
  1. Validate project and tenant
  2. Extract PDFs from uploaded files/ZIPs
  3. Upload files to blob storage immediately
  4. Create pending job in parsing_jobs collection
  5. Return job_id immediately (no parsing)
```

Request Flow:
```
POST /tenants/{tenant_id}/projects/{project_id}/reports
  ├─ Validate project/tenant
  ├─ Extract PDFs
  ├─ Upload to blob storage → returns blob URLs
  ├─ Create job entry with status="pending"
  └─ Return {"job_id": "...", "status": "pending", ...}
```

Response:
```json
{
  "success": true,
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "pending",
  "message": "Report upload successful. Parsing will begin shortly.",
  "files_uploaded": 1,
  "total_size_mb": 2.5,
  "webhook_url": "https://..."
}
```

**`get_report_status()` endpoint** - UPDATED:
```
OLD: Path /job/status/{Job_id} with minimal response
NEW: Path /job/status/{job_id} with comprehensive status
```

Returns detailed job information including:
- Job status and timestamps
- Parsing metrics (files processed, confidence score)
- Parsed data (when completed)
- Retry information (when failed)
- Webhook delivery status

Response:
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "completed",
  "message": "Successfully processed 1 file(s) in 45.23s",
  "created_at": 1704830400.0,
  "started_at": 1704830402.1,
  "completed_at": 1704830447.33,
  "files_processed": 1,
  "successful_parses": 1,
  "failed_parses": 0,
  "parsing_time_seconds": 45.23,
  "confidence_score": 0.92,
  "confidence_summary": "High confidence in extracted data",
  "parsed_data": {...},
  "webhook_status": {
    "delivered": true,
    "status": "success",
    "attempts": 1,
    "last_attempt_at": 1704830448.0
  }
}
```

##### `server/main.py`
Updated application lifespan to:
- **Startup**: Initialize parsing worker and start background task
- **Shutdown**: Gracefully stop worker and wait for cleanup

### MongoDB Schema

#### `parsing_jobs` Collection

```javascript
{
  "_id": ObjectId,                    // Job ID
  "tenant_id": String,                // Tenant scope
  "project_id": String,               // Project scope
  "report_id": String,                // Report identifier
  
  // Files
  "files": [
    {
      "filename": String,
      "blob_url": String,
      "size_mb": Number
    }
  ],
  "total_size_mb": Number,
  
  // Status
  "status": String,                   // "pending", "processing", "completed", "failed"
  "message": String,                  // Status message
  
  // Parsing results
  "files_processed": Number,
  "successful_parses": Number,
  "failed_parses": Number,
  "parsing_time_seconds": Number,
  "parsed_data": Object,              // AI model output
  "confidence_score": Number,
  "confidence_summary": String,
  
  // Retry logic
  "retry_count": Number,
  "max_retries": Number,
  "last_error": String,
  
  // Webhook handling
  "webhook_meta": {
    "delivered": Boolean,
    "status": String,
    "webhook_url": String,
    "last_attempt_at": Number,
    "attempts": Number
  },
  
  // Timestamps
  "created_at": Number,               // Unix timestamp
  "started_at": Number,               // When worker started
  "completed_at": Number,             // When worker finished
  
  // AI Model config
  "model_id": String,
  "model_name": String
}
```

### Job Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Upload Phase (Endpoint)                                  │
│    - Files uploaded to blob storage                         │
│    - Job created with status=PENDING                        │
│    - Job ID returned to client                              │
│    - Response sent immediately (no parsing)                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Waiting Phase (Background)                               │
│    - Job sits in PENDING state                              │
│    - Worker checks every 2 minutes                          │
│    - Client can query status anytime via get_report_status  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Processing Phase (Background Worker)                     │
│    - Worker picks job from queue                            │
│    - Status → PROCESSING                                    │
│    - Downloads files from blob URLs                         │
│    - Parses using AI model                                  │
│    - Calculates confidence score                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
              ┌─────────────┴────────────────┐
              ↓                              ↓
    ┌──────────────────┐        ┌──────────────────────┐
    │ Success Path     │        │ Failure Path         │
    ├──────────────────┤        ├──────────────────────┤
    │ Status→COMPLETED │        │ Status→PENDING (r=1) │
    │ Store parsed_data│        │ Store last_error     │
    │ Send webhook     │        │ Increment retry_count│
    │ (if configured)  │        │                      │
    └──────────────────┘        │ After MAX_RETRIES→   │
            ↓                   │ Status→FAILED        │
    ┌──────────────────┐        │ Send failure webhook │
    │ Complete         │        └──────────────────────┘
    └──────────────────┘                   ↓
                              ┌──────────────────────┐
                              │ Final Failure State  │
                              │ Job is FAILED        │
                              │ Won't be retried     │
                              └──────────────────────┘
```

### Configuration

Key settings in `server/config/settings.py`:

```python
# Worker Configuration (new)
PARSING_WORKER_POLLING_INTERVAL = 120  # seconds (2 minutes)
PARSING_WORKER_BATCH_SIZE = 10         # jobs per cycle
PARSING_WORKER_MAX_RETRIES = 3         # retry attempts
PARSING_WORKER_WEBHOOK_TIMEOUT = 10.0  # seconds
```

These can be overridden in the `ParsingWorker` class:
- `POLLING_INTERVAL_SECONDS`: How often to check for pending jobs
- `BATCH_SIZE`: Maximum jobs to process per cycle
- `MAX_RETRIES`: Maximum retry attempts before marking failed
- `WEBHOOK_TIMEOUT_SECONDS`: Timeout for webhook POST requests

### Workflow Example

#### 1. Client uploads report

```bash
curl -X POST "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports" \
  -F "file=@report.pdf" \
  -H "X-API-Key: your-key" \
  -H "Tenant-ID: tenant-001" \
  -G --data-urlencode "webhook_url=https://webhook.example.com/reports"
```

Response:
```json
{
  "success": true,
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "pending",
  "message": "Report upload successful. Parsing will begin shortly.",
  "files_uploaded": 1,
  "total_size_mb": 2.5,
  "webhook_url": "https://webhook.example.com/reports"
}
```

#### 2. Client checks job status

```bash
curl -X GET "http://localhost:8090/api/v1/job/status/507f1f77bcf86cd799439011" \
  -H "X-API-Key: your-key" \
  -H "Tenant-ID: tenant-001"
```

Response (while processing):
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "processing",
  "message": "Parsing in progress",
  "created_at": 1704830400.0,
  "started_at": 1704830402.1,
  "completed_at": null
}
```

Response (after completion):
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "completed",
  "message": "Successfully processed 1 file(s) in 45.23s",
  "created_at": 1704830400.0,
  "started_at": 1704830402.1,
  "completed_at": 1704830447.33,
  "files_processed": 1,
  "successful_parses": 1,
  "failed_parses": 0,
  "parsing_time_seconds": 45.23,
  "confidence_score": 0.92,
  "confidence_summary": "High confidence in extracted data",
  "parsed_data": {
    "patient_name": "John Doe",
    "date_of_visit": "2024-01-10",
    "diagnosis": ["Type 2 Diabetes"],
    "medications": [...],
    "procedures": [...],
    ...
  },
  "webhook_status": {
    "delivered": true,
    "status": "success",
    "attempts": 1,
    "last_attempt_at": 1704830448.0
  }
}
```

#### 3. Webhook callback received by client

The worker sends this to the configured webhook_url:

```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "tenant_id": "tenant-001",
  "project_id": "project-001",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "completed",
  "timestamp": "2024-01-13T10:44:07.330000",
  "parsed_data": {
    "patient_name": "John Doe",
    "date_of_visit": "2024-01-10",
    "diagnosis": ["Type 2 Diabetes"],
    ...
  }
}
```

### Benefits of This Architecture

1. **Immediate Response**: Upload returns immediately, improving user experience
2. **Scalability**: Background worker can process jobs independently
3. **Resilience**: Failed jobs are automatically retried (configurable)
4. **Observability**: Detailed job status available at any time
5. **Decoupling**: Parsing logic separated from HTTP request/response
6. **Webhook Support**: Clients can be notified asynchronously of completion
7. **Multi-tenant Safe**: Each job scoped to tenant with blob storage isolation
8. **Error Handling**: Comprehensive error tracking and retry logic

### Migration Notes

If migrating from the old synchronous system:

1. **Old endpoints** that did synchronous parsing no longer available
2. **New workflow** requires polling job status or using webhooks
3. **Database**: Ensure `parsing_jobs` collection exists (auto-created on first write)
4. **Blob Storage**: Must be configured for file uploads
5. **Background Worker**: Starts automatically on app startup
6. **Worker Logs**: Check server logs to verify worker is running

### Troubleshooting

**Worker not processing jobs?**
- Check logs for worker startup messages
- Verify MongoDB connectivity
- Confirm Azure blob storage is configured
- Check `BLOB_UPLOAD_TIMEOUT` setting

**Jobs stuck in PENDING?**
- Verify background worker is running (check app logs)
- Check MongoDB for connection issues
- Verify `PARSING_INTERVAL_SECONDS` configuration
- Check worker logs for errors

**Webhook not being sent?**
- Verify webhook_url was provided in upload request
- Check worker logs for webhook errors
- Confirm webhook endpoint is accessible from server
- Check webhook_meta.status in job document

**Files not downloading from blob?**
- Verify Azure storage connection string is correct
- Check blob URLs are valid
- Verify tenant_id matches blob path
- Check blob storage permissions

### Performance Tuning

Adjust worker parameters in `server/workers/parsing_worker.py`:

```python
# Process jobs more frequently
POLLING_INTERVAL_SECONDS = 60  # Instead of 120

# Process more jobs per cycle
BATCH_SIZE = 20  # Instead of 10

# Allow more retries
MAX_RETRIES = 5  # Instead of 3

# Longer webhook timeout for slow endpoints
WEBHOOK_TIMEOUT_SECONDS = 30.0  # Instead of 10.0
```

### Future Enhancements

1. **Priority Queue**: Process high-priority jobs first
2. **Dead Letter Queue**: Store permanently failed jobs separately
3. **Metrics/Monitoring**: Track parsing performance, success rates
4. **Batch Processing**: Process multiple reports as single job
5. **Scheduled Processing**: Run worker on specific times
6. **Rate Limiting**: Limit AI model API calls based on quota
7. **Caching**: Cache parsing results to reduce API calls
