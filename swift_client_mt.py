#!/usr/bin/env python3
"""
OpenStack Swift Client Implementation with Multithreading and Queue Support
"""

import requests
import json
import threading
import queue
import time
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed


class OperationType(Enum):
    """Types of Swift operations"""
    PUT_OBJECT = "put_object"
    GET_OBJECT = "get_object"
    PUT_FILE = "put_file"
    GET_FILE = "get_file"
    CREATE_CONTAINER = "create_container"
    LIST_CONTAINERS = "list_containers"
    LIST_OBJECTS = "list_objects"


@dataclass
class SwiftOperation:
    """Represents a Swift operation to be queued"""
    operation_type: OperationType
    container_name: Optional[str] = None
    object_name: Optional[str] = None
    data: Optional[bytes] = None
    file_path: Optional[str] = None
    content_type: str = 'application/octet-stream'
    metadata: Optional[Dict[str, str]] = None
    callback: Optional[Callable] = None
    operation_id: Optional[str] = None


@dataclass
class OperationResult:
    """Result of a Swift operation"""
    operation_id: str
    operation_type: OperationType
    success: bool
    result: Any
    error: Optional[str] = None
    duration: float = 0.0


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
        """Create a container"""
        url = self._get_url(container_name)
        response = self.session.put(url)
        return response.status_code in [201, 202]
    
    def list_containers(self) -> List[Dict[str, Any]]:
        """List all containers in the account"""
        url = f"{self.base_url}/v1/{self.account_id}"
        response = self.session.get(url)
        
        if response.status_code == 200:
            return response.json()
        return []
    
    def list_objects(self, container_name: str) -> List[Dict[str, Any]]:
        """List objects in a container"""
        url = self._get_url(container_name)
        response = self.session.get(url)
        
        if response.status_code == 200:
            return response.json()
        return []
    
    def put_object(self, container_name: str, object_name: str, 
                   data: bytes, content_type: str = 'application/octet-stream',
                   metadata: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Upload an object to a container"""
        url = self._get_url(container_name, object_name)
        headers = {'Content-Type': content_type}
        
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
        """Upload a file as an object"""
        with open(file_path, 'rb') as f:
            data = f.read()
        return self.put_object(container_name, object_name, data, content_type, metadata)
    
    def get_object(self, container_name: str, object_name: str) -> Optional[Dict[str, Any]]:
        """Download an object from a container"""
        url = self._get_url(container_name, object_name)
        response = self.session.get(url)
        
        if response.status_code == 200:
            metadata = {}
            for key, value in response.headers.items():
                if key.lower().startswith('x-object-meta-'):
                    meta_key = key[14:]
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
        """Download an object and save it to a file"""
        obj = self.get_object(container_name, object_name)
        if obj:
            with open(file_path, 'wb') as f:
                f.write(obj['data'])
            return True
        return False
    
    def health_check(self) -> bool:
        """Check if the Swift server is healthy"""
        try:
            url = f"{self.base_url}/health"
            response = self.session.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


class SwiftClientMultiThreaded:
    """
    Multithreaded Swift client with queue support for concurrent operations
    """
    
    def __init__(self, base_url: str, account_id: str, max_workers: int = 5):
        """
        Initialize multithreaded Swift client
        
        Args:
            base_url: Base URL of Swift server
            account_id: Account identifier
            max_workers: Maximum number of worker threads
        """
        self.base_url = base_url
        self.account_id = account_id
        self.max_workers = max_workers
        
        # Create a client for each thread to avoid session conflicts
        self._thread_local = threading.local()
        
        # Queue for operations
        self.operation_queue = queue.Queue()
        
        # Results storage
        self.results = {}
        self.results_lock = threading.Lock()
        
        # Worker control
        self.workers_running = False
        self.worker_threads = []
        
        # Statistics
        self.stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_duration': 0.0
        }
        self.stats_lock = threading.Lock()
    
    def _get_client(self) -> SwiftClient:
        """Get thread-local Swift client"""
        if not hasattr(self._thread_local, 'client'):
            self._thread_local.client = SwiftClient(self.base_url, self.account_id)
        return self._thread_local.client
    
    def _worker(self):
        """Worker thread that processes operations from the queue"""
        client = self._get_client()
        
        while self.workers_running:
            try:
                # Get operation from queue with timeout
                operation = self.operation_queue.get(timeout=1)
                
                # Process the operation
                result = self._execute_operation(client, operation)
                
                # Store result
                with self.results_lock:
                    self.results[result.operation_id] = result
                
                # Update statistics
                with self.stats_lock:
                    self.stats['total_operations'] += 1
                    if result.success:
                        self.stats['successful_operations'] += 1
                    else:
                        self.stats['failed_operations'] += 1
                    self.stats['total_duration'] += result.duration
                
                # Call callback if provided
                if operation.callback:
                    operation.callback(result)
                
                # Mark task as done
                self.operation_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
    
    def _execute_operation(self, client: SwiftClient, operation: SwiftOperation) -> OperationResult:
        """Execute a single operation"""
        start_time = time.time()
        
        try:
            if operation.operation_type == OperationType.PUT_OBJECT:
                result = client.put_object(
                    operation.container_name,
                    operation.object_name,
                    operation.data,
                    operation.content_type,
                    operation.metadata
                )
                success = result is not None
                
            elif operation.operation_type == OperationType.GET_OBJECT:
                result = client.get_object(
                    operation.container_name,
                    operation.object_name
                )
                success = result is not None
                
            elif operation.operation_type == OperationType.PUT_FILE:
                result = client.put_object_from_file(
                    operation.container_name,
                    operation.object_name,
                    operation.file_path,
                    operation.content_type,
                    operation.metadata
                )
                success = result is not None
                
            elif operation.operation_type == OperationType.GET_FILE:
                result = client.get_object_to_file(
                    operation.container_name,
                    operation.object_name,
                    operation.file_path
                )
                success = result
                
            elif operation.operation_type == OperationType.CREATE_CONTAINER:
                result = client.create_container(operation.container_name)
                success = result
                
            elif operation.operation_type == OperationType.LIST_CONTAINERS:
                result = client.list_containers()
                success = True
                
            elif operation.operation_type == OperationType.LIST_OBJECTS:
                result = client.list_objects(operation.container_name)
                success = True
                
            else:
                result = None
                success = False
            
            duration = time.time() - start_time
            
            return OperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                success=success,
                result=result,
                duration=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return OperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                success=False,
                result=None,
                error=str(e),
                duration=duration
            )
    
    def start_workers(self):
        """Start worker threads"""
        if self.workers_running:
            return
        
        self.workers_running = True
        self.worker_threads = []
        
        for i in range(self.max_workers):
            thread = threading.Thread(target=self._worker, name=f"SwiftWorker-{i}")
            thread.daemon = True
            thread.start()
            self.worker_threads.append(thread)
    
    def stop_workers(self, wait: bool = True):
        """Stop worker threads"""
        self.workers_running = False
        
        if wait:
            for thread in self.worker_threads:
                thread.join()
        
        self.worker_threads = []
    
    def queue_operation(self, operation: SwiftOperation) -> str:
        """
        Queue an operation for execution
        
        Args:
            operation: SwiftOperation to queue
            
        Returns:
            Operation ID for tracking
        """
        if operation.operation_id is None:
            operation.operation_id = f"{operation.operation_type.value}_{time.time()}_{id(operation)}"
        
        self.operation_queue.put(operation)
        return operation.operation_id
    
    def get_result(self, operation_id: str, timeout: Optional[float] = None) -> Optional[OperationResult]:
        """
        Get result of an operation
        
        Args:
            operation_id: ID of the operation
            timeout: Maximum time to wait for result
            
        Returns:
            OperationResult or None if not found
        """
        start_time = time.time()
        
        while True:
            with self.results_lock:
                if operation_id in self.results:
                    return self.results[operation_id]
            
            if timeout and (time.time() - start_time) > timeout:
                return None
            
            time.sleep(0.1)
    
    def wait_for_completion(self, timeout: Optional[float] = None):
        """Wait for all queued operations to complete"""
        if timeout is None:
            # Wait indefinitely
            self.operation_queue.join()
        else:
            # Wait with timeout
            start_time = time.time()
            while not self.operation_queue.empty():
                if (time.time() - start_time) > timeout:
                    break
                time.sleep(0.1)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get operation statistics"""
        with self.stats_lock:
            stats = self.stats.copy()
            if stats['total_operations'] > 0:
                stats['average_duration'] = stats['total_duration'] / stats['total_operations']
                stats['success_rate'] = stats['successful_operations'] / stats['total_operations']
            else:
                stats['average_duration'] = 0.0
                stats['success_rate'] = 0.0
            return stats
    
    def clear_results(self):
        """Clear stored results"""
        with self.results_lock:
            self.results.clear()
    
    def clear_statistics(self):
        """Clear statistics"""
        with self.stats_lock:
            self.stats = {
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'total_duration': 0.0
            }
    
    # Convenience methods for common operations
    
    def put_object_async(self, container_name: str, object_name: str, data: bytes,
                        content_type: str = 'application/octet-stream',
                        metadata: Optional[Dict[str, str]] = None,
                        callback: Optional[Callable] = None) -> str:
        """Queue an object upload operation"""
        operation = SwiftOperation(
            operation_type=OperationType.PUT_OBJECT,
            container_name=container_name,
            object_name=object_name,
            data=data,
            content_type=content_type,
            metadata=metadata,
            callback=callback
        )
        return self.queue_operation(operation)
    
    def get_object_async(self, container_name: str, object_name: str,
                        callback: Optional[Callable] = None) -> str:
        """Queue an object download operation"""
        operation = SwiftOperation(
            operation_type=OperationType.GET_OBJECT,
            container_name=container_name,
            object_name=object_name,
            callback=callback
        )
        return self.queue_operation(operation)
    
    def put_file_async(self, container_name: str, object_name: str, file_path: str,
                      content_type: str = 'application/octet-stream',
                      metadata: Optional[Dict[str, str]] = None,
                      callback: Optional[Callable] = None) -> str:
        """Queue a file upload operation"""
        operation = SwiftOperation(
            operation_type=OperationType.PUT_FILE,
            container_name=container_name,
            object_name=object_name,
            file_path=file_path,
            content_type=content_type,
            metadata=metadata,
            callback=callback
        )
        return self.queue_operation(operation)
    
    def get_file_async(self, container_name: str, object_name: str, file_path: str,
                      callback: Optional[Callable] = None) -> str:
        """Queue a file download operation"""
        operation = SwiftOperation(
            operation_type=OperationType.GET_FILE,
            container_name=container_name,
            object_name=object_name,
            file_path=file_path,
            callback=callback
        )
        return self.queue_operation(operation)
    
    def batch_upload(self, container_name: str, objects: List[Tuple[str, bytes, str]],
                    metadata: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Upload multiple objects concurrently
        
        Args:
            container_name: Container name
            objects: List of (object_name, data, content_type) tuples
            metadata: Optional metadata for all objects
            
        Returns:
            List of operation IDs
        """
        operation_ids = []
        for object_name, data, content_type in objects:
            op_id = self.put_object_async(container_name, object_name, data,
                                         content_type, metadata)
            operation_ids.append(op_id)
        return operation_ids
    
    def batch_download(self, container_name: str, object_names: List[str]) -> List[str]:
        """
        Download multiple objects concurrently
        
        Args:
            container_name: Container name
            object_names: List of object names to download
            
        Returns:
            List of operation IDs
        """
        operation_ids = []
        for object_name in object_names:
            op_id = self.get_object_async(container_name, object_name)
            operation_ids.append(op_id)
        return operation_ids


# Example usage
if __name__ == '__main__':
    print("Multithreaded Swift Client Demo")
    print("=" * 60)
    
    # Initialize multithreaded client
    client = SwiftClientMultiThreaded('http://localhost:8080', 'mt_account', max_workers=5)
    
    # Start workers
    client.start_workers()
    print(f"✓ Started {client.max_workers} worker threads")
    
    # Create container
    print("\nCreating container...")
    op_id = client.queue_operation(SwiftOperation(
        operation_type=OperationType.CREATE_CONTAINER,
        container_name='mt_test'
    ))
    result = client.get_result(op_id, timeout=5)
    if result and result.success:
        print("✓ Container created")
    
    # Upload multiple objects concurrently
    print("\nUploading 10 objects concurrently...")
    objects = [
        (f'file_{i}.txt', f'Content of file {i}'.encode(), 'text/plain')
        for i in range(10)
    ]
    op_ids = client.batch_upload('mt_test', objects, metadata={'batch': 'demo'})
    
    # Wait for completion
    client.wait_for_completion()
    print(f"✓ Uploaded {len(op_ids)} objects")
    
    # Download objects concurrently
    print("\nDownloading objects concurrently...")
    download_ids = client.batch_download('mt_test', [f'file_{i}.txt' for i in range(10)])
    client.wait_for_completion()
    print(f"✓ Downloaded {len(download_ids)} objects")
    
    # Show statistics
    print("\nStatistics:")
    stats = client.get_statistics()
    print(f"  Total operations: {stats['total_operations']}")
    print(f"  Successful: {stats['successful_operations']}")
    print(f"  Failed: {stats['failed_operations']}")
    print(f"  Success rate: {stats['success_rate']*100:.1f}%")
    print(f"  Average duration: {stats['average_duration']*1000:.2f}ms")
    
    # Stop workers
    client.stop_workers()
    print("\n✓ Workers stopped")

# Made with Bob
