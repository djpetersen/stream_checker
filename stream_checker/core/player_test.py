"""Phase 2: Player connectivity testing"""

import time
import multiprocessing
import platform
import os
from typing import Dict, Any, Optional
import logging

from stream_checker.utils.multiprocessing_utils import (
    cleanup_multiprocessing_queue,
    cleanup_multiprocessing_process,
    ensure_spawn_method,
    run_process_with_queue
)
from stream_checker.utils.subprocess_utils import run_subprocess_safe

logger = logging.getLogger("stream_checker")

# Try to import vlc, but don't fail if it's not available
try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError) as e:
    VLC_AVAILABLE = False
    logger.debug(f"python-vlc not available: {e}")


def _run_vlc_worker(queue, cmd, url, playback_duration, total_timeout):
    """Worker function for VLC subprocess - uses run_subprocess_safe for platform-agnostic safety"""
    import time
    start_time = time.time()
    result = None
    
    try:
        # Build full command with URL
        full_cmd = cmd + [url]
        
        # Use run_subprocess_safe for platform-agnostic subprocess execution
        # VLC will exit after --run-time duration, so timeout should be slightly longer
        subprocess_result = run_subprocess_safe(
            full_cmd,
            timeout=total_timeout,
            text=False
        )
        
        elapsed_time = time.time() - start_time
        
        # Convert run_subprocess_safe result format to worker result format
        if subprocess_result.get('success', False):
            result = {
                'success': True,
                'returncode': subprocess_result.get('returncode'),
                'stdout': subprocess_result.get('stdout'),
                'stderr': subprocess_result.get('stderr'),
                'elapsed_time': elapsed_time
            }
            # Check if it was a timeout
            if subprocess_result.get('error') == 'timeout':
                result['timeout'] = True
        else:
            # Handle errors from run_subprocess_safe
            error_msg = subprocess_result.get('error', 'Unknown error')
            result = {
                'success': False,
                'returncode': subprocess_result.get('returncode'),
                'stdout': subprocess_result.get('stdout'),
                'stderr': subprocess_result.get('stderr'),
                'error': error_msg,
                'elapsed_time': elapsed_time
            }
    except Exception as e:
        elapsed_time = time.time() - start_time
        result = {
            'success': False,
            'returncode': None,
            'stdout': None,
            'stderr': None,
            'error': str(e),
            'elapsed_time': elapsed_time
        }
    finally:
        # Always try to put result in queue, even if it's None
        try:
            if result is not None:
                queue.put(result)
            else:
                # Fallback if result was never set
                elapsed_time = time.time() - start_time
                queue.put({
                    'success': False,
                    'returncode': None,
                    'stdout': None,
                    'stderr': None,
                    'error': 'Unknown error in VLC worker',
                    'elapsed_time': elapsed_time
                })
        except Exception as e:
            # If queue.put fails (e.g., queue is closed), we can't do anything
            # The parent will timeout and clean up
            logger.debug(f"Error putting result in queue in _run_vlc_worker: {e}")


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
        self._current_media = None  # Track media object for explicit cleanup
        self._event_manager = None  # Track event manager to detach callbacks
        self._callbacks_detached = False  # Flag to prevent callback access after release
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
            self._event_manager = self.media_player.event_manager()
            self._event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
            self._event_manager.event_attach(vlc.EventType.MediaPlayerBuffering, self._on_buffering)
            self._event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
            self._event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end)
            
            # Create media object
            media = self.vlc_instance.media_new(url)
            if not media:
                result["status"] = "error"
                result["errors"].append("Failed to create media object")
                return result
            
            # Store media reference for explicit cleanup
            self._current_media = media
            
            # Start playback
            start_time = time.time()
            self.media_player.set_media(media)
            self.media_player.play()
            
            # Wait for connection
            connection_start = time.time()
            max_wait = self.connection_timeout
            waited = 0
            
            while waited < max_wait:
                # Defensive check - media_player might be released by callback
                if not self.media_player or self._callbacks_detached:
                    break
                try:
                    state = self.media_player.get_state()
                except (AttributeError, RuntimeError, Exception):
                    # Media player may have been released
                    break
                
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
                if self.media_player:
                    self.media_player.stop()
                return result
            
            # Play for specified duration
            playback_start = time.time()
            while (time.time() - playback_start) < self.playback_duration:
                # Defensive check - media_player might be released by callback
                if not self.media_player or self._callbacks_detached:
                    break
                try:
                    state = self.media_player.get_state()
                except (AttributeError, RuntimeError, Exception):
                    # Media player may have been released
                    break
                
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
            
            # Detach callbacks BEFORE stopping/releasing to prevent async callback crashes
            if self._event_manager and not self._callbacks_detached:
                try:
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerPlaying)
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerBuffering)
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerEncounteredError)
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                except Exception:
                    pass  # Ignore errors during detach
                self._callbacks_detached = True
                self._event_manager = None
            
            # Stop playback
            if self.media_player:
                try:
                    self.media_player.stop()
                except Exception:
                    pass  # Ignore errors during stop
            
            # Clean up - set to None after release to prevent double-free in finally block
            if self.media_player:
                try:
                    self.media_player.release()
                except Exception:
                    pass  # Ignore errors during release
                self.media_player = None
            if self._current_media:
                try:
                    self._current_media.release()
                except Exception:
                    pass  # Media may already be released by player
                self._current_media = None
            if self.vlc_instance:
                self.vlc_instance.release()
                self.vlc_instance = None
            
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
            # Ensure cleanup - set to None after release to prevent any double-free issues
            try:
                # Detach callbacks first to prevent async callback crashes
                if self._event_manager and not self._callbacks_detached:
                    try:
                        self._event_manager.event_detach(vlc.EventType.MediaPlayerPlaying)
                        self._event_manager.event_detach(vlc.EventType.MediaPlayerBuffering)
                        self._event_manager.event_detach(vlc.EventType.MediaPlayerEncounteredError)
                        self._event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                    except Exception:
                        pass  # Ignore errors during detach
                    self._callbacks_detached = True
                    self._event_manager = None
                
                if self.media_player:
                    try:
                        self.media_player.stop()
                    except Exception:
                        pass  # Ignore errors during stop
                    try:
                        self.media_player.release()
                    except Exception:
                        pass  # Ignore errors during release
                    self.media_player = None
                if self._current_media:
                    try:
                        self._current_media.release()
                    except Exception:
                        pass  # Media may already be released by player
                    self._current_media = None
                if self.vlc_instance:
                    try:
                        self.vlc_instance.release()
                    except Exception:
                        pass  # Ignore errors during release
                    self.vlc_instance = None
            except Exception as e:
                logger.debug(f"Error during VLC cleanup: {e}")
        
        return result
    
    def _on_playing(self, event):
        """Callback when playback starts"""
        # Defensive check - don't access if callbacks are detached
        if self._callbacks_detached:
            return
        try:
            self._playback_started = True
            logger.debug("VLC playback started")
        except Exception:
            pass  # Ignore errors in callback
    
    def _on_buffering(self, event):
        """Callback when buffering occurs"""
        # Defensive check - don't access if callbacks are detached
        if self._callbacks_detached:
            return
        try:
            self._buffering_events += 1
            logger.debug(f"VLC buffering event #{self._buffering_events}")
        except Exception:
            pass  # Ignore errors in callback
    
    def _on_error(self, event):
        """Callback when error occurs"""
        # Defensive check - don't access if callbacks are detached
        if self._callbacks_detached:
            return
        try:
            error_msg = "VLC playback error"
            self._playback_errors.append(error_msg)
            logger.error(f"VLC error: {error_msg}")
        except Exception:
            pass  # Ignore errors in callback
    
    def _on_end(self, event):
        """Callback when playback ends"""
        # Defensive check - don't access if callbacks are detached
        if self._callbacks_detached:
            return
        try:
            self._playback_completed = True
            logger.debug("VLC playback ended")
        except Exception:
            pass  # Ignore errors in callback


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
                    ok, result = run_process_with_queue(
                        target=_run_subprocess_worker,
                        args=(["which", "vlc"], 2),
                        join_timeout=5,
                        get_timeout=0.5,
                        name="_find_vlc_command.which"
                    )
                    if ok and result and result.get('success') and result.get('returncode') == 0:
                        vlc_path = result.get('stdout').decode().strip() if result.get('stdout') else None
                        if vlc_path:
                            paths.insert(0, vlc_path)
                else:
                    which_result = run_subprocess_safe(["which", "vlc"], timeout=2.0, text=False)
                    if which_result.get('success') and which_result.get('returncode') == 0:
                        vlc_path = which_result.get('stdout').decode().strip() if which_result.get('stdout') else None
                        if vlc_path:
                            paths.insert(0, vlc_path)
            except (FileNotFoundError, OSError, Exception):
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
                    from stream_checker.core.audio_analysis import _run_subprocess_worker
                    ok, result = run_process_with_queue(
                        target=_run_subprocess_worker,
                        args=([path, "--version"], 5),
                        join_timeout=7,
                        get_timeout=0.5,
                        name="_find_vlc_command"
                    )
                    if ok and result and result.get('success') and result.get('returncode') == 0:
                        return path
                else:
                    result = run_subprocess_safe(
                        [path, "--version"],
                        timeout=5.0,
                        text=False
                    )
                    if result.get('success') and result.get('returncode') == 0:
                        return path
            except (FileNotFoundError, Exception):
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
            # Run VLC with timeout - use platform-agnostic safe subprocess helper
            start_time = time.time()
            total_timeout = self.connection_timeout + self.playback_duration + 10  # Add buffer
            
            # Build VLC command - VLC will exit after --run-time duration
            vlc_cmd_list = [
                vlc_cmd,
                "--intf", "dummy",
                "--quiet",
                "--no-video",
                "--run-time", str(self.playback_duration),
                "--network-caching=3000",
                url
            ]
            
            # Use multiprocessing queue for VLC execution (platform-agnostic)
            ok, vlc_result = run_process_with_queue(
                target=_run_vlc_worker,
                args=(vlc_cmd_list, url, self.playback_duration, total_timeout),
                join_timeout=total_timeout + 10,
                get_timeout=0.5,
                name="PlayerTesterFallback.check"
            )
            
            if not ok or not vlc_result:
                result["status"] = "error"
                if not ok:
                    result["errors"].append("VLC process timeout")
                else:
                    result["errors"].append("VLC process result queue is empty")
                return result
            
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
                    error_text = stderr.decode('utf-8', errors='ignore') if isinstance(stderr, bytes) else str(stderr)
                    if error_text and "error" not in error_text.lower()[:100]:  # Only if it's a real error
                        result["error_details"] = error_text[:500]  # Limit error text
        
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
