# MongoDB Collections and Relationships

## Collections Overview

This document provides a complete reference of all MongoDB collections, their fields, indexes, and relationships.

---

## 1. **tenants** Collection

**Purpose**: Stores tenant information (hospitals/clinics)

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "tenant_id": "hosp_001",
  "name": "City Hospital",
  "email": "admin@cityhospital.com",
  "api_key": "sk_live_abc123xyz",
  "created_at": ISODate("2024-01-15T10:00:00Z"),
  "active": true,
  "quota": {
    "max_uploads_per_month": 1000,
    "max_storage_mb": 5000
  }
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `tenant_id` | String | Unique tenant identifier |
| `name` | String | Display name of tenant |
| `email` | String | Contact email |
| `api_key` | String | API authentication key |
| `created_at` | ISODate | Creation timestamp |
| `active` | Boolean | Tenant status |
| `quota.max_uploads_per_month` | Integer | Monthly upload limit |
| `quota.max_storage_mb` | Integer | Storage limit in MB |

### Indexes
- `tenant_id` (Unique)
- `api_key` (Unique)
- `email`
- `active`

### Relationships
- **Parent**: None (root collection)
- **Children**: `projects`, `ai_models`

---

## 2. **projects** Collection

**Purpose**: Stores projects within tenants

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "project_id": "proj_2024_001",
  "tenant_id": "hosp_001",
  "project_name": "Emergency Department - Phase 1",
  "description": "Emergency reports parsing project",
  "ai_model_id": "model_gemini_001",
  "is_active": true,
  "created_at": ISODate("2024-01-15T10:30:00Z"),
  "updated_at": ISODate("2024-01-20T15:45:00Z"),
  "metadata": {
    "department": "emergency",
    "priority": "high",
    "region": "north"
  }
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `project_id` | String | Unique project identifier |
| `tenant_id` | String | **FK to tenants.tenant_id** |
| `project_name` | String | Display name |
| `description` | String | Project description |
| `ai_model_id` | String | **FK to ai_models.model_id** |
| `is_active` | Boolean | Project active status |
| `created_at` | ISODate | Creation timestamp |
| `updated_at` | ISODate | Last update timestamp |
| `metadata` | Object | Custom key-value data |

### Indexes
- `project_id` (Unique)
- `tenant_id` (Compound: for querying all projects of a tenant)
- `tenant_id, ai_model_id` (Compound: for tenant + model queries)
- `is_active`

### Relationships
- **Parent**: `tenants` (via `tenant_id`)
- **Related**: `ai_models` (via `ai_model_id`)
- **Children**: `reports` (project-level documents)

### Constraints
- Each project must belong to exactly one tenant
- Each project must be associated with exactly one AI model
- A project's `tenant_id` must exist in the `tenants` collection
- A project's `ai_model_id` must exist in the `ai_models` collection

---

## 3. **ai_models** Collection

**Purpose**: Stores AI model configurations and pricing

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "model_id": "model_gemini_001",
  "tenant_id": "hosp_001",
  "model_name": "Gemini Pro Vision",
  "cost_per_page": 0.05,
  "description": "Advanced medical report parsing",
  "provider": "gemini",
  "status": "active",
  "created_at": ISODate("2024-01-10T08:00:00Z"),
  "updated_at": ISODate("2024-01-20T14:20:00Z")
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `model_id` | String | Unique model identifier |
| `tenant_id` | String | **FK to tenants.tenant_id** |
| `model_name` | String | Display name of model |
| `cost_per_page` | Float | USD cost per page |
| `description` | String | Model description |
| `provider` | String | AI provider (gemini, openai, etc) |
| `status` | String | Status: active, deprecated, archived |
| `created_at` | ISODate | Creation timestamp |
| `updated_at` | ISODate | Last update timestamp |

### Indexes
- `model_id` (Unique)
- `tenant_id` (for querying tenant's models)
- `tenant_id, status` (Compound: active models per tenant)
- `provider`

### Relationships
- **Parent**: `tenants` (via `tenant_id`)
- **Reverse Foreign Keys**: `projects` (multiple projects can use one model)

### Constraints
- Each AI model belongs to exactly one tenant
- A model's `tenant_id` must exist in the `tenants` collection
- Models can be shared by multiple projects within the same tenant

---

## 4. **reports** Collection

**Purpose**: Stores parsed medical reports

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "report_id": "rpt_2024_001",
  "tenant_id": "hosp_001",
  "project_id": "proj_2024_001",
  "ai_model_id": "model_gemini_001",
  "file_name": "patient_report_001.pdf",
  "blob_url": "https://medicalblobaccount.blob.core.windows.net/reports/rpt_2024_001.pdf",
  "pages_count": 5,
  "parsing_status": "completed",
  "parsed_data": {
    "patient_name": "John Doe",
    "date_of_admission": "2024-01-15",
    "diagnosis": "Pneumonia"
  },
  "cost_usd": 0.25,
  "parsing_time_seconds": 12.5,
  "created_at": ISODate("2024-01-20T15:45:00Z"),
  "updated_at": ISODate("2024-01-20T15:45:30Z")
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `report_id` | String | Unique report identifier |
| `tenant_id` | String | **FK to tenants.tenant_id** |
| `project_id` | String | **FK to projects.project_id** |
| `ai_model_id` | String | **FK to ai_models.model_id** |
| `file_name` | String | Original PDF filename |
| `blob_url` | String | Azure Blob Storage URL |
| `pages_count` | Integer | Number of pages |
| `parsing_status` | String | Status: pending, processing, completed, failed |
| `parsed_data` | Object | Extracted report data |
| `cost_usd` | Float | Cost incurred |
| `parsing_time_seconds` | Float | Processing duration |
| `created_at` | ISODate | Upload timestamp |
| `updated_at` | ISODate | Last update timestamp |

### Indexes
- `report_id` (Unique)
- `tenant_id` (for tenant's reports)
- `project_id` (for project's reports)
- `tenant_id, project_id` (Compound)
- `parsing_status`
- `created_at` (for time-series queries)

### Relationships
- **Parent**: `tenants` (via `tenant_id`)
- **Parent**: `projects` (via `project_id`)
- **Related**: `ai_models` (via `ai_model_id`)

### Constraints
- `tenant_id` must exist in `tenants` collection
- `project_id` must exist in `projects` collection
- `ai_model_id` must exist in `ai_models` collection
- Project's `tenant_id` must match report's `tenant_id`

---

## 5. **project_analytics** Collection

**Purpose**: Stores aggregated project-level analytics

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "project_id": "proj_2024_001",
  "tenant_id": "hosp_001",
  "timestamp": ISODate("2024-01-20T23:59:59Z"),
  "uploads_count": 150,
  "total_pages_processed": 450,
  "total_cost_usd": 22.50,
  "average_parsing_time_seconds": 10.2,
  "success_rate": 98.5
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `project_id` | String | **FK to projects.project_id** |
| `tenant_id` | String | **FK to tenants.tenant_id** |
| `timestamp` | ISODate | Aggregation timestamp |
| `uploads_count` | Integer | Number of uploads |
| `total_pages_processed` | Integer | Total pages parsed |
| `total_cost_usd` | Float | Total cost incurred |
| `average_parsing_time_seconds` | Float | Average parsing duration |
| `success_rate` | Float | Percentage of successful parses |

### Indexes
- `project_id` (Unique with timestamp)
- `tenant_id`
- `timestamp` (TTL index for data retention)

### Relationships
- **Parent**: `projects` (via `project_id`)
- **Parent**: `tenants` (via `tenant_id`)

---

## 6. **tenant_analytics** Collection

**Purpose**: Stores aggregated tenant-level analytics

### Document Structure
\`\`\`json
{
  "_id": ObjectId("..."),
  "tenant_id": "hosp_001",
  "timestamp": ISODate("2024-01-20T23:59:59Z"),
  "total_projects": 5,
  "total_uploads": 750,
  "total_pages_processed": 2250,
  "total_cost_usd": 112.50,
  "active_projects": 4
}
\`\`\`

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB internal ID |
| `tenant_id` | String | **FK to tenants.tenant_id** |
| `timestamp` | ISODate | Aggregation timestamp |
| `total_projects` | Integer | Total projects in tenant |
| `total_uploads` | Integer | Uploads across all projects |
| `total_pages_processed` | Integer | Pages across all projects |
| `total_cost_usd` | Float | Total cost across all projects |
| `active_projects` | Integer | Number of active projects |

### Indexes
- `tenant_id` (Unique with timestamp)
- `timestamp` (TTL index)

### Relationships
- **Parent**: `tenants` (via `tenant_id`)

---

## Data Relationships Diagram

\`\`\`
┌─────────────────┐
│    TENANTS      │
│  (tenant_id)    │
└────────┬────────┘
         │
    ┌────┴─────────────────────────┐
    │                              │
    │                              │
    ▼                              ▼
┌──────────────────┐      ┌─────────────────┐
│   PROJECTS       │      │   AI_MODELS     │
│ (project_id) ◄──┼──────┤ (model_id)      │
│ (tenant_id) ─┐  │      │ (tenant_id) ─┐  │
│(ai_model_id) ┤  │      │              │  │
└──────┬───────┘  │      └──────────────┘  │
       │          │                        │
       │ ◄────────┘                        │
       │                                   │
       ▼                                   │
┌──────────────────┐                       │
│    REPORTS       │                       │
│  (report_id)     │                       │
│  (tenant_id) ────┼───────────────────────┤
│  (project_id) ───┘                       │
│  (ai_model_id) ◄─────────────────────────┘
└────────┬─────────────────────────────────┘
         │
    ┌────┴──────────────────────────┐
    │                               │
    ▼                               ▼
┌──────────────────┐      ┌──────────────────────┐
│PROJECT_ANALYTICS │      │ TENANT_ANALYTICS     │
│ (project_id) ◄───┘      │  (tenant_id) ◄──────┘
│ (tenant_id)
└──────────────────┘
\`\`\`

---

## Query Examples

### Find all projects in a tenant
\`\`\`javascript
db.projects.find({ tenant_id: "hosp_001" })
\`\`\`

### Find all AI models for a tenant
\`\`\`javascript
db.ai_models.find({ tenant_id: "hosp_001", status: "active" })
\`\`\`

### Find reports for a specific project
\`\`\`javascript
db.reports.find({ project_id: "proj_2024_001", parsing_status: "completed" })
\`\`\`

### Get project analytics
\`\`\`javascript
db.project_analytics.findOne({ project_id: "proj_2024_001" }, { sort: { timestamp: -1 } })
\`\`\`

### Get all reports with their project and AI model info
\`\`\`javascript
db.reports.aggregate([
  { $match: { tenant_id: "hosp_001" } },
  { $lookup: { from: "projects", localField: "project_id", foreignField: "project_id", as: "project" } },
  { $lookup: { from: "ai_models", localField: "ai_model_id", foreignField: "model_id", as: "model" } },
  { $unwind: "$project" },
  { $unwind: "$model" }
])
\`\`\`

### Calculate tenant-level costs
\`\`\`javascript
db.reports.aggregate([
  { $match: { tenant_id: "hosp_001" } },
  { $group: { _id: "$tenant_id", total_cost: { $sum: "$cost_usd" }, count: { $sum: 1 } } }
])
\`\`\`

---

## Data Integrity Constraints

### Foreign Key Constraints (Application Level)

1. **Reports → Tenants**: `report.tenant_id` must exist in `tenants.tenant_id`
2. **Reports → Projects**: `report.project_id` must exist in `projects.project_id`
3. **Reports → AI Models**: `report.ai_model_id` must exist in `ai_models.model_id`
4. **Projects → Tenants**: `project.tenant_id` must exist in `tenants.tenant_id`
5. **Projects → AI Models**: `project.ai_model_id` must exist in `ai_models.model_id`
6. **AI Models → Tenants**: `ai_model.tenant_id` must exist in `tenants.tenant_id`
7. **Project Analytics → Projects**: `project_analytics.project_id` must exist
8. **Tenant Analytics → Tenants**: `tenant_analytics.tenant_id` must exist

### Business Logic Constraints

1. A project can only have reports from its own tenant
2. A project's AI model must belong to the same tenant
3. Only active AI models can be assigned to new projects
4. Tenant quotas cannot be exceeded (enforced by application)

---

## Indexes Summary

| Collection | Index | Type | Reason |
|-----------|-------|------|--------|
| tenants | tenant_id | Unique | Identifier lookup |
| tenants | api_key | Unique | Authentication |
| projects | project_id | Unique | Identifier lookup |
| projects | tenant_id | Single | Filter by tenant |
| projects | tenant_id, ai_model_id | Compound | Complex queries |
| ai_models | model_id | Unique | Identifier lookup |
| ai_models | tenant_id, status | Compound | Active models per tenant |
| reports | report_id | Unique | Identifier lookup |
| reports | tenant_id, project_id | Compound | Multi-level filtering |
| reports | parsing_status | Single | Status queries |
| reports | created_at | Single | Time-based queries |
| project_analytics | project_id, timestamp | Unique | Latest analytics |
| tenant_analytics | tenant_id, timestamp | Unique | Latest analytics |

---

## Migration Notes

- **Azure Blob Storage**: Stores PDF files only (no change)
- **MongoDB**: Stores all metadata, configuration, and aggregated analytics
- **Local Storage**: No longer used; all data now in MongoDB
- **Performance**: Indexes enable fast queries even with large datasets
