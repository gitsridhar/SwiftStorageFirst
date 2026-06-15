#!/usr/bin/env python3
"""
OpenStack Swift Server Implementation with SQLite Backend
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, Response
import os

app = Flask(__name__)

# Database configuration
DB_PATH = 'swift_storage.db'


class SwiftStorage:
    """SQLite-backed storage for Swift objects"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create accounts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                container_count INTEGER DEFAULT 0,
                object_count INTEGER DEFAULT 0,
                bytes_used INTEGER DEFAULT 0
            )
        ''')
        
        # Create containers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS containers (
                container_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                container_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                object_count INTEGER DEFAULT 0,
                bytes_used INTEGER DEFAULT 0,
                UNIQUE(account_id, container_name),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id)
            )
        ''')
        
        # Create objects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS objects (
                object_id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id INTEGER NOT NULL,
                object_name TEXT NOT NULL,
                content_type TEXT,
                content_length INTEGER,
                etag TEXT,
                data BLOB,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(container_id, object_name),
                FOREIGN KEY (container_id) REFERENCES containers(container_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def create_account(self, account_id):
        """Create or update account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO accounts (account_id) VALUES (?)
        ''', (account_id,))
        conn.commit()
        conn.close()
    
    def create_container(self, account_id, container_name):
        """Create a container"""
        self.create_account(account_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO containers (account_id, container_name)
                VALUES (?, ?)
            ''', (account_id, container_name))
            
            # Update account container count
            cursor.execute('''
                UPDATE accounts SET container_count = container_count + 1
                WHERE account_id = ?
            ''', (account_id,))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_container_id(self, account_id, container_name):
        """Get container ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT container_id FROM containers
            WHERE account_id = ? AND container_name = ?
        ''', (account_id, container_name))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def put_object(self, account_id, container_name, object_name, data, content_type, metadata=None):
        """Store an object"""
        container_id = self.get_container_id(account_id, container_name)
        if not container_id:
            return None
        
        # Calculate ETag (MD5 hash)
        etag = hashlib.md5(data).hexdigest()
        content_length = len(data)
        metadata_json = json.dumps(metadata) if metadata else None
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if object exists
            cursor.execute('''
                SELECT object_id, content_length FROM objects
                WHERE container_id = ? AND object_name = ?
            ''', (container_id, object_name))
            existing = cursor.fetchone()
            
            if existing:
                old_size = existing[1]
                # Update existing object
                cursor.execute('''
                    UPDATE objects
                    SET data = ?, content_type = ?, content_length = ?,
                        etag = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE container_id = ? AND object_name = ?
                ''', (data, content_type, content_length, etag, metadata_json,
                      container_id, object_name))
                
                # Update container and account bytes
                size_diff = content_length - old_size
                cursor.execute('''
                    UPDATE containers SET bytes_used = bytes_used + ?
                    WHERE container_id = ?
                ''', (size_diff, container_id))
                cursor.execute('''
                    UPDATE accounts SET bytes_used = bytes_used + ?
                    WHERE account_id = ?
                ''', (size_diff, account_id))
            else:
                # Insert new object
                cursor.execute('''
                    INSERT INTO objects (container_id, object_name, data,
                                       content_type, content_length, etag, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (container_id, object_name, data, content_type,
                      content_length, etag, metadata_json))
                
                # Update container and account stats
                cursor.execute('''
                    UPDATE containers
                    SET object_count = object_count + 1,
                        bytes_used = bytes_used + ?
                    WHERE container_id = ?
                ''', (content_length, container_id))
                cursor.execute('''
                    UPDATE accounts
                    SET object_count = object_count + 1,
                        bytes_used = bytes_used + ?
                    WHERE account_id = ?
                ''', (content_length, account_id))
            
            conn.commit()
            return etag
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_object(self, account_id, container_name, object_name):
        """Retrieve an object"""
        container_id = self.get_container_id(account_id, container_name)
        if not container_id:
            return None
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT data, content_type, content_length, etag, metadata
            FROM objects
            WHERE container_id = ? AND object_name = ?
        ''', (container_id, object_name))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'data': result[0],
                'content_type': result[1],
                'content_length': result[2],
                'etag': result[3],
                'metadata': json.loads(result[4]) if result[4] else {}
            }
        return None
    
    def list_containers(self, account_id):
        """List containers in an account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT container_name, object_count, bytes_used
            FROM containers
            WHERE account_id = ?
            ORDER BY container_name
        ''', (account_id,))
        results = cursor.fetchall()
        conn.close()
        
        return [{'name': r[0], 'count': r[1], 'bytes': r[2]} for r in results]
    
    def list_objects(self, account_id, container_name):
        """List objects in a container"""
        container_id = self.get_container_id(account_id, container_name)
        if not container_id:
            return []
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT object_name, content_length, content_type, etag, updated_at
            FROM objects
            WHERE container_id = ?
            ORDER BY object_name
        ''', (container_id,))
        results = cursor.fetchall()
        conn.close()
        
        return [{
            'name': r[0],
            'bytes': r[1],
            'content_type': r[2],
            'hash': r[3],
            'last_modified': r[4]
        } for r in results]


# Initialize storage
storage = SwiftStorage(DB_PATH)


# API Routes

@app.route('/v1/<account_id>', methods=['GET'])
def list_account_containers(account_id):
    """List containers in account"""
    containers = storage.list_containers(account_id)
    return jsonify(containers), 200


@app.route('/v1/<account_id>/<container_name>', methods=['PUT'])
def create_container(account_id, container_name):
    """Create a container"""
    success = storage.create_container(account_id, container_name)
    if success:
        return '', 201
    else:
        return '', 202  # Already exists


@app.route('/v1/<account_id>/<container_name>', methods=['GET'])
def list_container_objects(account_id, container_name):
    """List objects in container"""
    objects = storage.list_objects(account_id, container_name)
    if objects is not None:
        return jsonify(objects), 200
    else:
        return jsonify({'error': 'Container not found'}), 404


@app.route('/v1/<account_id>/<container_name>/<path:object_name>', methods=['PUT'])
def put_object(account_id, container_name, object_name):
    """Upload an object"""
    data = request.get_data()
    content_type = request.headers.get('Content-Type', 'application/octet-stream')
    
    # Extract custom metadata from headers
    metadata = {}
    for key, value in request.headers.items():
        if key.lower().startswith('x-object-meta-'):
            meta_key = key[14:]  # Remove 'X-Object-Meta-' prefix
            metadata[meta_key] = value
    
    try:
        etag = storage.put_object(account_id, container_name, object_name,
                                 data, content_type, metadata)
        if etag:
            return '', 201, {'ETag': etag}
        else:
            return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/v1/<account_id>/<container_name>/<path:object_name>', methods=['GET'])
def get_object(account_id, container_name, object_name):
    """Download an object"""
    obj = storage.get_object(account_id, container_name, object_name)
    
    if obj:
        headers = {
            'Content-Type': obj['content_type'],
            'Content-Length': obj['content_length'],
            'ETag': obj['etag']
        }
        
        # Add custom metadata to response headers
        for key, value in obj['metadata'].items():
            headers[f'X-Object-Meta-{key}'] = value
        
        return Response(obj['data'], headers=headers)
    else:
        return jsonify({'error': 'Object not found'}), 404


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    print("Starting Swift Server on http://localhost:8080")
    print(f"Database: {DB_PATH}")
    app.run(host='0.0.0.0', port=8080, debug=True)

# Made with Bob
