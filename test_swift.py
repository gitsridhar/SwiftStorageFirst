#!/usr/bin/env python3
"""
Test script to demonstrate Swift client PUT and GET operations
"""

import time
import sys
from swift_client import SwiftClient


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_swift_operations():
    """Test Swift server and client operations"""
    
    # Initialize client
    print_section("Initializing Swift Client")
    client = SwiftClient('http://localhost:8080', 'demo_account')
    print(f"✓ Client initialized for account: demo_account")
    print(f"  Server URL: http://localhost:8080")
    
    # Check server health
    print_section("Health Check")
    if client.health_check():
        print("✓ Server is healthy and responding")
    else:
        print("✗ Server is not responding!")
        print("  Please make sure the server is running:")
        print("  python swift_server.py")
        return False
    
    # Create containers
    print_section("Creating Containers")
    containers_to_create = ['documents', 'images', 'backups']
    
    for container in containers_to_create:
        if client.create_container(container):
            print(f"✓ Container '{container}' created successfully")
        else:
            print(f"✗ Failed to create container '{container}'")
    
    # Upload text objects
    print_section("Uploading Text Objects")
    
    text_objects = [
        ('documents', 'readme.txt', b'This is a README file for the Swift demo.', 'text/plain'),
        ('documents', 'notes.txt', b'Important notes:\n1. Test Swift\n2. Verify storage\n3. Check retrieval', 'text/plain'),
        ('backups', 'config.txt', b'server=localhost\nport=8080\ndatabase=swift_storage.db', 'text/plain'),
    ]
    
    for container, obj_name, data, content_type in text_objects:
        metadata = {
            'uploaded_by': 'test_script',
            'timestamp': str(int(time.time())),
            'size': str(len(data))
        }
        etag = client.put_object(container, obj_name, data, content_type, metadata)
        if etag:
            print(f"✓ Uploaded '{obj_name}' to '{container}' (ETag: {etag[:16]}...)")
        else:
            print(f"✗ Failed to upload '{obj_name}' to '{container}'")
    
    # Upload binary data
    print_section("Uploading Binary Objects")
    
    # Create some sample binary data
    binary_data = bytes(range(256))  # 256 bytes of binary data
    etag = client.put_object('images', 'sample.bin', binary_data, 
                            'application/octet-stream',
                            metadata={'type': 'binary', 'test': 'true'})
    if etag:
        print(f"✓ Uploaded binary object 'sample.bin' ({len(binary_data)} bytes)")
    
    # List all containers
    print_section("Listing All Containers")
    containers = client.list_containers()
    if containers:
        print(f"Found {len(containers)} container(s):")
        for container in containers:
            print(f"  📦 {container['name']}")
            print(f"     Objects: {container['count']}, Size: {container['bytes']} bytes")
    else:
        print("No containers found")
    
    # List objects in each container
    print_section("Listing Objects in Containers")
    for container in containers:
        container_name = container['name']
        objects = client.list_objects(container_name)
        print(f"\n📦 Container: {container_name}")
        if objects:
            for obj in objects:
                print(f"  📄 {obj['name']}")
                print(f"     Size: {obj['bytes']} bytes")
                print(f"     Type: {obj['content_type']}")
                print(f"     Hash: {obj['hash'][:16]}...")
                print(f"     Modified: {obj['last_modified']}")
        else:
            print("  (empty)")
    
    # Download and verify objects
    print_section("Downloading and Verifying Objects")
    
    test_downloads = [
        ('documents', 'readme.txt'),
        ('documents', 'notes.txt'),
        ('backups', 'config.txt'),
        ('images', 'sample.bin'),
    ]
    
    for container, obj_name in test_downloads:
        obj = client.get_object(container, obj_name)
        if obj:
            print(f"\n✓ Downloaded '{obj_name}' from '{container}'")
            print(f"  Content-Type: {obj['content_type']}")
            print(f"  Size: {obj['content_length']} bytes")
            print(f"  ETag: {obj['etag'][:16]}...")
            
            if obj['metadata']:
                print(f"  Metadata:")
                for key, value in obj['metadata'].items():
                    print(f"    {key}: {value}")
            
            # Display content for text files
            if obj['content_type'] == 'text/plain':
                content = obj['data'].decode('utf-8')
                print(f"  Content preview:")
                for line in content.split('\n')[:3]:  # Show first 3 lines
                    print(f"    {line}")
                if len(content.split('\n')) > 3:
                    print(f"    ... ({len(content.split('\n')) - 3} more lines)")
        else:
            print(f"✗ Failed to download '{obj_name}' from '{container}'")
    
    # Test file upload/download
    print_section("Testing File Upload/Download")
    
    # Create a test file
    test_file = 'test_upload.txt'
    test_content = b'This is a test file for upload/download operations.\nLine 2\nLine 3'
    with open(test_file, 'wb') as f:
        f.write(test_content)
    print(f"✓ Created test file: {test_file}")
    
    # Upload from file
    etag = client.put_object_from_file('documents', 'uploaded_file.txt', test_file, 
                                      'text/plain', 
                                      metadata={'source': 'file_upload'})
    if etag:
        print(f"✓ Uploaded file to Swift (ETag: {etag[:16]}...)")
    
    # Download to file
    download_file = 'test_download.txt'
    if client.get_object_to_file('documents', 'uploaded_file.txt', download_file):
        print(f"✓ Downloaded object to file: {download_file}")
        
        # Verify content
        with open(download_file, 'rb') as f:
            downloaded_content = f.read()
        
        if downloaded_content == test_content:
            print(f"✓ Content verification successful!")
        else:
            print(f"✗ Content mismatch!")
    
    # Update an existing object
    print_section("Updating Existing Object")
    
    updated_data = b'This is the UPDATED content of readme.txt'
    etag = client.put_object('documents', 'readme.txt', updated_data, 'text/plain',
                            metadata={'version': '2', 'updated': 'true'})
    if etag:
        print(f"✓ Updated 'readme.txt' (new ETag: {etag[:16]}...)")
        
        # Verify update
        obj = client.get_object('documents', 'readme.txt')
        if obj and obj['data'] == updated_data:
            print(f"✓ Update verified successfully")
            print(f"  New metadata: {obj['metadata']}")
    
    # Final summary
    print_section("Test Summary")
    containers = client.list_containers()
    total_objects = sum(c['count'] for c in containers)
    total_bytes = sum(c['bytes'] for c in containers)
    
    print(f"✓ All tests completed successfully!")
    print(f"\nFinal Statistics:")
    print(f"  Containers: {len(containers)}")
    print(f"  Total Objects: {total_objects}")
    print(f"  Total Storage: {total_bytes} bytes")
    
    return True


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════════╗
║         OpenStack Swift Server & Client Test Suite          ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        success = test_swift_operations()
        
        if success:
            print("\n" + "="*60)
            print("  ✓ All tests passed!")
            print("="*60)
            sys.exit(0)
        else:
            print("\n" + "="*60)
            print("  ✗ Tests failed - check server status")
            print("="*60)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# Made with Bob
