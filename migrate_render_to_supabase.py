#!/usr/bin/env python3
"""
Migrate data from Render PostgreSQL to Supabase
Run this script on Render Web Service where Render DB is accessible
"""

import sys
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Source: Render PostgreSQL (Internal URL)
RENDER_URL = "postgresql://runbot:MMJntms3At5ydvbRcyv1x3l5Yq8dgSUR@dpg-d5maq1f5r7bs73d13c30-a/runbot_tp8c"

# Target: Supabase PostgreSQL
SUPABASE_URL = "postgresql://postgres.dapbbiuzazcxogxitbrg:yuGeh2czvOgLaHjK@aws-1-eu-north-1.pooler.supabase.com:5432/postgres"

def test_connections():
    """Test both database connections"""
    logger.info("=" * 60)
    logger.info("TESTING DATABASE CONNECTIONS")
    logger.info("=" * 60)

    logger.info("\n1️⃣ Testing Render connection...")
    try:
        render_engine = create_engine(RENDER_URL, echo=False)
        with render_engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            logger.info(f"✅ Render: {version[:60]}")
    except Exception as e:
        logger.error(f"❌ Render connection failed: {e}")
        return False

    logger.info("\n2️⃣ Testing Supabase connection...")
    try:
        supabase_engine = create_engine(SUPABASE_URL, echo=False)
        with supabase_engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            logger.info(f"✅ Supabase: {version[:60]}")
    except Exception as e:
        logger.error(f"❌ Supabase connection failed: {e}")
        return False

    return True

def get_tables(engine):
    """Get all table names"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        return [row[0] for row in result]

def copy_table(source_engine, target_engine, table_name):
    """Copy all data from source table to target table"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Copying table: {table_name}")
    logger.info(f"{'='*60}")

    try:
        # Get row count from source
        with source_engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = result.fetchone()[0]

        if row_count == 0:
            logger.info(f"  ⏭️  Table {table_name} is empty, skipping")
            return True

        logger.info(f"  📊 Found {row_count} rows")

        # Get all data
        with source_engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM {table_name}"))
            columns = result.keys()
            rows = result.fetchall()

        # Clear target table
        with target_engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
            conn.commit()
        logger.info(f"  🧹 Cleared target table")

        # Insert data in batches
        batch_size = 100
        total_inserted = 0

        with target_engine.connect() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]

                for row in batch:
                    # Build INSERT statement
                    col_names = ', '.join(columns)
                    placeholders = ', '.join([f":{col}" for col in columns])
                    insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

                    row_dict = dict(zip(columns, row))
                    conn.execute(text(insert_sql), row_dict)

                total_inserted += len(batch)
                logger.info(f"  📝 Inserted {total_inserted}/{row_count} rows...")

            conn.commit()

        logger.info(f"  ✅ Successfully copied {total_inserted} rows")
        return True

    except Exception as e:
        logger.error(f"  ❌ Failed to copy {table_name}: {e}")
        return False

def migrate():
    """Main migration function"""
    logger.info("\n" + "=" * 60)
    logger.info("DATABASE MIGRATION: Render → Supabase")
    logger.info("=" * 60)

    # Test connections
    if not test_connections():
        logger.error("\n❌ Connection test failed. Aborting.")
        sys.exit(1)

    # Create engines
    render_engine = create_engine(RENDER_URL, echo=False)
    supabase_engine = create_engine(SUPABASE_URL, echo=False)

    # Get tables
    logger.info("\n" + "=" * 60)
    logger.info("SCANNING TABLES")
    logger.info("=" * 60)

    render_tables = get_tables(render_engine)
    supabase_tables = get_tables(supabase_engine)

    logger.info(f"\n📦 Render tables ({len(render_tables)}): {', '.join(render_tables)}")
    logger.info(f"📦 Supabase tables ({len(supabase_tables)}): {', '.join(supabase_tables)}")

    # Find tables to migrate
    tables_to_migrate = [t for t in render_tables if t in supabase_tables]

    if not tables_to_migrate:
        logger.warning("\n⚠️  No common tables found!")
        return

    logger.info(f"\n🎯 Will migrate {len(tables_to_migrate)} tables: {', '.join(tables_to_migrate)}")

    # Confirm migration
    logger.info("\n" + "=" * 60)
    logger.info("⚠️  WARNING: This will OVERWRITE data in Supabase!")
    logger.info("=" * 60)

    # Migrate each table
    success_count = 0
    fail_count = 0

    for table in tables_to_migrate:
        if copy_table(render_engine, supabase_engine, table):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"✅ Successfully migrated: {success_count} tables")
    logger.info(f"❌ Failed: {fail_count} tables")

    if fail_count == 0:
        logger.info("\n🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        logger.info("\nNext steps:")
        logger.info("1. Update DATABASE_URL in Render Environment to Supabase URL")
        logger.info("2. Redeploy the bot")
        logger.info("\nSupabase URL:")
        logger.info(SUPABASE_URL)
    else:
        logger.error("\n⚠️  MIGRATION COMPLETED WITH ERRORS")
        sys.exit(1)

if __name__ == "__main__":
    try:
        migrate()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
