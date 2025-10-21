#!/usr/bin/env python3
"""
Database migration script to add missing columns (rendered_text, grammar) to the sentences table.
This fixes the BinderException when trying to query these columns from older database versions.
"""

import click
import duckdb
import shutil
from pathlib import Path


def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    result = conn.execute(
        """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = ? AND column_name = ?
        """,
        [table_name, column_name]
    ).fetchone()
    return result[0] > 0


def migrate_sentences_table(conn):
    """Add missing columns to sentences table if they don't exist."""
    # Check and add rendered_text column
    if not check_column_exists(conn, 'sentences', 'rendered_text'):
        click.echo("Adding 'rendered_text' column to sentences table...")
        conn.execute("""
            ALTER TABLE sentences 
            ADD COLUMN rendered_text VARCHAR
        """)
        # Copy ja_text to rendered_text as initial value
        conn.execute("""
            UPDATE sentences 
            SET rendered_text = ja_text
            WHERE rendered_text IS NULL
        """)
        click.echo("✓ Added 'rendered_text' column")
    else:
        click.echo("✓ 'rendered_text' column already exists")

    # Check and add grammar column
    if not check_column_exists(conn, 'sentences', 'grammar'):
        click.echo("Adding 'grammar' column to sentences table...")
        conn.execute("""
            ALTER TABLE sentences 
            ADD COLUMN grammar VARCHAR
        """)
        click.echo("✓ Added 'grammar' column")
    else:
        click.echo("✓ 'grammar' column already exists")


def verify_schema(conn):
    """Verify that all required columns exist."""
    required_columns = [
        'id', 'user_id', 'hash', 'ja_text', 'en_text', 'cn_text',
        'reading', 'explanation', 'rendered_text', 'grammar',
        'created_at', 'last_reviewed', 'review_count', 'ease_factor',
        'interval_days', 'next_review', 'last_played', 'play_count'
    ]
    
    click.echo("\nVerifying schema...")
    missing_columns = []
    
    for col in required_columns:
        if not check_column_exists(conn, 'sentences', col):
            missing_columns.append(col)
    
    if missing_columns:
        click.echo(f"❌ Missing columns: {', '.join(missing_columns)}", err=True)
        return False
    else:
        click.echo("✓ All required columns are present")
        return True


@click.command()
@click.option('-i', '--input', 'input_db', required=True, type=click.Path(exists=True),
              help='Path to the input (old) database file')
@click.option('-o', '--output', 'output_db', required=True, type=click.Path(),
              help='Path to the output (new) database file')
@click.option('--force', is_flag=True, help='Overwrite output file if it exists')
def migrate(input_db, output_db, force):
    """Migrate old database schema to new schema with rendered_text and grammar columns."""
    
    # Check if output file exists
    output_path = Path(output_db)
    if output_path.exists() and not force:
        click.echo(f"Error: Output file '{output_db}' already exists. Use --force to overwrite.", err=True)
        return 1
    
    # Create a copy of the input database
    click.echo(f"Copying database from '{input_db}' to '{output_db}'...")
    shutil.copy2(input_db, output_db)
    click.echo("✓ Database copied")
    
    # Connect to the copied database
    try:
        conn = duckdb.connect(output_db)
        
        # Check if sentences table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        
        if 'sentences' not in table_names:
            click.echo("Error: 'sentences' table not found in database", err=True)
            conn.close()
            return 1
        
        # Perform migration
        click.echo("\nStarting migration...")
        migrate_sentences_table(conn)
        
        # Verify the schema
        if verify_schema(conn):
            click.echo("\n✅ Migration completed successfully!")
            
            # Show some statistics
            count = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
            click.echo(f"\nDatabase statistics:")
            click.echo(f"  Total sentences: {count}")
            
            # Count sentences that might have grammar patterns
            with_patterns = conn.execute("""
                SELECT COUNT(*) FROM sentences 
                WHERE rendered_text LIKE '%{{%}}%'
            """).fetchone()[0]
            click.echo(f"  Sentences with grammar patterns: {with_patterns}")
        else:
            click.echo("\n❌ Migration failed - schema verification failed", err=True)
            conn.close()
            return 1
        
        conn.close()
        
    except Exception as e:
        click.echo(f"\nError during migration: {str(e)}", err=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(migrate())