"""
Database connection and session management
"""

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import os
from typing import Generator
from contextlib import contextmanager

from src.models.models import Base

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and sessions"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        # Configure engine based on database type
        if self.database_url.startswith('postgresql'):
            # PostgreSQL configuration
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False
            )
        else:
            # SQLite configuration (for local testing)
            self.engine = create_engine(
                self.database_url,
                future=True,
                connect_args={"check_same_thread": False}
            )
        
        self.SessionLocal = sessionmaker(
            autocommit=False, 
            autoflush=False, 
            bind=self.engine
        )
        # Initialize database schema (create tables if not exists)
        try:
            self.init_database()
        except Exception as e:
            logger.warning(f"Init database failed: {e}")
    
    def init_database(self):
        """Initialize database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
            # Optionally run startup migrations if configured
            self.run_startup_migrations()
        except SQLAlchemyError as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around operations"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session_generator(self) -> Generator[Session, None, None]:
        """Get database session generator for FastAPI dependency injection"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            with self.engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def _apply_sql_script(self, script_path: str) -> None:
        """Apply a SQL migration script that may contain multiple statements."""
        import os
        if not os.path.exists(script_path):
            logger.warning(f"Migration script not found: {script_path}")
            return
        with open(script_path, 'r') as f:
            content = f.read()
        # Split by semicolon; ignore empty statements
        statements = [s.strip() for s in content.split(';') if s.strip()]
        if not statements:
            return
        with self.engine.connect() as conn:
            trans = conn.begin()
            try:
                for stmt in statements:
                    conn.execute(text(stmt))
                trans.commit()
            except Exception as e:
                trans.rollback()
                logger.error(f"Migration script failed: {script_path} -> {e}")
                raise

    def run_startup_migrations(self) -> None:
        """Run startup migrations automatically if enabled via env var."""
        run = os.getenv('AUTO_MIGRATE_ON_START', 'false').lower()
        if run not in ('1', 'true', 'yes'):
            return
        logger.info("Running startup migrations (AUTO_MIGRATE_ON_START is enabled)")
        import os
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
        challenge_script = os.path.join(script_dir, 'migrate_cascade_challenge_registrations.sql')
        event_script = os.path.join(script_dir, 'migrate_cascade_event_registrations.sql')
        try:
            self._apply_sql_script(challenge_script)
            self._apply_sql_script(event_script)
            logger.info("Startup migrations completed successfully")
        except Exception as e:
            logger.error(f"Startup migrations failed: {e}")

# Global database manager instance
db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get global database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager

def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session"""
    db_manager = get_db_manager()
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()
