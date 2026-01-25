"""Phase 4: Ad detection via metadata markers"""

import time
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger("stream_checker")


class AdDetector:
    """Detect advertising markers in stream metadata"""
    
    def __init__(
        self,
        monitoring_duration: int = 60,  # Monitor for 60 seconds
        check_interval: float = 2.0  # Check metadata every 2 seconds
    ):
        self.monitoring_duration = monitoring_duration
        self.check_interval = check_interval
        
        # Common ad marker patterns
        self.ad_title_patterns = [
            "commercial",
            "advertisement",
            "ad break",
            "advertising",
            "ad",
            "spot",
            "promo",
            "promotion"
        ]
        
        self.ad_genre_patterns = [
            "commercial",
            "advertisement",
            "ad",
            "spot"
        ]
    
    def detect(self, url: str) -> Dict[str, Any]:
        """
        Monitor stream metadata for ad markers
        
        Args:
            url: Stream URL to monitor
            
        Returns:
            Dictionary with ad detection results
        """
        result = {
            "ads_detected": False,
            "ad_breaks": [],
            "total_ad_time_seconds": 0,
            "ad_frequency_per_hour": 0,
            "monitoring_duration_seconds": self.monitoring_duration
        }
        
        ad_breaks = []
        start_time = time.time()
        last_title = None
        last_genre = None
        ad_break_start = None
        
        try:
            while (time.time() - start_time) < self.monitoring_duration:
                # Get current metadata
                metadata = self._get_stream_metadata(url)
                
                if metadata:
                    current_title = metadata.get("title", "").lower() if metadata.get("title") else ""
                    current_genre = metadata.get("genre", "").lower() if metadata.get("genre") else ""
                    
                    # Check if ad marker detected
                    is_ad = self._is_ad_marker(current_title, current_genre)
                    
                    if is_ad:
                        # Ad detected
                        if ad_break_start is None:
                            # Start of ad break
                            ad_break_start = time.time()
                            logger.debug(f"Ad break started at {ad_break_start}")
                    
                    else:
                        # Not an ad
                        if ad_break_start is not None:
                            # End of ad break
                            ad_break_end = time.time()
                            duration = ad_break_end - ad_break_start
                            
                            if duration >= 5:  # Minimum 5 seconds to count as ad break
                                ad_breaks.append({
                                    "start_time": datetime.fromtimestamp(ad_break_start, tz=timezone.utc).isoformat(),
                                    "end_time": datetime.fromtimestamp(ad_break_end, tz=timezone.utc).isoformat(),
                                    "duration_seconds": round(duration, 2),
                                    "detection_method": "metadata_marker",
                                    "title": last_title or "Unknown",
                                    "genre": last_genre or "Unknown"
                                })
                                logger.debug(f"Ad break ended: {duration:.2f} seconds")
                            
                            ad_break_start = None
                    
                    last_title = current_title
                    last_genre = current_genre
                
                # Wait before next check
                time.sleep(self.check_interval)
            
            # Check if ad break is still ongoing at end of monitoring
            if ad_break_start is not None:
                ad_break_end = time.time()
                duration = ad_break_end - ad_break_start
                if duration >= 5:
                    ad_breaks.append({
                        "start_time": datetime.fromtimestamp(ad_break_start, tz=timezone.utc).isoformat(),
                        "end_time": datetime.fromtimestamp(ad_break_end, tz=timezone.utc).isoformat(),
                        "duration_seconds": round(duration, 2),
                        "detection_method": "metadata_marker",
                        "title": last_title or "Unknown",
                        "genre": last_genre or "Unknown"
                    })
        
        except Exception as e:
            logger.error(f"Error during ad detection: {e}")
            result["error"] = str(e)
        
        # Calculate statistics
        result["ads_detected"] = len(ad_breaks) > 0
        result["ad_breaks"] = ad_breaks
        result["total_ad_time_seconds"] = sum(ab["duration_seconds"] for ab in ad_breaks)
        
        # Estimate frequency per hour (extrapolate from monitoring duration)
        if self.monitoring_duration > 0:
            ad_count = len(ad_breaks)
            hours_monitored = self.monitoring_duration / 3600
            result["ad_frequency_per_hour"] = round(ad_count / hours_monitored, 1) if hours_monitored > 0 else 0
        
        return result
    
    def _get_stream_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get current stream metadata"""
        try:
            # Try ICY metadata (Icecast/Shoutcast)
            response = requests.get(
                url,
                timeout=5,
                stream=True,
                headers={"Icy-MetaData": "1"}
            )
            
            metadata = {}
            
            # Check ICY headers
            for key, value in response.headers.items():
                if key.lower().startswith("icy-"):
                    metadata_key = key.lower().replace("icy-", "")
                    metadata[metadata_key] = value
            
            # Try to get title from ICY metadata
            if "icy-name" in metadata:
                metadata["title"] = metadata["icy-name"]
            if "icy-genre" in metadata:
                metadata["genre"] = metadata["icy-genre"]
            
            return metadata if metadata else None
        
        except Exception as e:
            logger.debug(f"Error getting metadata: {e}")
            return None
    
    def _is_ad_marker(self, title: str, genre: str) -> bool:
        """Check if metadata indicates an ad"""
        # Check title
        if title:
            for pattern in self.ad_title_patterns:
                if pattern in title:
                    return True
        
        # Check genre
        if genre:
            for pattern in self.ad_genre_patterns:
                if pattern in genre:
                    return True
        
        return False


class HealthScoreCalculator:
    """Calculate overall stream health score"""
    
    @staticmethod
    def calculate(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate health score based on all phase results
        
        Args:
            result: Complete test result dictionary
            
        Returns:
            Dictionary with health score and recommendations
        """
        score = 100
        issues = []
        recommendations = []
        
        # Phase 1: Connectivity (20 points)
        if "connectivity" in result:
            conn = result["connectivity"]
            if conn.get("status") != "success":
                score -= 20
                issues.append("Stream connectivity failed")
            elif conn.get("http_status") != 200:
                score -= 10
                issues.append(f"HTTP status: {conn.get('http_status')}")
        
        # SSL Certificate (10 points)
        if "ssl_certificate" in result and result["ssl_certificate"]:
            ssl = result["ssl_certificate"]
            if not ssl.get("valid", True):
                score -= 10
                issues.append("SSL certificate invalid or expired")
            elif ssl.get("days_until_expiration", 999) < 30:
                score -= 5
                issues.append(f"SSL certificate expiring in {ssl.get('days_until_expiration')} days")
                recommendations.append("Renew SSL certificate soon")
            if ssl.get("self_signed", False):
                score -= 5
                issues.append("Self-signed SSL certificate")
        
        # Phase 2: Player Tests (20 points)
        if "player_tests" in result:
            player_tests = result["player_tests"]
            if "vlc" in player_tests:
                vlc_result = player_tests["vlc"]
                if vlc_result.get("status") != "success":
                    score -= 20
                    issues.append("VLC player test failed")
                elif not vlc_result.get("format_supported", False):
                    score -= 10
                    issues.append("Stream format not supported by player")
        
        # Phase 3: Audio Analysis (30 points)
        if "audio_analysis" in result:
            audio = result["audio_analysis"]
            
            # Silence detection (10 points)
            silence = audio.get("silence_detection", {})
            if silence.get("silence_detected", False):
                silence_pct = silence.get("silence_percentage", 0)
                if silence_pct > 50:
                    score -= 10
                    issues.append(f"Excessive silence: {silence_pct}%")
                elif silence_pct > 20:
                    score -= 5
                    issues.append(f"Significant silence: {silence_pct}%")
            
            # Error detection (10 points)
            error_det = audio.get("error_detection", {})
            if error_det.get("error_detected", False):
                score -= 10
                issues.append("Error message detected in audio")
            
            # Audio quality (10 points)
            quality = audio.get("audio_quality", {})
            if quality.get("clipping_detected", False):
                score -= 5
                issues.append("Audio clipping detected")
                recommendations.append("Reduce input gain to prevent clipping")
            
            avg_volume = quality.get("average_volume_db")
            if avg_volume is not None and avg_volume < -30:
                score -= 5
                issues.append(f"Very low audio volume: {avg_volume} dB")
                recommendations.append("Increase stream volume levels")
        
        # Phase 4: Ad Detection (10 points) - Not a problem, just informational
        # Ads are normal, so they don't reduce health score
        
        # Connection Quality (10 points)
        if "connection_quality" in result:
            quality = result["connection_quality"]
            if not quality.get("stable", True):
                score -= 10
                issues.append("Unstable connection")
        
        # Ensure score doesn't go below 0
        score = max(0, score)
        
        # Generate recommendations if score is low
        if score < 80:
            if not recommendations:
                recommendations.append("Review stream configuration and server settings")
        
        return {
            "health_score": score,
            "issues": issues,
            "recommendations": recommendations
        }
