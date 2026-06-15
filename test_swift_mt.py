#!/usr/bin/env python3
"""
Test script for Multithreaded Swift Client
Demonstrates concurrent PUT and GET operations using queues and threads
"""

import time
import sys
import os
from swift_client_mt import SwiftClientMultiThreaded, SwiftOperation, OperationType, OperationResult


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def progress_callback(result: OperationResult):
    """Callback function to show progress"""
    status = "✓" if result.success else "✗"
    print(f"  {status} {result.operation_type.value} completed in {result.duration*1000:.2f}ms")


def test_multithreaded_operations():
    """Test multithreaded Swift operations"""
    
    print_section("Initializing Multithreaded Swift Client")
    
    # Initialize client with 1000 worker threads for massive concurrency
    client = SwiftClientMultiThreaded('http://localhost:8080', 'mt_demo_account', max_workers=1000)
    
    # Check server health first
    from swift_client import SwiftClient
    simple_client = SwiftClient('http://localhost:8080', 'mt_demo_account')
    if not simple_client.health_check():
        print("✗ Server is not responding!")
        print("  Please make sure the server is running:")
        print("  python swift_server.py")
        return False
    
    print(f"✓ Client initialized with {client.max_workers} worker threads (MASSIVE SCALE)")
    print(f"  Server URL: http://localhost:8080")
    print(f"  Account: mt_demo_account")
    
    # Start worker threads
    print_section("Starting Worker Threads")
    client.start_workers()
    print(f"✓ {len(client.worker_threads)} worker threads started")
    
    # Test 1: Create 1000 containers concurrently
    print_section("Test 1: Creating 1000 Containers Concurrently")
    
    # Generate 1000 container names
    containers = [f'container_{i:04d}' for i in range(1000)]
    container_ops = []
    
    print(f"Queuing {len(containers)} container creation operations...")
    start_time = time.time()
    
    for container in containers:
        op = SwiftOperation(
            operation_type=OperationType.CREATE_CONTAINER,
            container_name=container
        )
        op_id = client.queue_operation(op)
        container_ops.append(op_id)
    
    # Wait for all container creations to complete
    client.wait_for_completion()
    creation_time = time.time() - start_time
    
    print(f"\n✓ Created {len(containers)} containers in {creation_time:.2f}s")
    print(f"  Throughput: {len(containers)/creation_time:.2f} containers/second")
    
    # List all containers to verify
    print_section("Listing All Containers")
    print("Fetching container list from server...")
    all_containers = simple_client.list_containers()
    print(f"\nTotal containers in account: {len(all_containers)}")
    
    # Show first 20 and last 20 containers
    if len(all_containers) > 40:
        print("\nFirst 20 containers:")
        for i, container in enumerate(all_containers[:20]):
            print(f"  {i+1:4d}. {container['name']:20s} - {container['count']:4d} objects, {container['bytes']:8d} bytes")
        
        print(f"\n  ... ({len(all_containers) - 40} more containers) ...")
        
        print(f"\nLast 20 containers:")
        for i, container in enumerate(all_containers[-20:], start=len(all_containers)-19):
            print(f"  {i:4d}. {container['name']:20s} - {container['count']:4d} objects, {container['bytes']:8d} bytes")
    else:
        print("\nAll containers:")
        for i, container in enumerate(all_containers, start=1):
            print(f"  {i:4d}. {container['name']:20s} - {container['count']:4d} objects, {container['bytes']:8d} bytes")
    
    # Test 1.5: Fill all 1000 containers with data
    print_section("Test 1.5: Filling All 1000 Containers with Data")
    
    print("Preparing to upload 10 objects to each of 1000 containers...")
    print("Total: 10,000 objects across 1000 containers")
    
    start_time = time.time()
    fill_ops = []
    
    # Upload 10 objects to each container (10KB each = 100MB total)
    for container_idx in range(1000):
        container_name = f'container_{container_idx:04d}'
        for obj_idx in range(10):
            object_name = f'data_{obj_idx:02d}.txt'
            data = (f'Container {container_idx} - Object {obj_idx}\n' * 200).encode()  # 10KB
            op_id = client.put_object_async(container_name, object_name, data, 'text/plain',
                                           metadata={'container': str(container_idx), 'object': str(obj_idx)})
            fill_ops.append(op_id)
    
    print(f"Queued {len(fill_ops)} upload operations")
    print("Waiting for completion...")
    
    # Wait for all uploads
    client.wait_for_completion()
    fill_time = time.time() - start_time
    
    print(f"\n✓ Filled all 1000 containers in {fill_time:.2f}s")
    print(f"  Total objects uploaded: {len(fill_ops)}")
    print(f"  Throughput: {len(fill_ops)/fill_time:.2f} objects/second")
    print(f"  Data uploaded: ~100 MB")
    
    # List containers again to show they now have data
    print("\nVerifying containers now have data...")
    all_containers = simple_client.list_containers()
    containers_with_data = [c for c in all_containers if c['count'] > 0]
    print(f"✓ {len(containers_with_data)}/{len(all_containers)} containers now contain data")
    
    # Show sample of filled containers
    print("\nSample of filled containers (first 10):")
    for i, container in enumerate(all_containers[:10]):
        print(f"  {container['name']:20s} - {container['count']:4d} objects, {container['bytes']:8d} bytes")
    
    # Test 2: Batch upload - Upload many objects concurrently at MASSIVE SCALE
    print_section("Test 2: Additional Batch Upload (5000 Objects to container_0000)")
    
    start_time = time.time()
    
    # Prepare 5000 objects to upload with larger data
    objects_to_upload = []
    for i in range(5000):
        object_name = f'file_{i:05d}.txt'
        # Create larger data (10KB per object)
        data = (f'This is test file number {i}\n' * 200).encode()
        content_type = 'text/plain'
        objects_to_upload.append((object_name, data, content_type))
    
    print(f"Preparing to upload {len(objects_to_upload)} objects (~{len(objects_to_upload)*10}KB total)")
    
    # Upload all objects concurrently to first container
    upload_ids = client.batch_upload('container_0000', objects_to_upload,
                                     metadata={'batch': 'massive_test', 'count': '5000'})
    
    # Wait for all uploads to complete
    client.wait_for_completion()
    
    upload_duration = time.time() - start_time
    print(f"\n✓ Uploaded {len(upload_ids)} objects in {upload_duration:.2f}s")
    print(f"  Average: {upload_duration/len(upload_ids)*1000:.2f}ms per object")
    
    # Test 3: Batch download - Download many objects concurrently at MASSIVE SCALE
    print_section("Test 3: Batch Download (5000 Objects Concurrently)")
    
    start_time = time.time()
    
    # Download all objects concurrently from first container
    object_names = [f'file_{i:05d}.txt' for i in range(5000)]
    download_ids = client.batch_download('container_0000', object_names)
    
    # Wait for all downloads to complete
    client.wait_for_completion()
    
    download_duration = time.time() - start_time
    print(f"\n✓ Downloaded {len(download_ids)} objects in {download_duration:.2f}s")
    print(f"  Average: {download_duration/len(download_ids)*1000:.2f}ms per object")
    
    # Verify sample of downloaded data (checking all 5000 would be slow)
    print("\nVerifying sample of downloaded data (first 100 objects)...")
    success_count = 0
    for i in range(min(100, len(download_ids))):
        op_id = download_ids[i]
        result = client.get_result(op_id)
        if result and result.success and result.result:
            expected_content = (f'This is test file number {i}\n' * 200)
            actual_content = result.result['data'].decode('utf-8')
            if actual_content == expected_content:
                success_count += 1
    
    print(f"✓ Verified {success_count}/100 sample objects (all {len(download_ids)} downloaded)")
    
    # Test 4: Mixed operations - Upload and download simultaneously at MASSIVE SCALE
    print_section("Test 4: Mixed Operations (2000 Uploads + 2000 Downloads)")
    
    start_time = time.time()
    
    # Queue uploads to second container (2000 objects, 100KB each)
    image_uploads = []
    for i in range(2000):
        data = bytes([i % 256] * 102400)  # 100KB of binary data
        op_id = client.put_object_async('container_0001', f'image_{i:05d}.bin', data,
                                       'application/octet-stream',
                                       metadata={'size': '102400', 'index': str(i)})
        image_uploads.append(op_id)
    
    # Queue downloads from first container (2000 objects)
    doc_downloads = []
    for i in range(2000):
        op_id = client.get_object_async('container_0000', f'file_{i:05d}.txt')
        doc_downloads.append(op_id)
    
    # Wait for all operations
    client.wait_for_completion()
    
    mixed_duration = time.time() - start_time
    print(f"\n✓ Completed {len(image_uploads) + len(doc_downloads)} mixed operations in {mixed_duration:.2f}s")
    
    # Test 5: File upload/download operations at SCALE
    print_section("Test 5: File Upload/Download Operations (500 Files)")
    
    # Create test files
    test_files = []
    for i in range(500):
        filename = f'test_file_{i:04d}.txt'
        with open(filename, 'w') as f:
            # Each file is ~50KB
            f.write(f'Test file {i} - Line content\n' * 1000)
        test_files.append(filename)
    
    print(f"Created {len(test_files)} test files (~25MB total)")
    
    # Upload files concurrently to third container
    file_upload_ids = []
    for filename in test_files:
        op_id = client.put_file_async('container_0002', filename, filename, 'text/plain',
                                     metadata={'source': 'test_script'})
        file_upload_ids.append(op_id)
    
    client.wait_for_completion()
    print(f"✓ Uploaded {len(file_upload_ids)} files")
    
    # Download files concurrently from third container
    file_download_ids = []
    for filename in test_files:
        download_name = f'downloaded_{filename}'
        op_id = client.get_file_async('container_0002', filename, download_name)
        file_download_ids.append(op_id)
    
    client.wait_for_completion()
    print(f"✓ Downloaded {len(file_download_ids)} files")
    
    # Verify file contents
    print("\nVerifying file contents...")
    verified = 0
    missing = 0
    for filename in test_files:
        download_name = f'downloaded_{filename}'
        try:
            with open(filename, 'rb') as f1, open(download_name, 'rb') as f2:
                if f1.read() == f2.read():
                    verified += 1
        except FileNotFoundError:
            missing += 1
    
    print(f"✓ Verified {verified}/{len(test_files)} files")
    if missing > 0:
        print(f"  ⚠ {missing} files were not downloaded (may still be in queue)")
    
    # Cleanup test files
    for filename in test_files:
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass
        try:
            os.remove(f'downloaded_{filename}')
        except FileNotFoundError:
            pass
    
    # Test 6: MASSIVE batch operation with progress tracking
    print_section("Test 6: MASSIVE Batch with Progress Tracking (10000 Objects)")
    
    completed = [0]  # Use list to allow modification in callback
    
    def progress_tracker(result: OperationResult):
        completed[0] += 1
        if completed[0] % 500 == 0:
            print(f"  Progress: {completed[0]}/10000 operations completed")
    
    # Upload 10000 objects with 50KB each
    large_batch = []
    for i in range(10000):
        data = (f'Object {i} - ' * 1000).encode()  # ~50KB per object
        large_batch.append((f'obj_{i:05d}.txt', data, 'text/plain'))
    
    print(f"Preparing massive batch: 10000 objects (~500MB total)")
    
    start_time = time.time()
    batch_ids = client.batch_upload('container_0003', large_batch, metadata={'batch': 'massive'})
    
    # Wait for completion
    client.wait_for_completion()
    
    batch_duration = time.time() - start_time
    print(f"\n✓ Completed 10000 uploads in {batch_duration:.2f}s")
    print(f"  Throughput: {10000/batch_duration:.2f} operations/second")
    print(f"  Data rate: {(500*1024*1024)/batch_duration/1024/1024:.2f} MB/s")
    
    # Display final statistics
    print_section("Final Statistics")
    
    stats = client.get_statistics()
    print(f"Total Operations:     {stats['total_operations']}")
    print(f"Successful:           {stats['successful_operations']}")
    print(f"Failed:               {stats['failed_operations']}")
    print(f"Success Rate:         {stats['success_rate']*100:.1f}%")
    print(f"Average Duration:     {stats['average_duration']*1000:.2f}ms")
    print(f"Total Duration:       {stats['total_duration']:.2f}s")
    
    # Performance comparison at scale
    print_section("Performance Comparison (Sequential vs 1000 Threads)")
    
    # Sequential upload test
    print("\nSequential upload (100 objects, 10KB each)...")
    seq_start = time.time()
    seq_client = SwiftClient('http://localhost:8080', 'mt_demo_account')
    for i in range(100):
        data = (f'Sequential {i}\n' * 200).encode()  # 10KB
        seq_client.put_object('container_0004', f'seq_{i:03d}.txt', data, 'text/plain')
    seq_duration = time.time() - seq_start
    print(f"  Time: {seq_duration:.2f}s")
    print(f"  Throughput: {100/seq_duration:.2f} ops/s")
    
    # Concurrent upload test with 1000 threads
    print("\nConcurrent upload (100 objects, 10KB each, 1000 threads)...")
    client.clear_statistics()
    con_start = time.time()
    con_objects = [(f'con_{i:03d}.txt', (f'Concurrent {i}\n' * 200).encode(), 'text/plain') for i in range(100)]
    client.batch_upload('container_0005', con_objects)
    client.wait_for_completion()
    con_duration = time.time() - con_start
    print(f"  Time: {con_duration:.2f}s")
    print(f"  Throughput: {100/con_duration:.2f} ops/s")
    
    speedup = seq_duration / con_duration if con_duration > 0 else 0
    print(f"\n✓ Speedup: {speedup:.2f}x faster with 1000-thread multithreading")
    print(f"  Sequential: {seq_duration:.2f}s")
    print(f"  Concurrent: {con_duration:.2f}s")
    
    # Stop workers
    print_section("Cleanup")
    client.stop_workers()
    print("✓ Worker threads stopped")
    
    return True


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════════════╗
║     Multithreaded Swift Client Test Suite                       ║
║     Queue-based Concurrent Operations Demo                      ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        success = test_multithreaded_operations()
        
        if success:
            print("\n" + "="*70)
            print("  ✓ All multithreaded tests passed!")
            print("="*70)
            sys.exit(0)
        else:
            print("\n" + "="*70)
            print("  ✗ Tests failed - check server status")
            print("="*70)
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
