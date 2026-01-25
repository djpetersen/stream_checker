"""Phase 1: Stream connectivity and metadata extraction"""

import time
import ssl
import socket
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import mutagen
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3NoHeaderError


class ConnectivityChecker:
    """Check stream connectivity and extract metadata"""
    
    def __init__(
        self,
        connection_timeout: int = 30,
        read_timeout: int = 60,
        verify_ssl: bool = True
    ):
        self.connection_timeout = connection_timeout
        self.read_timeout = read_timeout
        self.verify_ssl = verify_ssl
    
    def check(self, url: str) -> Dict[str, Any]:
        """
        Perform Phase 1 checks: connectivity, SSL, parameters, metadata
        
        Args:
            url: Stream URL to check
            
        Returns:
            Dictionary with all Phase 1 results
        """
        result = {
            "stream_url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": 1,
            "connectivity": {},
            "ssl_certificate": {},
            "stream_parameters": {},
            "metadata": {},
            "server_headers": {},
            "hls_info": None
        }
        
        # Check connectivity
        connectivity_result = self._check_connectivity(url)
        result["connectivity"] = connectivity_result
        
        if connectivity_result["status"] != "success":
            return result  # Can't proceed if connection failed
        
        # Check SSL certificate (if HTTPS)
        if url.startswith("https://"):
            ssl_result = self._check_ssl_certificate(url)
            result["ssl_certificate"] = ssl_result
        
        # Extract stream parameters and metadata
        params_result = self._extract_stream_parameters(url)
        result["stream_parameters"] = params_result
        
        metadata_result = self._extract_metadata(url)
        result["metadata"] = metadata_result
        
        # Analyze server headers
        headers_result = self._analyze_headers(url)
        result["server_headers"] = headers_result
        
        # Check HLS if applicable
        if self._is_hls(url):
            hls_result = self._check_hls(url)
            result["hls_info"] = hls_result
        
        return result
    
    def _check_connectivity(self, url: str) -> Dict[str, Any]:
        """Check HTTP/HTTPS connectivity"""
        start_time = time.time()
        
        try:
            response = requests.head(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                allow_redirects=True,
                verify=self.verify_ssl,
                stream=True
            )
            
            response_time = int((time.time() - start_time) * 1000)
            
            return {
                "status": "success",
                "response_time_ms": response_time,
                "http_status": response.status_code,
                "content_type": response.headers.get("Content-Type", "unknown"),
                "final_url": response.url if response.url != url else None
            }
        
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "error": "Connection timeout",
                "response_time_ms": int((time.time() - start_time) * 1000)
            }
        
        except requests.exceptions.ConnectionError as e:
            return {
                "status": "connection_error",
                "error": str(e),
                "response_time_ms": int((time.time() - start_time) * 1000)
            }
        
        except requests.exceptions.SSLError as e:
            return {
                "status": "ssl_error",
                "error": str(e),
                "response_time_ms": int((time.time() - start_time) * 1000)
            }
        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "response_time_ms": int((time.time() - start_time) * 1000)
            }
    
    def _check_ssl_certificate(self, url: str) -> Dict[str, Any]:
        """Check SSL/TLS certificate"""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            port = parsed.port or 443
            
            # Create SSL context
            context = ssl.create_default_context()
            
            # Connect and get certificate
            with socket.create_connection((hostname, port), timeout=self.connection_timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    cert = x509.load_der_x509_certificate(cert_der, default_backend())
            
            # Extract certificate information
            issuer = cert.issuer.rfc4514_string()
            subject = cert.subject.rfc4514_string()
            # Use UTC-aware datetime methods to avoid deprecation warnings
            not_after = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)
            not_before = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
            
            # Ensure timezone-aware
            if not_after.tzinfo is None:
                not_after = not_after.replace(tzinfo=timezone.utc)
            if not_before.tzinfo is None:
                not_before = not_before.replace(tzinfo=timezone.utc)
            
            # Check if expired
            now = datetime.now(timezone.utc)
            is_valid = now < not_after
            
            # Calculate days until expiration
            days_until_expiration = None
            if is_valid:
                delta = not_after - now
                days_until_expiration = delta.days
            
            # Check if self-signed (issuer == subject)
            is_self_signed = issuer == subject
            
            return {
                "valid": is_valid,
                "expires": not_after.isoformat(),
                "days_until_expiration": days_until_expiration,
                "issued": not_before.isoformat(),
                "issuer": issuer,
                "subject": subject,
                "self_signed": is_self_signed
            }
        
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    def _extract_stream_parameters(self, url: str) -> Dict[str, Any]:
        """Extract stream technical parameters"""
        params = {
            "bitrate_kbps": None,
            "codec": None,
            "sample_rate_hz": None,
            "channels": None,
            "container": None
        }
        
        try:
            # Try to get a small sample of the stream
            response = requests.get(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                stream=True,
                headers={"Range": "bytes=0-8192"},  # Get first 8KB
                verify=self.verify_ssl
            )
            
            if response.status_code in [200, 206]:  # 206 is Partial Content
                # Save to temporary file for mutagen
                import tempfile
                max_bytes = 16384  # Limit to 16KB
                bytes_read = 0
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    for chunk in response.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                        bytes_read += len(chunk)
                        if bytes_read >= max_bytes or len(chunk) < 8192:  # Last chunk or limit reached
                            break
                    tmp_path = tmp.name
                
                try:
                    # Try to read with mutagen
                    audio_file = mutagen.File(tmp_path)
                    
                    if audio_file:
                        # Extract parameters based on file type
                        if isinstance(audio_file, MP3):
                            params["codec"] = "MP3"
                            params["container"] = "MP3"
                            if hasattr(audio_file.info, 'bitrate'):
                                params["bitrate_kbps"] = audio_file.info.bitrate // 1000
                            if hasattr(audio_file.info, 'sample_rate'):
                                params["sample_rate_hz"] = audio_file.info.sample_rate
                            if hasattr(audio_file.info, 'channels'):
                                channels = audio_file.info.channels
                                params["channels"] = "stereo" if channels == 2 else "mono" if channels == 1 else f"{channels} channels"
                        
                        elif isinstance(audio_file, MP4):
                            params["codec"] = "AAC"
                            params["container"] = "MP4"
                            if hasattr(audio_file.info, 'bitrate'):
                                params["bitrate_kbps"] = audio_file.info.bitrate // 1000
                            if hasattr(audio_file.info, 'sample_rate'):
                                params["sample_rate_hz"] = int(audio_file.info.sample_rate)
                            if hasattr(audio_file.info, 'channels'):
                                channels = audio_file.info.channels
                                params["channels"] = "stereo" if channels == 2 else "mono" if channels == 1 else f"{channels} channels"
                        
                        elif isinstance(audio_file, OggVorbis):
                            params["codec"] = "Vorbis"
                            params["container"] = "OGG"
                            if hasattr(audio_file.info, 'bitrate'):
                                params["bitrate_kbps"] = audio_file.info.bitrate // 1000
                            if hasattr(audio_file.info, 'sample_rate'):
                                params["sample_rate_hz"] = audio_file.info.sample_rate
                            if hasattr(audio_file.info, 'channels'):
                                channels = audio_file.info.channels
                                params["channels"] = "stereo" if channels == 2 else "mono" if channels == 1 else f"{channels} channels"
                        
                        else:
                            # Generic mutagen file
                            params["codec"] = type(audio_file).__name__
                            if hasattr(audio_file.info, 'bitrate'):
                                params["bitrate_kbps"] = audio_file.info.bitrate // 1000
                            if hasattr(audio_file.info, 'sample_rate'):
                                params["sample_rate_hz"] = audio_file.info.sample_rate
                
                except Exception as e:
                    # Mutagen couldn't read it, might be a stream
                    pass
                finally:
                    # Clean up temp file
                    import os
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            # Try to get ICY metadata (for Icecast/Shoutcast streams)
            icy_metadata = self._get_icy_metadata(url)
            if icy_metadata:
                if icy_metadata.get("icy-br"):
                    params["bitrate_kbps"] = int(icy_metadata["icy-br"])
                if icy_metadata.get("icy-sr"):
                    params["sample_rate_hz"] = int(icy_metadata["icy-sr"])
        
        except Exception as e:
            params["error"] = str(e)
        
        return params
    
    def _extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract stream metadata"""
        metadata = {
            "title": None,
            "genre": None,
            "artist": None,
            "description": None,
            "url": url
        }
        
        try:
            # Try ICY metadata first (Icecast/Shoutcast)
            icy_metadata = self._get_icy_metadata(url)
            if icy_metadata:
                metadata["title"] = icy_metadata.get("icy-name") or icy_metadata.get("StreamTitle")
                metadata["genre"] = icy_metadata.get("icy-genre")
                metadata["description"] = icy_metadata.get("icy-description")
            
            # Try mutagen for file-based metadata
            response = requests.get(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                stream=True,
                headers={"Range": "bytes=0-16384"},  # Get first 16KB
                verify=self.verify_ssl
            )
            
            if response.status_code in [200, 206]:
                import tempfile
                max_bytes = 16384  # Limit to 16KB
                bytes_read = 0
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    for chunk in response.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                        bytes_read += len(chunk)
                        if bytes_read >= max_bytes or len(chunk) < 8192:
                            break
                    tmp_path = tmp.name
                
                try:
                    audio_file = mutagen.File(tmp_path)
                    if audio_file:
                        tags = audio_file.tags
                        if tags:
                            # Try common tag formats
                            for key in ["TIT2", "TITLE", "\xa9nam"]:
                                if key in tags:
                                    metadata["title"] = str(tags[key][0]) if tags[key] else None
                                    break
                            
                            for key in ["TPE1", "ARTIST", "\xa9ART"]:
                                if key in tags:
                                    metadata["artist"] = str(tags[key][0]) if tags[key] else None
                                    break
                            
                            for key in ["TCON", "GENRE", "\xa9gen"]:
                                if key in tags:
                                    metadata["genre"] = str(tags[key][0]) if tags[key] else None
                                    break
                
                except Exception:
                    pass
                finally:
                    import os
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        
        except Exception as e:
            metadata["error"] = str(e)
        
        return metadata
    
    def _get_icy_metadata(self, url: str) -> Optional[Dict[str, str]]:
        """Get ICY metadata from Icecast/Shoutcast stream"""
        try:
            response = requests.get(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                stream=True,
                headers={"Icy-MetaData": "1"},
                verify=self.verify_ssl
            )
            
            # Check for ICY headers
            icy_headers = {}
            for key, value in response.headers.items():
                if key.lower().startswith("icy-"):
                    icy_headers[key.lower()] = value
            
            return icy_headers if icy_headers else None
        
        except Exception:
            return None
    
    def _analyze_headers(self, url: str) -> Dict[str, Any]:
        """Analyze HTTP response headers"""
        headers_info = {
            "server": None,
            "cors_enabled": False,
            "cache_control": None,
            "content_length": None,
            "content_type": None
        }
        
        try:
            response = requests.head(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                allow_redirects=True,
                verify=self.verify_ssl
            )
            
            headers = response.headers
            
            headers_info["server"] = headers.get("Server")
            headers_info["content_type"] = headers.get("Content-Type")
            headers_info["content_length"] = headers.get("Content-Length")
            headers_info["cache_control"] = headers.get("Cache-Control")
            
            # Check for CORS
            if "Access-Control-Allow-Origin" in headers:
                headers_info["cors_enabled"] = True
                headers_info["cors_origin"] = headers.get("Access-Control-Allow-Origin")
        
        except Exception as e:
            headers_info["error"] = str(e)
        
        return headers_info
    
    def _is_hls(self, url: str) -> bool:
        """Check if URL is an HLS stream"""
        return url.endswith(".m3u8") or ".m3u8" in url.lower()
    
    def _check_hls(self, url: str) -> Dict[str, Any]:
        """Check HLS stream"""
        hls_info = {
            "is_hls": True,
            "playlist_accessible": False,
            "segments_accessible": False,
            "variant_streams": []
        }
        
        try:
            response = requests.get(
                url,
                timeout=(self.connection_timeout, self.read_timeout),
                verify=self.verify_ssl
            )
            
            if response.status_code == 200:
                hls_info["playlist_accessible"] = True
                content = response.text
                
                # Check if it's a master playlist (contains #EXT-X-STREAM-INF)
                if "#EXT-X-STREAM-INF" in content:
                    hls_info["is_master_playlist"] = True
                    # Extract variant streams
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("#EXT-X-STREAM-INF"):
                            if i + 1 < len(lines):
                                variant_url = lines[i + 1].strip()
                                if variant_url and not variant_url.startswith("#"):
                                    hls_info["variant_streams"].append(variant_url)
                else:
                    hls_info["is_master_playlist"] = False
                    # Check if segments are accessible
                    lines = content.split("\n")
                    segment_count = sum(1 for line in lines if line.strip() and not line.startswith("#"))
                    hls_info["segment_count"] = segment_count
                    hls_info["segments_accessible"] = segment_count > 0
        
        except Exception as e:
            hls_info["error"] = str(e)
        
        return hls_info
