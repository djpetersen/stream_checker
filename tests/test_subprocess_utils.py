"""Unit tests for subprocess_utils module"""

import unittest
import threading
import platform
import os
from stream_checker.utils.subprocess_utils import run_subprocess_safe


class TestSubprocessUtils(unittest.TestCase):
    """Test safe subprocess execution"""
    
    def test_run_subprocess_safe_basic(self):
        """Test basic subprocess execution"""
        result = run_subprocess_safe(
            ["echo", "test"],
            timeout=5.0,
            text=True
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['stdout'].strip(), "test")
        self.assertFalse(result['is_signal_kill'])
    
    def test_run_subprocess_safe_timeout(self):
        """Test subprocess timeout handling"""
        result = run_subprocess_safe(
            ["sleep", "10"],
            timeout=0.1,
            text=True
        )
        
        self.assertFalse(result['success'])
        self.assertIn('timeout', result.get('error', '').lower())
    
    def test_run_subprocess_safe_signal_classification(self):
        """Test signal classification for killed processes"""
        # Test with a command that will fail (non-zero exit)
        result = run_subprocess_safe(
            ["false"],
            timeout=5.0,
            text=True
        )
        
        self.assertTrue(result['success'])  # subprocess.run() succeeded
        self.assertEqual(result['returncode'], 1)  # false returns 1
        self.assertFalse(result['is_signal_kill'])  # Not killed by signal
    
    @unittest.skipIf(platform.system() != "Darwin", "macOS-specific test")
    def test_run_subprocess_safe_ffmpeg_multithreaded(self):
        """
        Test that run_subprocess_safe prevents fork crashes on macOS
        when called from a multi-threaded process.
        
        This test starts a background thread, then calls run_subprocess_safe
        with ffmpeg 20 times to verify the parent Python process does not crash.
        """
        # Check if ffmpeg is available
        ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
        if not os.path.exists(ffmpeg_path):
            # Try to find ffmpeg in PATH
            import shutil
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                self.skipTest("ffmpeg not found in PATH")
        
        # Start a background thread to make the process multi-threaded
        thread_running = threading.Event()
        thread_started = threading.Event()
        
        def background_thread():
            thread_started.set()
            thread_running.wait()
        
        bg_thread = threading.Thread(target=background_thread)
        bg_thread.start()
        thread_started.wait(timeout=1.0)
        
        try:
            # Call run_subprocess_safe 20 times with ffmpeg
            # This would crash with fork() if not using spawn
            for i in range(20):
                result = run_subprocess_safe(
                    [ffmpeg_path, "-version"],
                    timeout=5.0,
                    text=True
                )
                
                # Verify we got a result (either success or error, but no crash)
                self.assertIsNotNone(result)
                self.assertIn('success', result)
                self.assertIn('returncode', result)
                
                # If successful, ffmpeg -version should return 0
                if result['success']:
                    self.assertEqual(result['returncode'], 0)
                    self.assertIn('ffmpeg', result['stdout'].lower())
                    self.assertFalse(result['is_signal_kill'])
                
                # Verify no signal kill (parent process should not crash)
                self.assertFalse(result.get('is_signal_kill', False),
                               f"Process was killed by signal on iteration {i}: {result.get('signal_name')}")
        
        finally:
            # Clean up background thread
            thread_running.set()
            bg_thread.join(timeout=2.0)
    
    def test_run_subprocess_safe_with_cwd(self):
        """Test subprocess execution with custom working directory"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_subprocess_safe(
                ["pwd"],
                timeout=5.0,
                cwd=tmpdir,
                text=True
            )
            
            self.assertTrue(result['success'])
            self.assertEqual(result['returncode'], 0)
            self.assertIn(tmpdir, result['stdout'])
    
    def test_run_subprocess_safe_with_env(self):
        """Test subprocess execution with custom environment"""
        result = run_subprocess_safe(
            ["sh", "-c", "echo $TEST_VAR"],
            timeout=5.0,
            env={"TEST_VAR": "test_value"},
            text=True
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['stdout'].strip(), "test_value")
    
    def test_run_subprocess_safe_text_mode(self):
        """Test subprocess execution in text mode vs bytes mode"""
        # Text mode
        result_text = run_subprocess_safe(
            ["echo", "test"],
            timeout=5.0,
            text=True
        )
        self.assertIsInstance(result_text['stdout'], str)
        
        # Bytes mode (default)
        result_bytes = run_subprocess_safe(
            ["echo", "test"],
            timeout=5.0,
            text=False
        )
        self.assertIsInstance(result_bytes['stdout'], bytes)


if __name__ == '__main__':
    unittest.main()
