# API Endpoints Reference

Complete reference of all API endpoints after MongoDB migration.

## Authentication
All endpoints require one of:
- `X-API-Key: sk_<tenant-id>_<token>` - Tenant API key
- `Authorization: Bearer <jwt-token>` - JWT token (if configured)
- Admin endpoints require: `X-Admin-Key: <admin-key>`

## Tenant Management (Admin)

### Create Tenant
\`\`\`
POST /api/v1/admin/tenants
Headers: X-Admin-Key
Body: {
  "name": "Hospital Name",
  "email": "admin@hospital.com",
  "quota_max_uploads_per_month": 100,
  "quota_max_storage_mb": 1000
}
\`\`\`

### List Tenants
\`\`\`
GET /api/v1/admin/tenants
Headers: X-Admin-Key
\`\`\`

### Get Tenant
\`\`\`
GET /api/v1/admin/tenants/{tenant_id}
Headers: X-Admin-Key
\`\`\`

### Update Tenant
\`\`\`
PATCH /api/v1/admin/tenants/{tenant_id}
Headers: X-Admin-Key
Body: { "name": "...", "email": "...", "active": true }
\`\`\`

### Delete Tenant
\`\`\`
DELETE /api/v1/admin/tenants/{tenant_id}
Headers: X-Admin-Key
\`\`\`

### Regenerate API Key
\`\`\`
POST /api/v1/admin/tenants/{tenant_id}/regenerate-api-key
Headers: X-Admin-Key
\`\`\`

## AI Models Management (Admin)

### Create AI Model
\`\`\`
POST /api/v1/admin/ai-models/tenants/{tenant_id}
Headers: X-Admin-Key
Body: {
  "model_name": "Gemini 2.5 Pro",
  "cost_per_page": 0.05,
  "description": "High accuracy model",
  "provider": "gemini"
}
\`\`\`

### List AI Models
\`\`\`
GET /api/v1/admin/ai-models/tenants/{tenant_id}
Headers: X-Admin-Key
Query: ?status_filter=active
\`\`\`

### Get AI Model
\`\`\`
GET /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}
Headers: X-Admin-Key
\`\`\`

### Update AI Model
\`\`\`
PATCH /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}
Headers: X-Admin-Key
Body: {
  "model_name": "Updated Name",
  "cost_per_page": 0.06,
  "status": "active"
}
\`\`\`

### Delete AI Model
\`\`\`
DELETE /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}
Headers: X-Admin-Key
\`\`\`

## Projects Management

### Create Project
\`\`\`
POST /api/v1/tenants/{tenant_id}/projects
Headers: X-API-Key
Body: {
  "project_name": "Cardiology Lab",
  "description": "...",
  "ai_model_id": "model-uuid"
}
\`\`\`

### List Projects
\`\`\`
GET /api/v1/tenants/{tenant_id}/projects
Headers: X-API-Key
Query: ?active_only=false
\`\`\`

### Get Project
\`\`\`
GET /api/v1/tenants/{tenant_id}/projects/{project_id}
Headers: X-API-Key
\`\`\`

### Update Project
\`\`\`
PATCH /api/v1/tenants/{tenant_id}/projects/{project_id}
Headers: X-API-Key
Body: {
  "project_name": "...",
  "description": "...",
  "ai_model_id": "...",
  "is_active": true
}
\`\`\`

### Delete Project
\`\`\`
DELETE /api/v1/tenants/{tenant_id}/projects/{project_id}
Headers: X-API-Key
\`\`\`

### Assign AI Model to Project
\`\`\`
POST /api/v1/tenants/{tenant_id}/projects/{project_id}/assign-model
Headers: X-API-Key
Body: { "ai_model_id": "model-uuid" }
\`\`\`

## Medical Reports (Updated)

### Upload Report to Project
\`\`\`
POST /api/v1/tenants/{tenant_id}/projects/{project_id}/reports
Headers: X-API-Key
Files: file=@report.pdf (or multiple files, or ZIP)

Response: {
  "success": true,
  "project_id": "...",
  "ai_model_id": "...",
  "parsing_time_seconds": 12.5,
  "confidence_score": 85,
  "parsed_data": { ... }
}
\`\`\`

### Upload Report (Legacy - Tenant Level)
\`\`\`
POST /api/v1/tenants/{tenant_id}/reports
Headers: X-API-Key
Query: ?model=gemini-2.5-pro (optional)
Files: file=@report.pdf

Note: This endpoint is maintained for backward compatibility.
      Use project-based upload for new code.
\`\`\`

### List Reports
\`\`\`
GET /api/v1/tenants/{tenant_id}/reports
Headers: X-API-Key
Query: ?limit=10&offset=0
\`\`\`

### Get Report
\`\`\`
GET /api/v1/tenants/{tenant_id}/reports/{report_id}
Headers: X-API-Key
\`\`\`

### Delete Report
\`\`\`
DELETE /api/v1/tenants/{tenant_id}/reports/{report_id}
Headers: X-API-Key
\`\`\`

## Usage & Billing

### Get Usage Summary
\`\`\`
GET /api/v1/tenants/{tenant_id}/usage
Headers: X-API-Key
\`\`\`

### Get Monthly Usage
\`\`\`
GET /api/v1/tenants/{tenant_id}/usage/monthly
Headers: X-API-Key
Query: ?month=2024-01
\`\`\`

## Analytics

### Project Analytics
\`\`\`
GET /api/v1/analytics/tenants/{tenant_id}/projects/{project_id}/summary
Headers: X-API-Key

Response: {
  "success": true,
  "project_id": "...",
  "project_name": "...",
  "ai_model": { "model_id": "...", "model_name": "...", "cost_per_page": 0.05 },
  "analytics": {
    "total_uploads": 150,
    "total_pages_processed": 3250,
    "total_cost_usd": 162.50,
    "average_parsing_time_seconds": 15.3,
    "average_success_rate_percent": 95.0
  }
}
\`\`\`

### Tenant Analytics
\`\`\`
GET /api/v1/analytics/tenants/{tenant_id}/summary
Headers: X-API-Key

Response: {
  "success": true,
  "summary": {
    "total_projects": 3,
    "active_projects": 2,
    "total_uploads": 450,
    "total_pages_processed": 9750,
    "total_cost_usd": 487.50,
    ...
  },
  "project_breakdowns": [ ... ]
}
\`\`\`

### Admin Tenant Analytics
\`\`\`
GET /api/v1/analytics/admin/tenants/{tenant_id}/detailed
Headers: X-Admin-Key

Response: {
  "success": true,
  "tenant": { ... },
  "projects": 3,
  "analytics": { ... }
}
\`\`\`

## Health Check

### Health Status
\`\`\`
GET /api/v1/health
\`\`\`

## Error Responses

All errors follow this format:
\`\`\`json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description"
  }
}
\`\`\`

Common error codes:
- `UNAUTHORIZED` (401): Missing or invalid authentication
- `FORBIDDEN` (403): Insufficient permissions
- `NOT_FOUND` (404): Resource not found
- `UNPROCESSABLE_ENTITY` (422): Invalid request data
- `INTERNAL_ERROR` (500): Server error

## Rate Limiting

All tenant endpoints are rate-limited based on quota:
- Default: 120 requests per minute
- Configure via `RATE_LIMIT_PER_MINUTE` environment variable

Rate limit headers:
\`\`\`
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1634567890
\`\`\`
