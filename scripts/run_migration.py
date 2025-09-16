#!/usr/bin/env python3
"""
Run Alembic migrations on Cloud SQL
"""
import os
import sys
import subprocess
from sqlalchemy import create_engine, text

def run_migration():
    """Run Alembic migrations"""
    
    # Get database connection details from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return False
    
    try:
        # Test database connection
        print("Testing database connection...")
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"Connected to: {version}")
        
        # Run Alembic migrations
        print("Running Alembic migrations...")
        result = subprocess.run([
            'alembic', 'upgrade', 'head'
        ], capture_output=True, text=True, cwd=os.getcwd())
        
        if result.returncode == 0:
            print("Migrations completed successfully!")
            print("STDOUT:", result.stdout)
            return True
        else:
            print("Migration failed!")
            print("STDERR:", result.stderr)
            print("STDOUT:", result.stdout)
            return False
            
    except Exception as e:
        print(f"ERROR: Failed to run migrations: {e}")
        return False

if __name__ == "__main__":
    # Set DATABASE_URL from command line argument if provided
    if len(sys.argv) > 1:
        os.environ['DATABASE_URL'] = sys.argv[1]
    
    success = run_migration()
    sys.exit(0 if success else 1)
