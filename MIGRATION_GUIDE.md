# Migration Guide: From Synchronous to Asynchronous Parsing

This guide explains how to migrate from the old synchronous parsing architecture to the new asynchronous job-based system.

## Key Differences

| Aspect | Old (Synchronous) | New (Asynchronous) |
|--------|------------------|-------------------|
| **Upload Behavior** | Blocks until parsing complete (3-5 mins) | Returns immediately (< 100ms) |
| **Response Time** | Long wait for parsed results | Instant job ID returned |
| **Server Load** | HTTP connection held during parsing | Connection closed immediately |
| **File Storage** | Kept in request | Uploaded to blob storage |
| **Status Checking** | Not available | Full status via GET endpoint |
| **Webhooks** | Not supported | Callback on completion |
| **Error Handling** | Immediate error response | Retry logic with max attempts |
| **Scalability** | Limited (HTTP connections) | High (independent workers) |

## API Changes

### Upload Endpoint

#### Old Request
```bash
curl -X POST "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports" \
  -F "file=@report.pdf" \
  -H "X-API-Key: your-key"
```

#### Old Response (after 3-5 minutes)
```json
{
  "success": true,
  "parsed_data": {
    "patient_name": "...",
    "diagnosis": [...],
    ...
  }
}
```

#### New Request (same)
```bash
curl -X POST "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports" \
  -F "file=@report.pdf" \
  -H "X-API-Key: your-key" \
  -G --data-urlencode "webhook_url=https://webhook.example.com/reports"
```

#### New Response (immediate)
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

### New Status Endpoint

To get results, use the new status endpoint with the returned `job_id`:

```bash
curl -X GET "http://localhost:8090/api/v1/job/status/507f1f77bcf86cd799439011" \
  -H "X-API-Key: your-key"
```

Response (when pending):
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "status": "pending",
  "message": "Parsing in progress"
}
```

Response (when complete):
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "status": "completed",
  "parsed_data": {
    "patient_name": "...",
    "diagnosis": [...],
    ...
  }
}
```

## Client Migration Strategies

### Option 1: Polling (Simple)

Poll the status endpoint until job is complete:

```python
import time
import requests

# Upload report
response = requests.post(
    f"http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports",
    files={"file": open("report.pdf", "rb")},
    headers={"X-API-Key": "your-key"}
)

job_id = response.json()["job_id"]

# Poll status
while True:
    status = requests.get(
        f"http://localhost:8090/api/v1/job/status/{job_id}",
        headers={"X-API-Key": "your-key"}
    ).json()
    
    if status["status"] == "completed":
        parsed_data = status["parsed_data"]
        print(f"Success! Parsed data: {parsed_data}")
        break
    elif status["status"] == "failed":
        print(f"Error: {status['message']}")
        break
    else:
        print(f"Status: {status['status']}")
        time.sleep(5)  # Check every 5 seconds
```

### Option 2: Webhooks (Recommended)

Use webhooks for real-time notifications:

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhooks/parsing")
async def parsing_webhook(request: Request):
    """Receive parsing completion notification"""
    data = await request.json()
    
    job_id = data["job_id"]
    status = data["status"]
    
    if status == "completed":
        parsed_data = data["parsed_data"]
        print(f"Parsing complete! Data: {parsed_data}")
        # Process parsed data
    elif status == "failed":
        print(f"Parsing failed: {data.get('error', 'Unknown error')}")
        # Handle failure
    
    return {"success": True}
```

Then when uploading, provide the webhook URL:

```bash
curl -X POST "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports" \
  -F "file=@report.pdf" \
  -H "X-API-Key: your-key" \
  -G --data-urlencode "webhook_url=https://yourapp.com/webhooks/parsing"
```

### Option 3: Async/Await (Python)

```python
import asyncio
import aiohttp

async def upload_and_wait(file_path):
    """Upload report and wait for completion"""
    async with aiohttp.ClientSession() as session:
        # Upload
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename="report.pdf")
            
            async with session.post(
                "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports",
                data=data,
                headers={"X-API-Key": "your-key"}
            ) as resp:
                upload_result = await resp.json()
                job_id = upload_result["job_id"]
        
        # Poll until complete
        while True:
            async with session.get(
                f"http://localhost:8090/api/v1/job/status/{job_id}",
                headers={"X-API-Key": "your-key"}
            ) as resp:
                status = await resp.json()
            
            if status["status"] == "completed":
                return status["parsed_data"]
            elif status["status"] == "failed":
                raise Exception(f"Job failed: {status['message']}")
            
            await asyncio.sleep(2)

# Usage
result = asyncio.run(upload_and_wait("report.pdf"))
```

## Database Migration

The system now uses a new `parsing_jobs` collection. No migration needed—it's created automatically on first use.

### Keeping Old Reports

Old reports are still in the `parsed_reports` collection. You can:

1. **Keep both**: Old reports stay in `parsed_reports`, new ones use the job system
2. **Migrate old data**: Write a script to import old results into new schema
3. **Archive old data**: Back up `parsed_reports` and leave unchanged

### Collection Reference

- **`parsing_jobs`**: New collection for asynchronous job tracking
- **`parsed_reports`**: Original collection (now unused but preserved)
- **`projects`**, **`tenants`**, **`ai_models`**: Unchanged

## Configuration Requirements

### Azure Blob Storage

Must be fully configured for file uploads:

```env
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_CONTAINER_NAME=medical-reports
```

### MongoDB

Ensure these collections exist (auto-created):
- `parsing_jobs` - Job queue and status tracking
- `parsed_reports` - (Optional) Store full parsed results

## Deployment Steps

1. **Back up MongoDB**: In case you need to rollback
   ```bash
   mongodump --uri="mongodb://localhost:27017/medical_report_parser"
   ```

2. **Deploy code changes**: Update to new version

3. **Verify worker is running**: Check logs for "Parsing worker started"
   ```
   INFO: Parsing worker started
   ```

4. **Test upload endpoint**: Verify you get immediate response with job_id

5. **Test status endpoint**: Verify status can be queried

6. **Test webhook**: If using webhooks, verify callbacks are received

## Troubleshooting Migration Issues

### Old Clients Getting Timeout

**Issue**: Clients expecting synchronous response get timeout
**Solution**: Update client to use job_id polling or webhooks

### Worker Not Starting

**Issue**: App starts but worker not processing jobs
**Solution**: 
- Check logs for "Parsing worker started" message
- Verify MongoDB connection
- Check Azure storage configuration
- Verify Gemini API key is set

### Jobs Stuck in Pending

**Issue**: Jobs created but never processed
**Solution**:
- Check worker is running (look for polling logs)
- Verify `POLLING_INTERVAL_SECONDS` is reasonable (default 120)
- Check for errors in worker logs

### Webhook Not Received

**Issue**: Job completes but webhook not called
**Solution**:
- Verify webhook_url was provided in upload request
- Ensure webhook endpoint is publicly accessible
- Check firewall/networking
- Look for webhook errors in server logs

## Rollback Plan

If you need to rollback:

1. **Deploy previous code version**
2. **Old API endpoints** will still work (if you didn't remove them)
3. **New jobs** will be stuck in `parsing_jobs` collection
4. **Options**:
   - Let them be (harmless)
   - Archive the collection
   - Delete and retry with old system

## Performance Expectations

### Old System
- Upload: 3-5 minutes (includes parsing)
- Response time: Single request blocks entire time

### New System
- Upload: < 100ms (just file upload + job creation)
- Status checks: < 50ms
- Parsing happens independently (configurable 2-minute cycle)
- Total time: Same as before, but distributed

### Scaling
- Old: Limited by HTTP connections (blocking)
- New: Scales with worker capacity (10 jobs/cycle configurable)

## Questions & Answers

**Q: What happens if server restarts during parsing?**
A: Job status stays in MongoDB. Worker resumes processing on startup.

**Q: Can I have multiple workers?**
A: Current design supports single worker. Multi-worker support coming soon.

**Q: What's the maximum retry count?**
A: Configurable, defaults to 3 retries before marking failed.

**Q: Can I override the polling interval?**
A: Yes, modify `POLLING_INTERVAL_SECONDS` in `server/workers/parsing_worker.py`

**Q: Are old synchronous endpoints still available?**
A: No, they've been removed. Use the new asynchronous API.

**Q: Can I get results without webhooks?**
A: Yes, poll the status endpoint. Webhooks are optional.

**Q: Is webhook delivery guaranteed?**
A: Webhooks are retried, but not guaranteed. Use status endpoint for critical data.

**Q: What format is the parsed_data in webhook payload?**
A: Same format as status endpoint response.
