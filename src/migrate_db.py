#!/usr/bin/env python3
"""
Database migration script
Adds service_id and office_id columns to appointment_logs table
"""

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate_database(db_path: str = "bot_data.db"):
    """Apply database migrations"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(appointment_logs)")
        columns = [row[1] for row in cursor.fetchall()]

        migrations_applied = []

        if "service_id" not in columns:
            logger.info("Adding service_id column to appointment_logs...")
            cursor.execute("ALTER TABLE appointment_logs ADD COLUMN service_id INTEGER")
            migrations_applied.append("service_id")

        if "office_id" not in columns:
            logger.info("Adding office_id column to appointment_logs...")
            cursor.execute("ALTER TABLE appointment_logs ADD COLUMN office_id INTEGER")
            migrations_applied.append("office_id")

        if migrations_applied:
            conn.commit()
            logger.info(
                f"✅ Migration complete! Added columns: {', '.join(migrations_applied)}"
            )
        else:
            logger.info("✅ Database already up to date, no migrations needed")

        # Show updated schema
        cursor.execute("PRAGMA table_info(appointment_logs)")
        logger.info("\nCurrent appointment_logs schema:")
        for row in cursor.fetchall():
            logger.info(f"  - {row[1]} ({row[2]})")

        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    # Setup basic logging for script execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    db_file = sys.argv[1] if len(sys.argv) > 1 else "bot_data.db"

    if not Path(db_file).exists():
        logger.error(f"❌ Database file not found: {db_file}")
        sys.exit(1)

    success = migrate_database(db_file)
    sys.exit(0 if success else 1)
