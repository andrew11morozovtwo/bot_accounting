#!/usr/bin/env python3
"""Database migration script to update assets table schema."""
import sys
import os

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.db import get_db_engine, get_session, Category
from src.config import Config
import sqlite3


def check_column_exists(cursor, table_name, column_name):
    """Check if column exists in table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate_assets_table():
    """Migrate assets table from category (string) to category_id (FK)."""
    db_path = Config.DB_PATH
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if migration is needed
        has_old_column = check_column_exists(cursor, "assets", "category")
        has_new_column = check_column_exists(cursor, "assets", "category_id")
        
        if has_new_column:
            print("✓ Migration already completed. Table has category_id column.")
            return
        
        if not has_old_column:
            print("✓ No migration needed. Table doesn't have old category column.")
            return
        
        print("Migration needed: converting category (string) to category_id (FK)")
        
        # Step 1: Create new table with correct schema
        print("Step 1: Creating new assets table...")
        cursor.execute("""
            CREATE TABLE assets_new (
                id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                category_id INTEGER,
                code VARCHAR(100),
                owner_user_id INTEGER,
                qty FLOAT NOT NULL DEFAULT 0.0,
                price FLOAT,
                state VARCHAR(50) NOT NULL DEFAULT 'in_stock',
                created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
                updated_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
                PRIMARY KEY (id),
                FOREIGN KEY(category_id) REFERENCES categories (id),
                FOREIGN KEY(owner_user_id) REFERENCES users (id),
                UNIQUE (code)
            )
        """)
        
        # Step 2: Get all categories to map names to IDs
        print("Step 2: Mapping category names to IDs...")
        session = get_session()
        try:
            categories = session.query(Category).all()
            category_map = {cat.name: cat.id for cat in categories}
            print(f"  Found {len(category_map)} categories: {list(category_map.keys())}")
        finally:
            session.close()
        
        # Step 3: Copy data from old table to new table
        print("Step 3: Copying data from old table...")
        cursor.execute("SELECT * FROM assets")
        old_assets = cursor.fetchall()
        
        # Get column names from old table
        cursor.execute("PRAGMA table_info(assets)")
        old_columns = [row[1] for row in cursor.fetchall()]
        
        migrated_count = 0
        skipped_count = 0
        
        for old_row in old_assets:
            asset_dict = dict(zip(old_columns, old_row))
            
            # Map category name to category_id
            category_id = None
            if asset_dict.get('category'):
                category_name = asset_dict['category']
                category_id = category_map.get(category_name)
                if not category_id:
                    print(f"  Warning: Category '{category_name}' not found, setting to NULL")
            
            # Insert into new table
            cursor.execute("""
                INSERT INTO assets_new (
                    id, name, category_id, code, owner_user_id, qty, price, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_dict['id'],
                asset_dict['name'],
                category_id,
                asset_dict.get('code'),
                asset_dict.get('owner_user_id'),
                asset_dict.get('qty', 0.0),
                asset_dict.get('price'),
                asset_dict.get('state', 'in_stock'),
                asset_dict.get('created_at'),
                asset_dict.get('updated_at')
            ))
            migrated_count += 1
        
        print(f"  Migrated {migrated_count} assets")
        
        # Step 4: Drop old table
        print("Step 4: Dropping old table...")
        cursor.execute("DROP TABLE assets")
        
        # Step 5: Rename new table
        print("Step 5: Renaming new table...")
        cursor.execute("ALTER TABLE assets_new RENAME TO assets")
        
        # Step 6: Recreate indexes
        print("Step 6: Recreating indexes...")
        cursor.execute("CREATE INDEX ix_assets_code ON assets (code)")
        if check_column_exists(cursor, "assets", "category_id"):
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_assets_category_id ON assets (category_id)")
        
        # Commit changes
        conn.commit()
        print("✓ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


def main():
    """Main function."""
    print("=" * 80)
    print("DATABASE MIGRATION")
    print("=" * 80)
    
    try:
        migrate_assets_table()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
