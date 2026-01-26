"""Phase 3: Audio analysis - silence and error detection"""

import os
import subprocess
import tempfile
import multiprocessing
import numpy as np
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger("stream_checker")

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
            import platform
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


def _run_subprocess_safe(cmd, timeout, stdout, stderr):
    """
    Run subprocess in a spawned process to avoid fork issues on macOS.
    This function runs in a separate process and returns the result via a queue.
    """
    try:
        process = subprocess.run(
            cmd,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout
        )
        return {
            'returncode': process.returncode,
            'stdout': process.stdout,
            'stderr': process.stderr,
            'success': True
        }
    except subprocess.TimeoutExpired as e:
        return {
            'returncode': None,
            'stdout': None,
            'stderr': e.stderr if hasattr(e, 'stderr') else None,
            'success': False,
            'error': 'timeout'
        }
    except Exception as e:
        return {
            'returncode': None,
            'stdout': None,
            'stderr': None,
            'success': False,
            'error': str(e)
        }


def _run_subprocess_worker(queue, cmd, timeout):
    """Worker function for multiprocessing - must be at module level for pickling"""
    try:
        result = _run_subprocess_safe(cmd, timeout, subprocess.PIPE, subprocess.PIPE)
        queue.put(result)
    except Exception as e:
        # Put error result in queue so caller knows something went wrong
        queue.put({
            'success': False,
            'returncode': None,
            'stdout': None,
            'stderr': None,
            'error': str(e)
        })
    # Note: Don't close queue here - it's managed by the caller


class AudioAnalyzer:
    """Analyze audio streams for silence, errors, and quality metrics"""
    
    def __init__(
        self,
        sample_duration: int = 10,
        silence_threshold_db: float = -40.0,
        silence_min_duration: float = 2.0
    ):
        if sample_duration <= 0:
            raise ValueError("sample_duration must be positive")
        if not (-100 <= silence_threshold_db <= 0):
            raise ValueError("silence_threshold_db must be between -100 and 0")
        if silence_min_duration <= 0:
            raise ValueError("silence_min_duration must be positive")
        self.sample_duration = sample_duration
        self.silence_threshold_db = silence_threshold_db
        self.silence_min_duration = silence_min_duration
    
    def analyze(self, url: str) -> Dict[str, Any]:
        """
        Analyze audio stream for silence, errors, and quality
        
        Args:
            url: Stream URL to analyze
            
        Returns:
            Dictionary with audio analysis results
        """
        result = {
            "sample_duration_seconds": self.sample_duration,
            "silence_detection": {
                "silence_detected": False,
                "silence_percentage": 0.0,
                "silence_periods": [],
                "threshold_db": self.silence_threshold_db
            },
            "error_detection": {
                "error_detected": False,
                "error_messages": [],
                "repetitive_pattern_detected": False
            },
            "audio_quality": {
                "average_volume_db": None,
                "peak_volume_db": None,
                "dynamic_range_db": None,
                "clipping_detected": False
            }
        }
        
        # Download audio sample
        audio_file = self._download_audio_sample(url)
        if not audio_file:
            result["error"] = "Failed to download audio sample"
            return result
        
        try:
            # Load audio using ffmpeg to convert to raw PCM
            audio_data, sample_rate, channels = self._load_audio_raw(audio_file)
            if audio_data is None:
                result["error"] = "Failed to load audio data"
                return result
            
            # Analyze audio
            self._detect_silence(audio_data, sample_rate, channels, result)
            self._analyze_quality(audio_data, sample_rate, channels, result)
            self._detect_errors(audio_data, sample_rate, channels, result)
            
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            result["error"] = str(e)
        
        finally:
            # Clean up temp file
            try:
                if audio_file and os.path.exists(audio_file):
                    os.unlink(audio_file)
            except (OSError, PermissionError) as e:
                logger.debug(f"Could not delete temp file {audio_file}: {e}")
        
        return result
    
    def _find_ffmpeg(self) -> Optional[str]:
        """Find ffmpeg executable"""
        # Check common locations
        paths = ["ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]
        for path in paths:
            try:
                # Use multiprocessing to avoid fork issues
                import platform
                if platform.system() == "Darwin":
                    # On macOS, use multiprocessing with spawn
                    _ensure_spawn_method()  # Ensure spawn method is set before creating queue
                    queue = None
                    process_obj = None
                    try:
                        queue = multiprocessing.Queue()
                        process_obj = multiprocessing.Process(
                            target=_run_subprocess_worker,
                            args=(queue, [path, "-version"], 2)
                        )
                        process_obj.start()
                        process_obj.join(timeout=5)
                        if process_obj.is_alive():
                            process_obj.terminate()
                            process_obj.join(timeout=2)
                            if process_obj.is_alive():
                                process_obj.kill()
                                process_obj.join()
                            continue
                        if not queue.empty():
                            result = queue.get()
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
                            logger.debug(f"Error cleaning up process in _find_ffmpeg: {e}")
                        try:
                            if queue is not None:
                                # CRITICAL: Properly drain and close queue to prevent semaphore leaks
                                try:
                                    # Get any remaining items (with timeout to avoid blocking)
                                    import queue as queue_module
                                    while True:
                                        try:
                                            queue.get(timeout=0.1)
                                        except queue_module.Empty:
                                            break
                                        except Exception as e:
                                            logger.debug(f"Error draining queue in _find_ffmpeg: {e}")
                                            break
                                except Exception as e:
                                    logger.debug(f"Error in queue drain loop in _find_ffmpeg: {e}")
                                try:
                                    queue.close()
                                except Exception as e:
                                    logger.debug(f"Error closing queue in _find_ffmpeg: {e}")
                                try:
                                    queue.join_thread(timeout=2)
                                except Exception as e:
                                    logger.debug(f"Error joining queue thread in _find_ffmpeg: {e}")
                        except Exception as e:
                            logger.debug(f"Error in queue cleanup in _find_ffmpeg: {e}")
                else:
                    # On other platforms, subprocess is safe
                    result = subprocess.run([path, "-version"], capture_output=True, timeout=2)
                    if result.returncode == 0:
                        return path
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                continue
        return None
    
    def _download_audio_sample(self, url: str) -> Optional[str]:
        """Download audio sample using ffmpeg"""
        # Check if ffmpeg is available
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            logger.error("ffmpeg not found in PATH")
            return None
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)
        
        try:
            # Use ffmpeg to download and convert audio
            cmd = [
                ffmpeg_path,
                "-i", url,
                "-t", str(self.sample_duration),  # Duration
                "-acodec", "libmp3lame",  # MP3 codec
                "-ar", "44100",  # Sample rate
                "-ac", "2",  # Stereo
                "-y",  # Overwrite output
                temp_path
            ]
            
            # Run ffmpeg with timeout
            # Use multiprocessing with spawn on macOS to avoid fork issues
            timeout = self.sample_duration + 30  # Add buffer
            import platform
            if platform.system() == "Darwin":
                # On macOS, use multiprocessing with spawn to avoid fork crash
                _ensure_spawn_method()  # Ensure spawn method is set before creating queue
                queue = multiprocessing.Queue()
                process_obj = None
                try:
                    process_obj = multiprocessing.Process(
                        target=_run_subprocess_worker,
                        args=(queue, cmd, timeout)
                    )
                    process_obj.start()
                    process_obj.join(timeout=timeout + 5)
                    if process_obj.is_alive():
                        process_obj.terminate()
                        process_obj.join(timeout=2)
                        if process_obj.is_alive():
                            process_obj.kill()
                            process_obj.join()
                        raise subprocess.TimeoutExpired(cmd, timeout)
                    
                    if queue.empty():
                        raise Exception("Subprocess result queue is empty")
                    
                    result = queue.get()
                    process_returncode = result.get('returncode')
                    process_stderr = result.get('stderr')
                finally:
                    # Clean up resources - CRITICAL to prevent semaphore leaks
                    try:
                        if process_obj and process_obj.is_alive():
                            process_obj.terminate()
                            process_obj.join(timeout=1)
                            if process_obj.is_alive():
                                process_obj.kill()
                                process_obj.join()
                    except Exception:
                        pass
                    try:
                        if queue is not None:
                            # CRITICAL: Properly drain and close queue to prevent semaphore leaks
                            try:
                                # Get any remaining items (with timeout to avoid blocking)
                                import queue as queue_module
                                while True:
                                    try:
                                        queue.get(timeout=0.1)
                                    except queue_module.Empty:
                                        break
                                    except Exception:
                                        break
                            except Exception:
                                pass
                            try:
                                queue.close()
                            except Exception:
                                pass
                            try:
                                queue.join_thread(timeout=2)
                            except Exception:
                                pass
                    except Exception:
                        pass
            else:
                # On other platforms, subprocess is safe
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout
                )
                process_returncode = process.returncode
                process_stderr = process.stderr
            
            if process_returncode == 0 and os.path.exists(temp_path):
                file_size = os.path.getsize(temp_path)
                if file_size > 0:
                    return temp_path
                else:
                    logger.warning(f"ffmpeg produced empty file: {temp_path}")
                    try:
                        os.unlink(temp_path)
                    except (OSError, PermissionError):
                        pass
                    return None
            else:
                error_msg = process_stderr.decode('utf-8', errors='ignore') if process_stderr else "Unknown error"
                logger.error(f"ffmpeg failed (code {process_returncode}): {error_msg}")
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except (OSError, PermissionError):
                        pass
                return None
        
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg timeout")
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except (OSError, PermissionError):
                    pass
            return None
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except (OSError, PermissionError):
                    pass
            return None
    
    def _load_audio_raw(self, audio_file: str) -> Tuple[Optional[np.ndarray], int, int]:
        """Load audio file as raw PCM data using ffmpeg"""
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            return None, 0, 0
        
        try:
            # Use ffmpeg to convert to raw PCM (16-bit signed, little-endian)
            cmd = [
                ffmpeg_path,
                "-i", audio_file,
                "-f", "s16le",  # 16-bit signed little-endian
                "-acodec", "pcm_s16le",
                "-ar", "44100",  # Sample rate
                "-ac", "2",  # Stereo
                "-"  # Output to stdout
            ]
            
            # Use multiprocessing with spawn on macOS to avoid fork issues
            import platform
            if platform.system() == "Darwin":
                # On macOS, use multiprocessing with spawn
                _ensure_spawn_method()  # Ensure spawn method is set before creating queue
                queue = None
                process_obj = None
                try:
                    queue = multiprocessing.Queue()
                    process_obj = multiprocessing.Process(
                        target=_run_subprocess_worker,
                        args=(queue, cmd, 30)
                    )
                    process_obj.start()
                    process_obj.join(timeout=35)
                    if process_obj.is_alive():
                        process_obj.terminate()
                        process_obj.join(timeout=2)
                        if process_obj.is_alive():
                            process_obj.kill()
                            process_obj.join()
                        logger.error("ffmpeg conversion timeout")
                        return None, 0, 0
                    
                    if queue.empty():
                        logger.error("Subprocess result queue is empty")
                        return None, 0, 0
                    
                    result = queue.get()
                    process_returncode = result.get('returncode')
                    process_stdout = result.get('stdout')
                    process_stderr = result.get('stderr')
                finally:
                    # Clean up resources - CRITICAL to prevent semaphore leaks
                    try:
                        if process_obj and process_obj.is_alive():
                            process_obj.terminate()
                            process_obj.join(timeout=1)
                            if process_obj.is_alive():
                                process_obj.kill()
                                process_obj.join()
                    except Exception:
                        pass
                    try:
                        if queue is not None:
                            # CRITICAL: Properly drain and close queue to prevent semaphore leaks
                            try:
                                # Get any remaining items (with timeout to avoid blocking)
                                import queue as queue_module
                                while True:
                                    try:
                                        queue.get(timeout=0.1)
                                    except queue_module.Empty:
                                        break
                                    except Exception:
                                        break
                            except Exception:
                                pass
                            try:
                                queue.close()
                            except Exception:
                                pass
                            try:
                                queue.join_thread(timeout=2)
                            except Exception:
                                pass
                    except Exception:
                        pass
            else:
                # On other platforms, subprocess is safe
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30
                )
                process_returncode = process.returncode
                process_stdout = process.stdout
                process_stderr = process.stderr
            
            if process_returncode != 0:
                error_msg = process_stderr.decode('utf-8', errors='ignore') if process_stderr else "Unknown error"
                logger.error(f"ffmpeg conversion failed: {error_msg}")
                return None, 0, 0
            
            # Convert bytes to numpy array
            raw_data = process_stdout
            if not raw_data or len(raw_data) == 0:
                logger.error("ffmpeg produced no audio data")
                return None, 0, 0
            
            samples = np.frombuffer(raw_data, dtype=np.int16)
            
            if len(samples) == 0:
                logger.error("No audio samples extracted")
                return None, 0, 0
            
            # Handle stereo (interleaved)
            sample_rate = 44100
            channels = 2
            if channels == 2 and len(samples) >= 2:
                try:
                    samples_reshaped = samples.reshape(-1, 2)
                    if len(samples_reshaped) > 0:
                        # Convert to mono by averaging (keep as float for precision)
                        samples = np.mean(samples_reshaped, axis=1)
                    else:
                        logger.warning("Empty reshaped samples array")
                        return None, 0, 0
                except ValueError:
                    # If reshape fails (odd number of samples), pad with zero
                    if len(samples) % 2 != 0:
                        samples_padded = np.append(samples, 0)
                        samples_reshaped = samples_padded.reshape(-1, 2)
                        if len(samples_reshaped) > 0:
                            samples = np.mean(samples_reshaped, axis=1)
                        else:
                            logger.warning("Empty reshaped samples array after padding")
                            return None, 0, 0
                    else:
                        raise
            
            return samples, sample_rate, 1  # Return as mono
            
        except Exception as e:
            logger.error(f"Error loading audio: {e}")
            return None, 0, 0
    
    def _detect_silence(self, samples: np.ndarray, sample_rate: int, channels: int, result: Dict[str, Any]):
        """Detect silence periods in audio"""
        # Validate inputs
        if sample_rate <= 0:
            logger.warning(f"Invalid sample rate: {sample_rate}")
            return
        if len(samples) == 0:
            logger.warning("No samples provided for silence detection")
            return
        
        # Calculate RMS (Root Mean Square) for each window
        window_size = max(1, int(sample_rate * 0.1))  # 100ms windows, minimum 1
        num_windows = len(samples) // window_size
        
        if num_windows == 0:
            logger.warning("No windows available for silence detection")
            return
        
        silence_periods = []
        total_silence_samples = 0
        
        for i in range(num_windows):
            window = samples[i * window_size:(i + 1) * window_size]
            if len(window) == 0:
                continue
            window_mean_sq = np.mean(window.astype(np.float64) ** 2)
            if window_mean_sq > 0:
                rms = np.sqrt(window_mean_sq)
            else:
                rms = 0
            
            # Convert RMS to dB
            if rms > 0:
                rms_db = float(20 * np.log10(rms / (2 ** 15)))  # Normalize to 16-bit range
            else:
                rms_db = -np.inf
            
            # Check if below threshold
            if rms_db < self.silence_threshold_db:
                total_silence_samples += window_size
                # Track silence period start/end
                time_start = i * window_size / sample_rate
                if not silence_periods or silence_periods[-1]["end"] is not None:
                    silence_periods.append({
                        "start": time_start,
                        "end": None,
                        "duration": 0
                    })
                else:
                    # Continue existing silence period
                    silence_periods[-1]["end"] = time_start + (window_size / sample_rate)
            else:
                # End current silence period if exists
                if silence_periods and silence_periods[-1]["end"] is None:
                    silence_periods[-1]["end"] = (i * window_size) / sample_rate
                    silence_periods[-1]["duration"] = (
                        silence_periods[-1]["end"] - silence_periods[-1]["start"]
                    )
        
        # Close any open silence periods
        for period in silence_periods:
            if period["end"] is None:
                period["end"] = len(samples) / sample_rate
                period["duration"] = period["end"] - period["start"]
        
        # Filter periods by minimum duration
        significant_periods = [
            p for p in silence_periods
            if p["duration"] >= self.silence_min_duration
        ]
        
        # Calculate silence percentage
        total_samples = len(samples)
        if total_samples > 0:
            silence_percentage = (total_silence_samples / total_samples) * 100
        else:
            silence_percentage = 0.0
            logger.warning("No audio samples available for silence detection")
        
        result["silence_detection"] = {
            "silence_detected": len(significant_periods) > 0,
            "silence_percentage": round(silence_percentage, 2),
            "silence_periods": [
                {
                    "start_seconds": round(p["start"], 2),
                    "end_seconds": round(p["end"], 2),
                    "duration_seconds": round(p["duration"], 2)
                }
                for p in significant_periods
            ],
            "threshold_db": self.silence_threshold_db
        }
    
    def _analyze_quality(self, samples: np.ndarray, sample_rate: int, channels: int, result: Dict[str, Any]):
        """Analyze audio quality metrics"""
        if len(samples) == 0:
            logger.warning("No samples provided for quality analysis")
            return
        
        # Normalize to [-1, 1] range (16-bit signed integer)
        max_value = 2 ** 15
        samples_normalized = samples.astype(np.float32) / max_value
        
        # Calculate RMS
        rms_sq = np.mean(samples_normalized.astype(np.float64) ** 2)
        rms = np.sqrt(rms_sq) if rms_sq > 0 else 0
        rms_db = float(20 * np.log10(rms)) if rms > 0 else -np.inf
        
        # Calculate peak
        peak = float(np.max(np.abs(samples_normalized)))
        peak_db = float(20 * np.log10(peak)) if peak > 0 else -np.inf
        
        # Dynamic range (difference between peak and RMS)
        dynamic_range_db = float(peak_db - rms_db) if peak_db > -np.inf and rms_db > -np.inf else None
        
        # Detect clipping (samples at or very close to maximum)
        clipping_threshold = 0.99  # 99% of max
        clipped_samples = int(np.sum(np.abs(samples_normalized) >= clipping_threshold))
        clipping_percentage = float((clipped_samples / len(samples_normalized)) * 100) if len(samples_normalized) > 0 else 0.0
        clipping_detected = clipping_percentage > 1.0  # More than 1% clipped
        
        result["audio_quality"] = {
            "average_volume_db": round(rms_db, 2) if rms_db > -np.inf else None,
            "peak_volume_db": round(peak_db, 2) if peak_db > -np.inf else None,
            "dynamic_range_db": round(dynamic_range_db, 2) if dynamic_range_db is not None else None,
            "clipping_detected": clipping_detected,
            "clipping_percentage": round(clipping_percentage, 2)
        }
    
    def _detect_errors(self, samples: np.ndarray, sample_rate: int, channels: int, result: Dict[str, Any]):
        """Detect error messages in audio (basic pattern detection)"""
        # For now, we'll use a simple approach:
        # Check for repetitive patterns that might indicate error messages
        # This is a simplified version - full implementation would use speech recognition
        
        if len(samples) == 0 or sample_rate <= 0:
            return
        
        # Normalize to [-1, 1] range
        max_value = 2 ** 15
        samples_normalized = samples.astype(np.float32) / max_value
        
        # Check for repetitive patterns (autocorrelation)
        # Simplified: check if audio has very low variance (repetitive)
        window_size = max(1, int(sample_rate * 1.0))  # 1 second windows, minimum 1
        num_windows = len(samples_normalized) // window_size
        
        if num_windows >= 2:
            windows = [
                samples_normalized[i * window_size:(i + 1) * window_size]
                for i in range(num_windows)
            ]
            
            # Filter out empty windows and calculate variance for each window
            variances = [np.var(w) for w in windows if len(w) > 0]
            
            # Check if variances are very similar (repetitive pattern)
            if len(variances) > 1:
                try:
                    variance_std = np.std(variances)
                    variance_mean = np.mean(variances)
                    
                    # Check for valid numeric values (not NaN or inf)
                    if not (np.isnan(variance_std) or np.isnan(variance_mean) or 
                            np.isinf(variance_std) or np.isinf(variance_mean)):
                        # Low variance and low variance of variances suggests repetition
                        if variance_mean < 0.01 and variance_std < 0.005:
                            result["error_detection"]["repetitive_pattern_detected"] = True
                            result["error_detection"]["error_detected"] = True
                            result["error_detection"]["error_messages"].append(
                                "Repetitive audio pattern detected (possible error message)"
                            )
                except (ValueError, TypeError) as e:
                    logger.debug(f"Error calculating variance statistics: {e}")
        
        # Note: Full speech recognition would require additional libraries
        # and is marked as optional in the spec
