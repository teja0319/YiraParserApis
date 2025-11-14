"""
MongoDB integration for data persistence.
Provides database connection and collection managers.
"""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

from server.config.settings import get_settings

logger = logging.getLogger(__name__)


class MongoDBClient:
    """MongoDB client wrapper for async operations."""
    
    _instance: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def get_client(cls) -> AsyncIOMotorClient:
        """Get or create MongoDB client."""
        if cls._instance is None:
            settings = get_settings()
            cls._instance = AsyncIOMotorClient(settings.mongodb_url)
            logger.info("MongoDB client initialized")
        return cls._instance
    
    @classmethod
    async def get_database(cls) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if cls._db is None:
            settings = get_settings()
            client = await cls.get_client()
            cls._db = client[settings.mongodb_database]
            logger.info(f"Connected to MongoDB database: {settings.mongodb_database}")
            
            # Create indexes
            await cls._create_indexes()
        
        return cls._db
    
    @classmethod
    async def _create_indexes(cls):
        """Create required database indexes."""
        db = cls._db
        
        try:
            # Projects collection indexes
            projects = db["projects"]
            await projects.create_index([("tenant_id", ASCENDING)])
            await projects.create_index([("tenant_id", ASCENDING), ("project_id", ASCENDING)], unique=True)
            await projects.create_index([("created_at", DESCENDING)])
            logger.info("Created indexes for projects collection")
            
            # AI Models collection indexes
            ai_models = db["ai_models"]
            await ai_models.create_index([("tenant_id", ASCENDING)])
            await ai_models.create_index([("model_id", ASCENDING)], unique=True)
            await ai_models.create_index([("created_at", DESCENDING)])
            logger.info("Created indexes for ai_models collection")
            
            # Analytics collection indexes
            analytics = db["analytics"]
            await analytics.create_index([("tenant_id", ASCENDING)])
            await analytics.create_index([("project_id", ASCENDING)])
            await analytics.create_index([("timestamp", DESCENDING)])
            logger.info("Created indexes for analytics collection")
            
            # Parsing jobs collection indexes
            parsing_jobs = db["parsing_jobs"]
            await parsing_jobs.create_index([("tenant_id", ASCENDING)])
            await parsing_jobs.create_index([("status", ASCENDING)])
            await parsing_jobs.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
            await parsing_jobs.create_index([("created_at", DESCENDING)])
            await parsing_jobs.create_index([("retry_count", ASCENDING)])
            logger.info("Created indexes for parsing_jobs collection")
            
            # Parsed reports collection indexes
            parsed_reports = db["parsed_reports"]
            await parsed_reports.create_index([("tenant_id", ASCENDING)])
            await parsed_reports.create_index([("project_id", ASCENDING)])
            await parsed_reports.create_index([("job_id", ASCENDING)])
            await parsed_reports.create_index([("created_at", DESCENDING)])
            logger.info("Created indexes for parsed_reports collection")
            
        except OperationFailure as e:
            logger.warning(f"Index creation warning (may already exist): {e}")
    
    @classmethod
    async def close(cls):
        """Close MongoDB connection."""
        if cls._instance:
            cls._instance.close()
            cls._instance = None
            cls._db = None
            logger.info("MongoDB connection closed")
