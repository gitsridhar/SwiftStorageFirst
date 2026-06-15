#!/usr/bin/env python3
"""
OpenStack Swift Client Implementation
"""

import requests
import json
from typing import Optional, Dict, List, Any


class SwiftClient:
    """Simple Swift client for interacting with Swift server"""
    
    def __init__(self, base_url: str, account_id: str):
        """
        Initialize Swift client
        
        Args:
            base_url: Base URL of Swift server (e.g., 'http://localhost:8080')
            account_id: Account identifier
        """
        self.base_url = base_url.rstrip('/')
        self.account_id = account_id
        self.session = requests.Session()
    
    def _get_url(self, *parts):
        """Construct URL from parts"""
        return f"{self.base_url}/v1/{self.account_id}/{'/'.join(str(p) for p in parts)}"
    
    def create_container(self, container_name: str) -> bool:
        """
        Create a container
        
        Args:
            container_name: Name of the container to create
            
        Returns:
            True if created successfully, False otherwise
        """
        url = self._get_url(container_name)
        response = self.session.put(url)
        return response.status_code in [201, 202]
    
    def list_containers(self) -> List[Dict[str, Any]]:
        """
        List all containers in the account
        
        Returns:
            List of container information dictionaries
        """
        url = f"{self.base_url}/v1/{self.account_id}"
        response = self.session.get(url)
        
        if response.status_code == 200:
            return response.json()
        return []
    
    def list_objects(self, container_name: str) -> List[Dict[str, Any]]:
        """
        List objects in a container
        
        Args:
            container_name: Name of the container
            
        Returns:
            List of object information dictionaries
        """
        url = self._get_url(container_name)
        response = self.session.get(url)
        
        if response.status_code == 200:
            return response.json()
        return []
    
    def put_object(self, container_name: str, object_name: str, 
                   data: bytes, content_type: str = 'application/octet-stream',
                   metadata: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Upload an object to a container
        
        Args:
            container_name: Name of the container
            object_name: Name of the object
            data: Object data as bytes
            content_type: MIME type of the object
            metadata: Optional dictionary of custom metadata
            
        Returns:
            ETag of the uploaded object, or None if failed
        """
        url = self._get_url(container_name, object_name)
        headers = {'Content-Type': content_type}
        
        # Add custom metadata to headers
        if metadata:
            for key, value in metadata.items():
                headers[f'X-Object-Meta-{key}'] = str(value)
        
        response = self.session.put(url, data=data, headers=headers)
        
        if response.status_code == 201:
            return response.headers.get('ETag')
        return None
    
    def put_object_from_file(self, container_name: str, object_name: str,
                            file_path: str, content_type: str = 'application/octet-stream',
                            metadata: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Upload a file as an object
        
        Args:
            container_name: Name of the container
            object_name: Name of the object
            file_path: Path to the file to upload
            content_type: MIME type of the object
            metadata: Optional dictionary of custom metadata
            
        Returns:
            ETag of the uploaded object, or None if failed
        """
        with open(file_path, 'rb') as f:
            data = f.read()
        return self.put_object(container_name, object_name, data, content_type, metadata)
    
    def get_object(self, container_name: str, object_name: str) -> Optional[Dict[str, Any]]:
        """
        Download an object from a container
        
        Args:
            container_name: Name of the container
            object_name: Name of the object
            
        Returns:
            Dictionary containing object data and metadata, or None if not found
        """
        url = self._get_url(container_name, object_name)
        response = self.session.get(url)
        
        if response.status_code == 200:
            # Extract metadata from headers
            metadata = {}
            for key, value in response.headers.items():
                if key.lower().startswith('x-object-meta-'):
                    meta_key = key[14:]  # Remove 'X-Object-Meta-' prefix
                    metadata[meta_key] = value
            
            return {
                'data': response.content,
                'content_type': response.headers.get('Content-Type'),
                'content_length': int(response.headers.get('Content-Length', 0)),
                'etag': response.headers.get('ETag'),
                'metadata': metadata
            }
        return None
    
    def get_object_to_file(self, container_name: str, object_name: str,
                          file_path: str) -> bool:
        """
        Download an object and save it to a file
        
        Args:
            container_name: Name of the container
            object_name: Name of the object
            file_path: Path where to save the file
            
        Returns:
            True if successful, False otherwise
        """
        obj = self.get_object(container_name, object_name)
        if obj:
            with open(file_path, 'wb') as f:
                f.write(obj['data'])
            return True
        return False
    
    def health_check(self) -> bool:
        """
        Check if the Swift server is healthy
        
        Returns:
            True if server is healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/health"
            response = self.session.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


# Example usage
if __name__ == '__main__':
    # Initialize client
    client = SwiftClient('http://localhost:8080', 'test_account')
    
    # Check server health
    if client.health_check():
        print("✓ Server is healthy")
    else:
        print("✗ Server is not responding")
        exit(1)
    
    # Create a container
    print("\nCreating container 'test_container'...")
    if client.create_container('test_container'):
        print("✓ Container created")
    
    # Upload some data
    print("\nUploading object 'hello.txt'...")
    test_data = b"Hello, Swift! This is a test object."
    etag = client.put_object('test_container', 'hello.txt', test_data,
                            content_type='text/plain',
                            metadata={'author': 'test_user', 'version': '1.0'})
    if etag:
        print(f"✓ Object uploaded with ETag: {etag}")
    
    # List containers
    print("\nListing containers...")
    containers = client.list_containers()
    for container in containers:
        print(f"  - {container['name']} ({container['count']} objects, {container['bytes']} bytes)")
    
    # List objects in container
    print("\nListing objects in 'test_container'...")
    objects = client.list_objects('test_container')
    for obj in objects:
        print(f"  - {obj['name']} ({obj['bytes']} bytes, {obj['content_type']})")
    
    # Download the object
    print("\nDownloading object 'hello.txt'...")
    obj = client.get_object('test_container', 'hello.txt')
    if obj:
        print(f"✓ Object downloaded")
        print(f"  Content: {obj['data'].decode('utf-8')}")
        print(f"  Content-Type: {obj['content_type']}")
        print(f"  ETag: {obj['etag']}")
        print(f"  Metadata: {obj['metadata']}")

# Made with Bob
