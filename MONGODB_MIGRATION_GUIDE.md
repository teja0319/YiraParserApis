# MongoDB Migration Guide

This guide explains the major changes made to the Medical Report Parser API to support MongoDB data storage and a project-based architecture.

## Overview of Changes

### 1. **Storage Migration: Local Storage → MongoDB**
- **Previous**: Tenant data stored in `/server/data/tenants.json`
- **Now**: All data (tenants, projects, AI models, analytics) stored in MongoDB
- **Why**: Better scalability, atomicity, and support for complex queries
- **Azure Blob Storage**: PDF files continue to be stored in Azure Blob Storage (unchanged)

### 2. **New Data Model: Tenant → Projects → AI Models**

\`\`\`
Tenant (e.g., "hospital-xyz")
├── Project 1 (e.g., "Cardiology Lab")
│   ├── AI Model (e.g., "Gemini Pro with Custom Config")
│   └── Reports (uploaded PDFs)
├── Project 2 (e.g., "Radiology Lab")
│   ├── AI Model (e.g., "Gemini Flash for Speed")
│   └── Reports (uploaded PDFs)
└── Project 3 (e.g., "General Practice")
    ├── AI Model
    └── Reports
\`\`\`

### 3. **AI Models Management**
New CRUD API for managing AI models at the tenant level:

\`\`\`python
POST   /api/v1/admin/ai-models/tenants/{tenant_id}          # Create
GET    /api/v1/admin/ai-models/tenants/{tenant_id}          # List all
GET    /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}  # Get one
PATCH  /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}  # Update
DELETE /api/v1/admin/ai-models/tenants/{tenant_id}/{model_id}  # Delete
\`\`\`

**AI Model Fields:**
- `model_id`: Unique identifier (auto-generated UUID)
- `model_name`: Display name (e.g., "Gemini 2.5 Pro")
- `cost_per_page`: Cost in USD (e.g., 0.05)
- `description`: Optional description
- `provider`: AI provider (currently "gemini")
- `status`: active | deprecated | archived
- `created_at`, `updated_at`: Timestamps

### 4. **Projects Management**
Full CRUD for projects under each tenant:

\`\`\`python
POST   /api/v1/tenants/{tenant_id}/projects                 # Create
GET    /api/v1/tenants/{tenant_id}/projects                 # List
GET    /api/v1/tenants/{tenant_id}/projects/{project_id}    # Get one
PATCH  /api/v1/tenants/{tenant_id}/projects/{project_id}    # Update
DELETE /api/v1/tenants/{tenant_id}/projects/{project_id}    # Delete
POST   /api/v1/tenants/{tenant_id}/projects/{project_id}/assign-model  # Assign AI Model
\`\`\`

**Project Fields:**
- `project_id`: Unique identifier (auto-generated UUID)
- `project_name`: Display name
- `description`: Optional description
- `ai_model_id`: Reference to assigned AI Model
- `is_active`: Boolean status
- `metadata`: Custom key-value pairs
- `created_at`, `updated_at`: Timestamps

### 5. **Parser API Changes**
The medical report parsing endpoint now uses projects:

**Before:**
\`\`\`bash
POST /api/v1/tenants/{tenant_id}/reports
  ?model=gemini-2.5-pro
  (file upload)
\`\`\`

**Now:**
\`\`\`bash
POST /api/v1/tenants/{tenant_id}/projects/{project_id}/reports
  (file upload)
\`\`\`

**What Changed:**
- `model` query parameter removed
- `project_id` path parameter added
- AI model is automatically retrieved from project configuration
- Request body stays the same (just upload the PDF)

**Example Request:**
\`\`\`bash
curl -X POST \
  "http://localhost:8090/api/v1/tenants/hospital-xyz/projects/cardio-lab/reports" \
  -H "X-API-Key: sk_hospital_xyz_xxxxx" \
  -F "file=@report.pdf"
\`\`\`

**Response Now Includes:**
\`\`\`json
{
  "success": true,
  "tenant_id": "hospital-xyz",
  "project_id": "cardio-lab-uuid",
  "ai_model_id": "gemini-pro-uuid",
  "model_used": "gemini-2.5-pro",
  "parsing_time_seconds": 12.5,
  "confidence_score": 85,
  "parsed_data": { ... }
}
\`\`\`

### 6. **Analytics Endpoints**
New comprehensive analytics for tracking usage and costs:

\`\`\`python
GET /api/v1/analytics/tenants/{tenant_id}/projects/{project_id}/summary
GET /api/v1/analytics/tenants/{tenant_id}/summary
GET /api/v1/analytics/admin/tenants/{tenant_id}/detailed  # Admin only
\`\`\`

**Project-Level Analytics:**
- Total uploads
- Total pages processed
- Total cost (based on AI model's cost_per_page)
- Average parsing time
- Success rate

**Tenant-Level Analytics:**
- All metrics aggregated across all projects
- Breakdown by project
- Cost attribution per project

## Setup Instructions

### 1. **Install Dependencies**
\`\`\`bash
pip install -r requirements.txt
\`\`\`

The new `pymongo` and `motor` packages are already added to requirements.txt.

### 2. **Configure MongoDB**
Set environment variables:

\`\`\`bash
# .env file
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=medical_report_parser

# Or use MongoDB Atlas
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true
MONGODB_DATABASE=medical_report_parser
\`\`\`

### 3. **Run Migration Script**
\`\`\`bash
python -m scripts.migrate_to_mongodb
\`\`\`

This script:
- Connects to MongoDB
- Migrates existing tenants from JSON
- Creates necessary indexes
- Initializes collections

### 4. **Verify Migration**
\`\`\`bash
# Check tenants were migrated
curl -H "X-Admin-Key: your-admin-key" \
  http://localhost:8090/api/v1/admin/tenants
\`\`\`

## Workflow Examples

### Example 1: Setting Up a New Tenant with Projects

\`\`\`bash
# 1. Create tenant (admin)
curl -X POST \
  -H "X-Admin-Key: sk_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "City Medical Center",
    "email": "admin@citymedical.com",
    "quota_max_uploads_per_month": 500
  }' \
  http://localhost:8090/api/v1/admin/tenants

# Response includes tenant_id and api_key
# tenant_id = "city-medical-center-a1b2"
# api_key = "sk_city_medical_center_a1b2_xyz..."

# 2. Create AI models for the tenant (admin)
curl -X POST \
  -H "X-Admin-Key: sk_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "Gemini 2.5 Pro",
    "cost_per_page": 0.05,
    "description": "High accuracy model for complex reports",
    "provider": "gemini"
  }' \
  http://localhost:8090/api/v1/admin/ai-models/tenants/city-medical-center-a1b2

# Response includes model_id
# model_id = "550e8400-e29b-41d4-a716-446655440000"

# 3. Create project for the tenant
curl -X POST \
  -H "X-API-Key: sk_city_medical_center_a1b2_xyz..." \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Cardiology Department",
    "description": "Reports from cardiac patients",
    "ai_model_id": "550e8400-e29b-41d4-a716-446655440000"
  }' \
  http://localhost:8090/api/v1/tenants/city-medical-center-a1b2/projects

# Response includes project_id
# project_id = "660f9401-f40c-51e5-b827-557766551111"

# 4. Upload reports to project
curl -X POST \
  -H "X-API-Key: sk_city_medical_center_a1b2_xyz..." \
  -F "file=@cardiac_report.pdf" \
  http://localhost:8090/api/v1/tenants/city-medical-center-a1b2/projects/660f9401-f40c-51e5-b827-557766551111/reports

# 5. View project analytics
curl \
  -H "X-API-Key: sk_city_medical_center_a1b2_xyz..." \
  http://localhost:8090/api/v1/analytics/tenants/city-medical-center-a1b2/projects/660f9401-f40c-51e5-b827-557766551111/summary
\`\`\`

### Example 2: Switching AI Models for a Project

\`\`\`bash
# Create a new faster AI model
curl -X POST \
  -H "X-Admin-Key: sk_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "Gemini 2.5 Flash",
    "cost_per_page": 0.02,
    "description": "Fast model for routine reports"
  }' \
  http://localhost:8090/api/v1/admin/ai-models/tenants/city-medical-center-a1b2

# Assign the new model to the project
curl -X POST \
  -H "X-API-Key: sk_city_medical_center_a1b2_xyz..." \
  -H "Content-Type: application/json" \
  -d '{"ai_model_id": "new-model-id"}' \
  http://localhost:8090/api/v1/tenants/city-medical-center-a1b2/projects/660f9401-f40c-51e5-b827-557766551111/assign-model

# Future uploads will use the new model
\`\`\`

### Example 3: Getting Tenant-Level Analytics

\`\`\`bash
# Tenant-level summary
curl \
  -H "X-API-Key: sk_city_medical_center_a1b2_xyz..." \
  http://localhost:8090/api/v1/analytics/tenants/city-medical-center-a1b2/summary

# Response includes:
# - Total projects (3)
# - Active projects (2)
# - Total uploads across all projects (150)
# - Total pages processed (3,250)
# - Total cost ($162.50)
# - Breakdown by project
\`\`\`

## Database Schema

### Collections

**ai_models**
\`\`\`javascript
{
  model_id: "uuid",
  tenant_id: "tenant-id",
  model_name: "Gemini 2.5 Pro",
  cost_per_page: 0.05,
  description: "...",
  provider: "gemini",
  status: "active",
  created_at: ISODate(),
  updated_at: ISODate()
}
\`\`\`

**projects**
\`\`\`javascript
{
  project_id: "uuid",
  tenant_id: "tenant-id",
  project_name: "Cardiology Lab",
  description: "...",
  ai_model_id: "model-uuid",
  is_active: true,
  metadata: {},
  created_at: ISODate(),
  updated_at: ISODate()
}
\`\`\`

**analytics**
\`\`\`javascript
{
  project_id: "uuid",
  tenant_id: "tenant-id",
  timestamp: ISODate(),
  uploads_count: 10,
  total_pages_processed: 250,
  total_cost_usd: 12.50,
  average_parsing_time_seconds: 15.3,
  success_rate: 95.0
}
\`\`\`

**tenants** (migrated from JSON)
\`\`\`javascript
{
  _id: "tenant-id",
  tenant_id: "tenant-id",
  name: "City Medical Center",
  email: "admin@...",
  api_key: "sk_...",
  created_at: "2024-01-01T...",
  active: true,
  quota: {
    max_uploads_per_month: 500,
    max_storage_mb: 10000
  }
}
\`\`\`

## Environment Variables

Add these to your `.env` file:

\`\`\`bash
# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=medical_report_parser

# Existing variables remain unchanged
GEMINI_API_KEY=your-key
AZURE_STORAGE_CONNECTION_STRING=your-connection-string
ADMIN_API_KEY=your-admin-key
\`\`\`

## Key Benefits

1. **Scalability**: MongoDB handles large-scale deployments better than JSON files
2. **Atomicity**: Multi-document transactions ensure data consistency
3. **Flexibility**: Projects allow different teams/departments to use different AI models
4. **Cost Attribution**: Cost per page tracking enables accurate billing per project
5. **Analytics**: Comprehensive analytics at project and tenant levels
6. **Performance**: Indexed queries are much faster than file-based lookups

## Migration Checklist

- [ ] Install pymongo and motor dependencies
- [ ] Configure MONGODB_URL and MONGODB_DATABASE environment variables
- [ ] Start MongoDB server (local or cloud)
- [ ] Run migration script: `python -m scripts.migrate_to_mongodb`
- [ ] Verify tenants migrated: `GET /api/v1/admin/tenants`
- [ ] Create AI models for each tenant
- [ ] Create projects and assign AI models
- [ ] Update client code to use new `/tenants/{tenant_id}/projects/{project_id}/reports` endpoint
- [ ] Test report uploads with new endpoint
- [ ] Monitor analytics dashboard

## Troubleshooting

**MongoDB Connection Error**
\`\`\`
pymongo.errors.ServerSelectionTimeoutError
\`\`\`
- Verify MONGODB_URL is correct
- Ensure MongoDB server is running
- Check network connectivity

**Indexes Not Created**
- Run migration script again: `python -m scripts.migrate_to_mongodb`
- Check logs for any errors

**Projects Not Found**
- Verify `project_id` is correct
- Ensure project belongs to the authenticated tenant
- Check authorization headers (X-API-Key)

## Support

For issues or questions:
1. Check logs: `docker logs medical-report-parser`
2. Review API documentation: `http://localhost:8090/docs`
3. Verify MongoDB connection in admin panel
