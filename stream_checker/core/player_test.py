"""Phase 2: Player connectivity testing"""

import time
import threading
import subprocess
import multiprocessing
import platform
import os
from typing import Dict, Any, Optional
import logging

# Use spawn method on macOS to avoid fork issues
# Defer setting until actually needed to avoid conflicts in Flask/multi-threaded environments
_mp_start_method_set = False

def _ensure_spawn_method():
    """Ensure multiprocessing uses spawn method on macOS - call only when needed"""
    global _mp_start_method_set
    if _mp_start_method_set:
        return
    
    if hasattr(multiprocessing, 'get_start_method'):
        try:
            if platform.system() != "Darwin":
                _mp_start_method_set = True
                return
            
            current_method = multiprocessing.get_start_method(allow_none=True)
            if current_method is None:
                # Not set yet, set it to spawn on macOS
                try:
                    multiprocessing.set_start_method('spawn')
                    _mp_start_method_set = True
                except RuntimeError:
                    # Can't set - might already be set in another process
                    pass
            elif current_method == 'spawn':
                _mp_start_method_set = True
            else:
                # Try to change it, but don't force (may fail in some contexts)
                try:
                    multiprocessing.set_start_method('spawn', force=True)
                    _mp_start_method_set = True
                except RuntimeError:
                    # Already set or can't change - this is OK
                    pass
        except RuntimeError:
            # Already set or can't change - this is OK
            pass

logger = logging.getLogger("stream_checker")

# Try to import vlc, but don't fail if it's not available
try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError) as e:
    VLC_AVAILABLE = False
    logger.debug(f"python-vlc not available: {e}")


def _run_vlc_worker(queue, cmd, url, playback_duration, total_timeout):
    """Worker function for VLC subprocess - runs in separate process to avoid fork crash"""
    import time
    process = None
    try:
        process = subprocess.Popen(
            cmd + [url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        
        start_time = time.time()
        
        # Wait for process with timeout
        try:
            stdout, stderr = process.communicate(timeout=total_timeout)
            return_code = process.returncode
            elapsed_time = time.time() - start_time
            queue.put({
                'success': True,
                'returncode': return_code,
                'stdout': stdout,
                'stderr': stderr,
                'elapsed_time': elapsed_time
            })
        except subprocess.TimeoutExpired:
            # Try graceful termination first
            try:
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                return_code = process.returncode
                elapsed_time = time.time() - start_time
                queue.put({
                    'success': True,
                    'returncode': return_code,
                    'stdout': stdout,
                    'stderr': stderr,
                    'timeout': True,
                    'elapsed_time': elapsed_time
                })
            except subprocess.TimeoutExpired:
                # Force kill if terminate didn't work
                process.kill()
                process.wait()
                elapsed_time = time.time() - start_time
                queue.put({
                    'success': False,
                    'returncode': None,
                    'stdout': None,
                    'stderr': None,
                    'error': 'timeout',
                    'elapsed_time': elapsed_time
                })
    except Exception as e:
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        queue.put({
            'success': False,
            'returncode': None,
            'stdout': None,
            'stderr': None,
            'error': str(e),
            'elapsed_time': elapsed_time
        })
    finally:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception as e:
                logger.debug(f"Error terminating VLC process in worker: {e}")
                try:
                    process.kill()
                    process.wait()
                except Exception as e2:
                    logger.debug(f"Error killing VLC process in worker: {e2}")


class PlayerTester:
    """Test stream playback with VLC player"""
    
    def __init__(
        self,
        playback_duration: int = 5,
        connection_timeout: int = 30
    ):
        if playback_duration <= 0:
            raise ValueError("playback_duration must be positive")
        if connection_timeout <= 0:
            raise ValueError("connection_timeout must be positive")
        self.playback_duration = playback_duration
        self.connection_timeout = connection_timeout
        self.vlc_instance = None
        self.media_player = None
        self._playback_errors = []
        self._connection_time = None
        self._buffering_events = 0
        self._playback_started = False
        self._playback_completed = False
    
    def check(self, url: str) -> Dict[str, Any]:
        """
        Test stream playback with VLC
        
        Args:
            url: Stream URL to test
            
        Returns:
            Dictionary with Phase 2 results
        """
        result = {
            "status": "unknown",
            "connection_time_ms": None,
            "playback_duration_seconds": 0,
            "errors": [],
            "buffering_events": 0,
            "format_supported": False,
            "error_details": None
        }
        
        try:
            # Create VLC instance
            self.vlc_instance = vlc.Instance([
                '--intf', 'dummy',  # No interface
                '--quiet',  # Suppress output
                '--no-video',  # Audio only
                '--aout', 'dummy',  # Dummy audio output
                '--network-caching=3000',  # 3 second network cache
            ])
            
            if not self.vlc_instance:
                result["status"] = "error"
                result["errors"].append("Failed to create VLC instance")
                result["error_details"] = "VLC may not be installed or accessible"
                return result
            
            # Create media player
            self.media_player = self.vlc_instance.media_player_new()
            
            if not self.media_player:
                result["status"] = "error"
                result["errors"].append("Failed to create VLC media player")
                return result
            
            # Set up event callbacks
            event_manager = self.media_player.event_manager()
            event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
            event_manager.event_attach(vlc.EventType.MediaPlayerBuffering, self._on_buffering)
            event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
            event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end)
            
            # Create media object
            media = self.vlc_instance.media_new(url)
            if not media:
                result["status"] = "error"
                result["errors"].append("Failed to create media object")
                return result
            
            # Start playback
            start_time = time.time()
            self.media_player.set_media(media)
            self.media_player.play()
            
            # Wait for connection
            connection_start = time.time()
            max_wait = self.connection_timeout
            waited = 0
            
            while waited < max_wait:
                state = self.media_player.get_state()
                
                if state == vlc.State.Playing:
                    self._connection_time = (time.time() - connection_start) * 1000
                    self._playback_started = True
                    result["connection_time_ms"] = int(self._connection_time)
                    result["status"] = "success"
                    result["format_supported"] = True
                    break
                elif state == vlc.State.Error:
                    result["status"] = "error"
                    result["errors"].append("VLC reported playback error")
                    result["format_supported"] = False
                    break
                elif state == vlc.State.Ended:
                    result["status"] = "error"
                    result["errors"].append("Stream ended immediately")
                    break
                
                time.sleep(0.1)
                waited += 0.1
            
            if not self._playback_started:
                result["status"] = "timeout"
                result["errors"].append(f"Connection timeout after {self.connection_timeout} seconds")
                result["error_details"] = f"Stream did not start playing within {self.connection_timeout} seconds"
                self.media_player.stop()
                return result
            
            # Play for specified duration
            playback_start = time.time()
            while (time.time() - playback_start) < self.playback_duration:
                state = self.media_player.get_state()
                
                if state == vlc.State.Error:
                    result["status"] = "error"
                    result["errors"].append("Playback error during test")
                    break
                elif state == vlc.State.Ended:
                    result["status"] = "error"
                    result["errors"].append("Stream ended unexpectedly")
                    break
                elif state == vlc.State.Stopped:
                    result["status"] = "error"
                    result["errors"].append("Playback stopped unexpectedly")
                    break
                
                time.sleep(0.5)
            
            # Calculate actual playback duration
            actual_duration = time.time() - playback_start
            result["playback_duration_seconds"] = round(actual_duration, 2)
            result["buffering_events"] = self._buffering_events
            
            # Stop playback
            self.media_player.stop()
            
            # Clean up
            self.media_player.release()
            self.vlc_instance.release()
            
        except vlc.VLCException as e:
            result["status"] = "error"
            result["errors"].append(f"VLC exception: {str(e)}")
            result["error_details"] = str(e)
            logger.error(f"VLC exception: {e}")
        
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"Unexpected error: {str(e)}")
            result["error_details"] = str(e)
            logger.error(f"Player test error: {e}")
        
        finally:
            # Ensure cleanup
            try:
                if self.media_player:
                    self.media_player.stop()
                    self.media_player.release()
                if self.vlc_instance:
                    self.vlc_instance.release()
            except Exception as e:
                logger.debug(f"Error during VLC cleanup: {e}")
        
        return result
    
    def _on_playing(self, event):
        """Callback when playback starts"""
        # Note: VLC callbacks are called from VLC's thread, but VLC handles thread safety
        # These callbacks are typically single-threaded per instance
        self._playback_started = True
        logger.debug("VLC playback started")
    
    def _on_buffering(self, event):
        """Callback when buffering occurs"""
        # Note: VLC callbacks are thread-safe within VLC's context
        self._buffering_events += 1
        logger.debug(f"VLC buffering event #{self._buffering_events}")
    
    def _on_error(self, event):
        """Callback when error occurs"""
        error_msg = "VLC playback error"
        self._playback_errors.append(error_msg)
        logger.error(f"VLC error: {error_msg}")
    
    def _on_end(self, event):
        """Callback when playback ends"""
        self._playback_completed = True
        logger.debug("VLC playback ended")


class PlayerTesterFallback:
    """
    Fallback player tester using command-line VLC
    Used if python-vlc is not available or fails
    """
    
    def __init__(
        self,
        playback_duration: int = 5,
        connection_timeout: int = 30
    ):
        if playback_duration <= 0:
            raise ValueError("playback_duration must be positive")
        if connection_timeout <= 0:
            raise ValueError("connection_timeout must be positive")
        self.playback_duration = playback_duration
        self.connection_timeout = connection_timeout
    
    def _find_vlc_command(self) -> Optional[str]:
        """Find VLC command-line executable"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            paths = [
                "/Applications/VLC.app/Contents/MacOS/VLC",
                "/usr/local/bin/vlc",
                "/opt/homebrew/bin/vlc",
                "vlc"
            ]
            # Also check if VLC is in PATH via which
            # Use multiprocessing on macOS to avoid fork crash
            try:
                if platform.system() == "Darwin":
                    from stream_checker.core.audio_analysis import _run_subprocess_worker
                    import queue as queue_module
                    mp_queue = multiprocessing.Queue()
                    process_obj = multiprocessing.Process(
                        target=_run_subprocess_worker,
                        args=(mp_queue, ["which", "vlc"], 2)
                    )
                    process_obj.start()
                    process_obj.join(timeout=5)
                    if process_obj.is_alive():
                        process_obj.terminate()
                        process_obj.join()
                    if not mp_queue.empty():
                        result = mp_queue.get()
                        if result.get('success') and result.get('returncode') == 0:
                            vlc_path = result.get('stdout').decode().strip() if result.get('stdout') else None
                            if vlc_path:
                                paths.insert(0, vlc_path)
                else:
                    which_result = subprocess.run(["which", "vlc"], capture_output=True, timeout=2)
                    if which_result.returncode == 0:
                        vlc_path = which_result.stdout.decode().strip()
                        if vlc_path:
                            paths.insert(0, vlc_path)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, Exception):
                pass
        elif system == "Linux":
            paths = ["/usr/bin/vlc", "/usr/local/bin/vlc", "vlc"]
        elif system == "Windows":
            paths = [
                "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",
                "C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe",
                "vlc.exe"
            ]
        else:
            paths = ["vlc"]
        
        for path in paths:
            try:
                if system == "Darwin":
                    # On macOS, use multiprocessing to avoid fork crash
                    _ensure_spawn_method()  # Ensure spawn method is set before creating queue
                    from stream_checker.core.audio_analysis import _run_subprocess_worker
                    mp_queue = None
                    process_obj = None
                    try:
                        mp_queue = multiprocessing.Queue()
                        process_obj = multiprocessing.Process(
                            target=_run_subprocess_worker,
                            args=(mp_queue, [path, "--version"], 5)
                        )
                        process_obj.start()
                        process_obj.join(timeout=7)
                        if process_obj.is_alive():
                            process_obj.terminate()
                            process_obj.join(timeout=2)
                            if process_obj.is_alive():
                                process_obj.kill()
                                process_obj.join()
                            continue
                        if not mp_queue.empty():
                            result = mp_queue.get()
                            if result.get('success') and result.get('returncode') == 0:
                                return path
                    finally:
                        # Clean up resources - CRITICAL to prevent semaphore leaks
                        try:
                            if process_obj and process_obj.is_alive():
                                process_obj.terminate()
                                process_obj.join(timeout=1)
                                if process_obj.is_alive():
                                    process_obj.kill()
                                    process_obj.join()
                        except Exception as e:
                            logger.debug(f"Error cleaning up process in _find_vlc_command: {e}")
                        try:
                            if mp_queue is not None:
                                # CRITICAL: Properly drain and close queue to prevent semaphore leaks
                                try:
                                    # Get any remaining items (with timeout to avoid blocking)
                                    import queue as queue_module
                                    while True:
                                        try:
                                            mp_queue.get(timeout=0.1)
                                        except queue_module.Empty:
                                            break
                                        except Exception as e:
                                            logger.debug(f"Error draining queue in _find_vlc_command: {e}")
                                            break
                                except Exception as e:
                                    logger.debug(f"Error in queue drain loop in _find_vlc_command: {e}")
                                try:
                                    mp_queue.close()
                                except Exception as e:
                                    logger.debug(f"Error closing queue in _find_vlc_command: {e}")
                                try:
                                    mp_queue.join_thread(timeout=2)
                                except Exception as e:
                                    logger.debug(f"Error joining queue thread in _find_vlc_command: {e}")
                        except Exception as e:
                            logger.debug(f"Error in queue cleanup in _find_vlc_command: {e}")
                else:
                    result = subprocess.run(
                        [path, "--version"],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        return path
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                continue
        
        return None
    
    def check(self, url: str) -> Dict[str, Any]:
        """Test stream using command-line VLC"""
        result = {
            "status": "unknown",
            "connection_time_ms": None,
            "playback_duration_seconds": 0,
            "errors": [],
            "buffering_events": 0,
            "format_supported": False,
            "error_details": None,
            "method": "command_line"
        }
        
        vlc_cmd = self._find_vlc_command()
        if not vlc_cmd:
            result["status"] = "error"
            result["errors"].append("VLC not found")
            result["error_details"] = "VLC command-line tool not found in PATH"
            return result
        
        try:
            # Run VLC with timeout
            start_time = time.time()
            total_timeout = self.connection_timeout + self.playback_duration + 10  # Add buffer
            
            # On macOS, use multiprocessing to avoid fork crash
            # On other platforms, subprocess is safe
            if platform.system() == "Darwin":
                # Use multiprocessing for VLC on macOS
                _ensure_spawn_method()  # Ensure spawn method is set before creating queue
                vlc_cmd_list = [
                    vlc_cmd,
                    "--intf", "dummy",
                    "--quiet",
                    "--no-video",
                    "--run-time", str(self.playback_duration),
                    "--network-caching=3000"
                ]
                
                mp_queue = None
                process_obj = None
                try:
                    mp_queue = multiprocessing.Queue()
                    process_obj = multiprocessing.Process(
                        target=_run_vlc_worker,
                        args=(mp_queue, vlc_cmd_list, url, self.playback_duration, total_timeout)
                    )
                    process_obj.start()
                    process_obj.join(timeout=total_timeout + 10)
                    
                    if process_obj.is_alive():
                        process_obj.terminate()
                        process_obj.join(timeout=2)
                        if process_obj.is_alive():
                            process_obj.kill()
                            process_obj.join()
                        result["status"] = "error"
                        result["errors"].append("VLC process timeout")
                        return result
                    
                    if mp_queue.empty():
                        result["status"] = "error"
                        result["errors"].append("VLC process result queue is empty")
                        return result
                    
                    vlc_result = mp_queue.get()
                    return_code = vlc_result.get('returncode')
                    stdout = vlc_result.get('stdout')
                    stderr = vlc_result.get('stderr')
                    elapsed_time = vlc_result.get('elapsed_time', 0)
                    
                    result["playback_duration_seconds"] = round(elapsed_time, 2)
                    
                    # Check return code
                    if return_code == 0 or return_code == -15:  # -15 is SIGTERM (normal termination)
                        result["status"] = "success"
                        result["format_supported"] = True
                        # Estimate connection time (first 20% of total time, max 5 seconds)
                        connection_time = min(elapsed_time * 0.2, 5.0)
                        result["connection_time_ms"] = int(connection_time * 1000)
                    else:
                        result["status"] = "error"
                        if return_code != -15:  # Don't add error for SIGTERM
                            result["errors"].append(f"VLC returned error code {return_code}")
                        if stderr:
                            error_text = stderr.decode('utf-8', errors='ignore')
                            if error_text and "error" not in error_text.lower()[:100]:  # Only if it's a real error
                                result["error_details"] = error_text[:500]  # Limit error text
                finally:
                    # Clean up resources - CRITICAL to prevent semaphore leaks
                    try:
                        if process_obj and process_obj.is_alive():
                            process_obj.terminate()
                            process_obj.join(timeout=1)
                            if process_obj.is_alive():
                                process_obj.kill()
                                process_obj.join()
                    except Exception as e:
                        logger.debug(f"Error cleaning up process in PlayerTesterFallback.check: {e}")
                    try:
                        if mp_queue is not None:
                            # CRITICAL: Properly drain and close queue to prevent semaphore leaks
                            try:
                                # Get any remaining items (with timeout to avoid blocking)
                                import queue as queue_module
                                while True:
                                    try:
                                        mp_queue.get(timeout=0.1)
                                    except queue_module.Empty:
                                        break
                                    except Exception as e:
                                        logger.debug(f"Error draining queue in PlayerTesterFallback.check: {e}")
                                        break
                            except Exception as e:
                                logger.debug(f"Error in queue drain loop in PlayerTesterFallback.check: {e}")
                            try:
                                mp_queue.close()
                            except Exception as e:
                                logger.debug(f"Error closing queue in PlayerTesterFallback.check: {e}")
                            try:
                                mp_queue.join_thread(timeout=2)
                            except Exception as e:
                                logger.debug(f"Error joining queue thread in PlayerTesterFallback.check: {e}")
                    except Exception as e:
                        logger.debug(f"Error in queue cleanup in PlayerTesterFallback.check: {e}")
            else:
                # On other platforms, subprocess is safe
                process = subprocess.Popen(
                    [
                        vlc_cmd,
                        "--intf", "dummy",
                        "--quiet",
                        "--no-video",
                        "--run-time", str(self.playback_duration),
                        "--network-caching=3000",
                        url
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL
                )
                
                # Start a timer to stop VLC after playback duration
                def stop_vlc():
                    time.sleep(self.playback_duration + 2)  # Add 2 seconds buffer
                    if process.poll() is None:  # Process still running
                        try:
                            process.terminate()
                        except (OSError, ProcessLookupError) as e:
                            logger.debug(f"Error terminating VLC process: {e}")
                
                timer_thread = threading.Thread(target=stop_vlc, daemon=True)
                timer_thread.start()
                
                # Wait for process with timeout
                try:
                    stdout, stderr = process.communicate(timeout=total_timeout)
                    return_code = process.returncode
                    
                    elapsed_time = time.time() - start_time
                    result["playback_duration_seconds"] = round(elapsed_time, 2)
                    
                    # Check return code
                    if return_code == 0 or return_code == -15:  # -15 is SIGTERM (normal termination)
                        result["status"] = "success"
                        result["format_supported"] = True
                        # Estimate connection time (first 20% of total time, max 5 seconds)
                        connection_time = min(elapsed_time * 0.2, 5.0)
                        result["connection_time_ms"] = int(connection_time * 1000)
                    else:
                        result["status"] = "error"
                        if return_code != -15:  # Don't add error for SIGTERM
                            result["errors"].append(f"VLC returned error code {return_code}")
                        if stderr:
                            error_text = stderr.decode('utf-8', errors='ignore')
                            if error_text and "error" not in error_text.lower()[:100]:  # Only if it's a real error
                                result["error_details"] = error_text[:500]  # Limit error text
                except subprocess.TimeoutExpired:
                    # Try graceful termination first
                    try:
                        process.terminate()
                        stdout, stderr = process.communicate(timeout=5)
                        return_code = process.returncode
                        elapsed_time = time.time() - start_time
                        result["playback_duration_seconds"] = round(elapsed_time, 2)
                        
                        if return_code == 0:
                            result["status"] = "success"
                            result["format_supported"] = True
                        else:
                            result["status"] = "error"
                            result["errors"].append("Process timeout (terminated)")
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        process.kill()
                        stdout, stderr = process.communicate()
                        return_code = -1
                        elapsed_time = time.time() - start_time
                        result["playback_duration_seconds"] = round(elapsed_time, 2)
                        result["status"] = "error"
                        result["errors"].append("Process timeout (killed)")
        
        except FileNotFoundError:
            result["status"] = "error"
            result["errors"].append("VLC executable not found")
            result["error_details"] = "VLC command-line tool not found"
        
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"Unexpected error: {str(e)}")
            result["error_details"] = str(e)
            logger.error(f"Fallback player test error: {e}")
        
        return result


def test_player_connectivity(url: str, playback_duration: int = 5, connection_timeout: int = 30) -> Dict[str, Any]:
    """
    Test player connectivity with automatic fallback
    
    Args:
        url: Stream URL to test
        playback_duration: Duration to play stream (seconds)
        connection_timeout: Maximum time to wait for connection (seconds)
        
    Returns:
        Dictionary with player test results
    """
    # Try python-vlc first (if available)
    if VLC_AVAILABLE:
        try:
            tester = PlayerTester(playback_duration, connection_timeout)
            result = tester.check(url)
            result["method"] = "python_vlc"
            return result
        except Exception as e:
            logger.warning(f"python-vlc test failed, trying fallback: {e}")
    else:
        logger.debug("python-vlc not available, using command-line fallback")
    
    # Fallback to command-line VLC
    try:
        tester = PlayerTesterFallback(playback_duration, connection_timeout)
        result = tester.check(url)
        return result
    except Exception as e:
        logger.error(f"Fallback player test also failed: {e}")
        return {
            "status": "error",
            "connection_time_ms": None,
            "playback_duration_seconds": 0,
            "errors": [f"Both player test methods failed: {str(e)}"],
            "buffering_events": 0,
            "format_supported": False,
            "error_details": str(e),
            "method": "none"
        }
