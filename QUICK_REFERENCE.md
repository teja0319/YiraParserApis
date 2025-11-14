# Quick Reference: Asynchronous Parsing API

## Upload Report

### Endpoint
```
POST /tenants/{tenant_id}/projects/{project_id}/reports
```

### Parameters
- **tenant_id** (path): Tenant identifier
- **project_id** (path): Project identifier
- **file** (form, required): PDF file(s) or ZIP containing PDFs
- **webhook_url** (query, optional): Callback URL for completion notification

### Example
```bash
curl -X POST "http://localhost:8090/api/v1/tenants/tenant-001/projects/project-001/reports" \
  -F "file=@report.pdf" \
  -H "X-API-Key: your-api-key" \
  -G --data-urlencode "webhook_url=https://webhook.example.com/parsing"
```

### Response (Success)
```json
{
  "success": true,
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "pending",
  "message": "Report upload successful. Parsing will begin shortly.",
  "files_uploaded": 1,
  "total_size_mb": 2.5,
  "webhook_url": "https://webhook.example.com/parsing"
}
```

### Response (Error)
```json
{
  "detail": "Project 'invalid-project' not found for tenant 'tenant-001'"
}
```

### Status Codes
- **200**: Upload successful, job queued
- **400**: Invalid file format or no PDFs found
- **403**: Project or tenant not active
- **404**: Project or tenant not found
- **422**: Project has no AI model assigned
- **503**: Azure storage not configured

---

## Get Job Status

### Endpoint
```
GET /job/status/{job_id}
```

### Parameters
- **job_id** (path): Job identifier from upload response

### Example
```bash
curl -X GET "http://localhost:8090/api/v1/job/status/507f1f77bcf86cd799439011" \
  -H "X-API-Key: your-api-key"
```

### Response (Pending)
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "pending",
  "message": "Parsing in progress",
  "created_at": 1704830400.0
}
```

### Response (Processing)
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "processing",
  "message": "Parsing in progress",
  "created_at": 1704830400.0,
  "started_at": 1704830402.1
}
```

### Response (Completed)
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
    "lab_results": [...],
    "imaging_findings": [...],
    "recommendations": [...],
    "photo_comparison": {...}
  },
  "webhook_status": {
    "delivered": true,
    "status": "success",
    "attempts": 1,
    "last_attempt_at": 1704830448.0
  }
}
```

### Response (Failed)
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "failed",
  "message": "Failed after 3 retries: Connection timeout",
  "created_at": 1704830400.0,
  "started_at": 1704830402.1,
  "completed_at": 1704830550.0,
  "retry_count": 3,
  "max_retries": 3,
  "last_error": "Connection timeout when parsing PDF"
}
```

### Response (Not Found)
```json
{
  "detail": "Job 'invalid-id' not found."
}
```

### Status Codes
- **200**: Status retrieved successfully
- **404**: Job not found
- **500**: Server error

---

## Webhook Callback

### When Sent
Automatically sent when job completes (if webhook_url provided in upload request)

### Method & Headers
```
POST {webhook_url}
Content-Type: application/json
```

### Payload (Success)
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
    "medications": [...],
    ...
  }
}
```

### Payload (Failure)
```json
{
  "job_id": "507f1f77bcf86cd799439011",
  "tenant_id": "tenant-001",
  "project_id": "project-001",
  "report_id": "507f1f77bcf86cd799439012",
  "status": "failed",
  "timestamp": "2024-01-13T10:55:30.120000",
  "error": "Failed to parse any files after 3 retries"
}
```

### Expected Response
Your webhook endpoint should return:
```json
{
  "success": true
}
```

HTTP Status: 200-299 for success, other for retry

---

## Polling Strategy Example

### Simple Polling (JavaScript)
```javascript
async function uploadAndPoll(file) {
  // Step 1: Upload
  const formData = new FormData();
  formData.append('file', file);
  
  const uploadRes = await fetch(
    `/api/v1/tenants/${tenantId}/projects/${projectId}/reports` +
    `?webhook_url=${encodeURIComponent(webhookUrl)}`,
    {
      method: 'POST',
      headers: {'X-API-Key': apiKey},
      body: formData
    }
  );
  
  const uploadData = await uploadRes.json();
  const jobId = uploadData.job_id;
  
  // Step 2: Poll status
  let result;
  let attempts = 0;
  const maxAttempts = 300; // 5 minutes at 1-second intervals
  
  while (attempts < maxAttempts) {
    const statusRes = await fetch(
      `/api/v1/job/status/${jobId}`,
      {headers: {'X-API-Key': apiKey}}
    );
    
    result = await statusRes.json();
    
    if (result.status === 'completed') {
      console.log('Success!', result.parsed_data);
      return result;
    } else if (result.status === 'failed') {
      console.error('Job failed:', result.message);
      throw new Error(result.message);
    }
    
    // Wait before next poll
    await new Promise(r => setTimeout(r, 1000));
    attempts++;
  }
  
  throw new Error('Polling timeout');
}
```

### With Exponential Backoff
```python
import asyncio
import aiohttp
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(multiplier=1, min=2, max=60), 
       stop=stop_after_attempt(30))
async def check_job_status(session, job_id):
    async with session.get(
        f"http://api/v1/job/status/{job_id}",
        headers={"X-API-Key": api_key}
    ) as resp:
        return await resp.json()

async def upload_and_wait(file_path):
    async with aiohttp.ClientSession() as session:
        # Upload
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename='report.pdf')
            
            async with session.post(
                f"http://api/v1/tenants/{tenant_id}/projects/{project_id}/reports",
                data=data,
                headers={"X-API-Key": api_key}
            ) as resp:
                upload = await resp.json()
        
        # Poll with exponential backoff
        job_id = upload['job_id']
        
        while True:
            result = await check_job_status(session, job_id)
            
            if result['status'] == 'completed':
                return result['parsed_data']
            elif result['status'] == 'failed':
                raise Exception(f"Job failed: {result['message']}")
```

---

## Common Issues & Solutions

### "Project not found" Error
**Cause**: Invalid project_id or tenant_id
**Solution**: Verify project exists in database for the tenant

### "Project has no AI model assigned" Error
**Cause**: Project doesn't have an AI model configured
**Solution**: Contact support to assign model to project (contact@yira.ai)

### Job Stuck in "pending" State
**Cause**: Background worker not running
**Solution**: Check server logs for "Parsing worker started" message

### "Azure storage is not configured" Error
**Cause**: Azure blob storage not set up
**Solution**: Configure AZURE_STORAGE_CONNECTION_STRING environment variable

### Webhook Not Received
**Cause**: Multiple possibilities
**Solution**: 
1. Verify webhook_url was valid in upload request
2. Ensure webhook endpoint is publicly accessible
3. Check firewall/networking
4. Look at server logs for webhook errors

---

## Rate Limits

Currently no rate limits enforced, but keep in mind:
- Upload endpoint: Can handle multiple concurrent uploads
- Status checks: Lightweight, safe to poll frequently
- Webhook callbacks: One per job completion
- Background worker: Processes 10 jobs per 2-minute cycle

---

## Authentication

All endpoints require:
- **X-API-Key** header: Your API key
- **Tenant-ID** header: Your tenant identifier (optional, derived from auth)

---

## Data Retention

- **Job metadata**: Kept in MongoDB indefinitely
- **Files**: Kept in blob storage per your Azure retention policy
- **Parsed results**: Stored with job indefinitely
- **Webhooks**: Not stored, only delivery status tracked

---

## Performance Tips

1. **Use webhooks** for large-scale automation (don't poll)
2. **Poll sparingly** - checking every 5-10 seconds is fine
3. **Reuse upload files** - let the system consolidate them
4. **Monitor job status** in your dashboard for insights
5. **Set reasonable webhook timeout** on your server

---

## Support

For issues:
1. Check `ASYNC_PARSING_ARCHITECTURE.md` for details
2. Check `MIGRATION_GUIDE.md` for examples
3. Review server logs (should show worker activity)
4. Contact support: contact@yira.ai
