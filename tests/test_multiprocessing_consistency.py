"""Tests to ensure multiprocessing code uses centralized helper and doesn't regress"""

import unittest
import multiprocessing
import platform
import time
from typing import Dict, Any

from stream_checker.utils.multiprocessing_utils import (
    run_process_with_queue,
    ensure_spawn_method,
    DEFAULT_QUEUE_GET_TIMEOUT,
    DEFAULT_PROCESS_CLEANUP_TIMEOUT,
    QUEUE_DRAIN_TIMEOUT,
    QUEUE_JOIN_THREAD_TIMEOUT
)


def _test_worker_success(queue, test_value: str) -> None:
    """Test worker that successfully returns a result"""
    time.sleep(0.1)  # Simulate some work
    queue.put({
        'success': True,
        'returncode': 0,
        'stdout': test_value.encode(),
        'stderr': None,
        'test_value': test_value
    })


def _test_worker_timeout(queue, delay: float) -> None:
    """Test worker that takes too long (should timeout)"""
    time.sleep(delay)
    queue.put({'success': True, 'returncode': 0})


def _test_worker_crash(queue) -> None:
    """Test worker that crashes before putting result"""
    raise RuntimeError("Worker crashed intentionally")


def _test_worker_smoke(queue, sentinel_value: str) -> None:
    """Top-level worker function for smoke testing - must be picklable"""
    queue.put({
        'success': True,
        'sentinel': sentinel_value,
        'platform': platform.system()
    })


def _test_worker_picklable(queue, data: dict) -> None:
    """Top-level worker function for pickling test - accepts plain dict"""
    queue.put({
        'success': True,
        'received_data': data
    })


class TestMultiprocessingConsistency(unittest.TestCase):
    """Test that multiprocessing uses centralized helper and doesn't regress"""
    
    def test_run_process_with_queue_success(self):
        """Test successful execution through run_process_with_queue"""
        ok, result = run_process_with_queue(
            target=_test_worker_success,
            args=("test_value_123",),
            join_timeout=2.0,
            get_timeout=0.5,
            name="test_success"
        )
        
        self.assertTrue(ok, "Process should complete successfully")
        self.assertIsNotNone(result, "Result should not be None")
        self.assertEqual(result.get('success'), True)
        self.assertEqual(result.get('returncode'), 0)
        self.assertEqual(result.get('test_value'), "test_value_123")
    
    def test_run_process_with_queue_timeout(self):
        """Test timeout handling in run_process_with_queue"""
        ok, result = run_process_with_queue(
            target=_test_worker_timeout,
            args=(3.0,),  # Worker sleeps 3 seconds
            join_timeout=1.0,  # But we only wait 1 second
            get_timeout=0.5,
            name="test_timeout"
        )
        
        self.assertFalse(ok, "Process should timeout")
        self.assertIsNone(result, "Result should be None on timeout")
    
    def test_run_process_with_queue_crash(self):
        """Test worker crash handling in run_process_with_queue"""
        ok, result = run_process_with_queue(
            target=_test_worker_crash,
            args=(),
            join_timeout=2.0,
            get_timeout=0.5,
            name="test_crash"
        )
        
        # Worker crashes, should return structured failure info
        self.assertFalse(ok, "Process should fail on crash")
        # Result may be None (timeout/empty queue) or structured failure info (non-zero exitcode)
        if result is not None:
            # If structured failure, should have exitcode
            self.assertIn('exitcode', result, "Failure info should include exitcode")
    
    def test_spawn_method_set_on_macos(self):
        """Test that spawn method is set on macOS (required for fork safety)"""
        if platform.system() == "Darwin":
            # Reset the global state to test fresh initialization
            import stream_checker.utils.multiprocessing_utils as mp_utils
            mp_utils._mp_start_method_set = False
            
            # Call ensure_spawn_method
            ensure_spawn_method()
            
            # Verify spawn method is set
            current_method = multiprocessing.get_start_method(allow_none=True)
            self.assertEqual(
                current_method,
                'spawn',
                f"Start method should be 'spawn' on macOS, got '{current_method}'"
            )
    
    def test_cleanup_completes_quickly(self):
        """Test that cleanup doesn't hang (uses short timeouts)"""
        import time
        
        # Run a process that completes quickly
        start_time = time.time()
        ok, result = run_process_with_queue(
            target=_test_worker_success,
            args=("cleanup_test",),
            join_timeout=1.0,
            get_timeout=0.5,
            name="test_cleanup"
        )
        elapsed = time.time() - start_time
        
        # Cleanup should complete quickly (well under 5 seconds)
        self.assertLess(
            elapsed,
            5.0,
            f"Cleanup should complete quickly, took {elapsed:.2f}s"
        )
        self.assertTrue(ok, "Process should complete")
    
    def test_no_direct_process_creation(self):
        """Test that we're using the helper, not creating processes directly"""
        # This test verifies the pattern - actual enforcement is in CI script
        # We just verify the helper works as expected
        ok, result = run_process_with_queue(
            target=_test_worker_success,
            args=("pattern_test",),
            join_timeout=2.0,
            get_timeout=DEFAULT_QUEUE_GET_TIMEOUT,
            name="test_pattern"
        )
        
        self.assertTrue(ok, "Helper should work correctly")
        # If this test passes, it means we're using the helper correctly
    
    def test_constants_exist(self):
        """Test that timeout constants are defined and have expected values"""
        # Verify constants exist
        self.assertIsNotNone(DEFAULT_QUEUE_GET_TIMEOUT)
        self.assertIsNotNone(DEFAULT_PROCESS_CLEANUP_TIMEOUT)
        self.assertIsNotNone(QUEUE_DRAIN_TIMEOUT)
        self.assertIsNotNone(QUEUE_JOIN_THREAD_TIMEOUT)
        
        # Verify they are numeric
        self.assertIsInstance(DEFAULT_QUEUE_GET_TIMEOUT, (int, float))
        self.assertIsInstance(DEFAULT_PROCESS_CLEANUP_TIMEOUT, (int, float))
        self.assertIsInstance(QUEUE_DRAIN_TIMEOUT, (int, float))
        self.assertIsInstance(QUEUE_JOIN_THREAD_TIMEOUT, (int, float))
        
        # Verify they are positive
        self.assertGreater(DEFAULT_QUEUE_GET_TIMEOUT, 0)
        self.assertGreater(DEFAULT_PROCESS_CLEANUP_TIMEOUT, 0)
        self.assertGreater(QUEUE_DRAIN_TIMEOUT, 0)
        self.assertGreater(QUEUE_JOIN_THREAD_TIMEOUT, 0)
    
    def test_helper_uses_constants(self):
        """Test that helper uses constants (lightweight introspection)"""
        import stream_checker.utils.multiprocessing_utils as mp_utils
        import inspect
        
        # Get the source code of run_process_with_queue
        source = inspect.getsource(mp_utils.run_process_with_queue)
        
        # Verify it references the constants (not hardcoded values)
        # The default parameter should use DEFAULT_QUEUE_GET_TIMEOUT
        self.assertIn("DEFAULT_QUEUE_GET_TIMEOUT", source)
        
        # Verify cleanup uses constants
        cleanup_source = inspect.getsource(mp_utils.cleanup_multiprocessing_process)
        self.assertIn("DEFAULT_PROCESS_CLEANUP_TIMEOUT", cleanup_source)
        
        cleanup_queue_source = inspect.getsource(mp_utils.cleanup_multiprocessing_queue)
        self.assertIn("QUEUE_DRAIN_TIMEOUT", cleanup_queue_source)
        self.assertIn("QUEUE_JOIN_THREAD_TIMEOUT", cleanup_queue_source)
    
    def test_spawn_compatibility_smoke(self):
        """
        Smoke test: Verify run_process_with_queue works on current platform.
        
        This test verifies that the helper function works correctly regardless
        of the platform's default start method (fork on Linux, spawn on macOS).
        """
        sentinel = "smoke_test_sentinel_12345"
        
        ok, result = run_process_with_queue(
            target=_test_worker_smoke,
            args=(sentinel,),
            join_timeout=5.0,
            get_timeout=DEFAULT_QUEUE_GET_TIMEOUT,
            name="test_spawn_compatibility_smoke"
        )
        
        # Should succeed on all platforms
        self.assertTrue(ok, "Worker should complete successfully on all platforms")
        self.assertIsNotNone(result, "Result should not be None")
        self.assertEqual(result.get('success'), True)
        self.assertEqual(result.get('sentinel'), sentinel)
        
        # On macOS, verify spawn method is active
        if platform.system() == "Darwin":
            current_method = multiprocessing.get_start_method(allow_none=True)
            self.assertEqual(
                current_method,
                'spawn',
                f"On macOS, start method should be 'spawn', got '{current_method}'"
            )
    
    def test_worker_is_picklable(self):
        """
        Test that worker function is picklable (module top-level) and args are picklable.
        
        This test ensures:
        1. Worker function is at module top-level (not a lambda/closure)
        2. Worker args are picklable (plain dict, not lambda)
        """
        import pickle
        
        # Test 1: Worker function should be picklable (module top-level)
        try:
            pickled_worker = pickle.dumps(_test_worker_picklable)
            unpickled_worker = pickle.loads(pickled_worker)
            self.assertIsNotNone(unpickled_worker, "Worker function should be picklable")
        except Exception as e:
            self.fail(f"Worker function is not picklable: {e}")
        
        # Test 2: Worker args should be picklable (plain dict, not lambda)
        test_data = {
            'key1': 'value1',
            'key2': 42,
            'key3': [1, 2, 3]
        }
        
        try:
            pickled_data = pickle.dumps(test_data)
            unpickled_data = pickle.loads(pickled_data)
            self.assertEqual(unpickled_data, test_data, "Test data should be picklable")
        except Exception as e:
            self.fail(f"Test data is not picklable: {e}")
        
        # Test 3: Actually run the worker with picklable args
        ok, result = run_process_with_queue(
            target=_test_worker_picklable,
            args=(test_data,),
            join_timeout=5.0,
            get_timeout=DEFAULT_QUEUE_GET_TIMEOUT,
            name="test_worker_is_picklable"
        )
        
        self.assertTrue(ok, "Worker should complete successfully with picklable args")
        self.assertIsNotNone(result, "Result should not be None")
        self.assertEqual(result.get('success'), True)
        self.assertEqual(result.get('received_data'), test_data)


if __name__ == '__main__':
    unittest.main()
