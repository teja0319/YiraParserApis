"""
Migration script to move data from local storage (JSON) to MongoDB.
Run this once to migrate existing tenants and usage data.

Usage:
    python -m scripts.migrate_to_mongodb
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.config.settings import get_settings
from server.integrations.mongodb import MongoDBClient
from server.models.tenant import tenant_manager
from server.utils.usage_tracker import usage_tracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_data():
    """
    Migrate data from local JSON files to MongoDB.
    """
    try:
        db = await MongoDBClient.get_database()
        
        logger.info("Starting migration to MongoDB...")
        
        # 1. Migrate tenants
        logger.info("Migrating tenants...")
        tenants_collection = db["tenants"]
        
        tenants = tenant_manager.list_all_tenants()
        for tenant_id, tenant in tenants.items():
            tenant_doc = tenant.dict()
            tenant_doc["_id"] = tenant_id
            
            await tenants_collection.update_one(
                {"_id": tenant_id},
                {"$set": tenant_doc},
                upsert=True
            )
            logger.info(f"  Migrated tenant: {tenant_id}")
        
        logger.info(f"Successfully migrated {len(tenants)} tenants")
        
        # 2. Initialize collections with default documents if needed
        logger.info("Initializing project collections...")
        projects_collection = db["projects"]
        ai_models_collection = db["ai_models"]
        analytics_collection = db["analytics"]
        
        # Create indexes
        logger.info("Creating MongoDB indexes...")
        await projects_collection.create_index([("tenant_id", 1)])
        await projects_collection.create_index([("tenant_id", 1), ("project_id", 1)], unique=True)
        
        await ai_models_collection.create_index([("tenant_id", 1)])
        await ai_models_collection.create_index([("model_id", 1)], unique=True)
        
        await analytics_collection.create_index([("tenant_id", 1)])
        await analytics_collection.create_index([("project_id", 1)])
        
        logger.info("MongoDB indexes created successfully")
        
        logger.info("Migration completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Verify data in MongoDB")
        logger.info("2. Create AI Models using the /api/v1/admin/ai-models/tenants/{tenant_id} endpoint")
        logger.info("3. Create Projects using the /api/v1/tenants/{tenant_id}/projects endpoint")
        logger.info("4. Update parser API calls to use project_id instead of model parameter")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(migrate_data())
