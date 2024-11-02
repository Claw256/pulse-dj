import numpy as np
from typing import Dict, Any, Optional, Callable
import sounddevice as sd
import time
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    """Real-time audio frequency analyzer"""
    
    FREQ_BANDS = {
        'sub_bass': (20, 60),
        'bass': (60, 250),
        'low_mid': (250, 500),
        'mid': (500, 2000),
        'high_mid': (2000, 4000),
        'high': (4000, 20000)
    }
    
    def __init__(self, sample_rate: int = 44100, window_size: int = 2048, overlap: float = 0.5):
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.overlap_samples = int(window_size * overlap)
        self.window = np.hanning(window_size)
        self.band_indices = self._calculate_band_indices()
        self.peak_energy = {band: 0.0 for band in self.FREQ_BANDS.keys()}
        self.smoothing = 0.2  # Smoothing factor for peak normalization
        
    def _calculate_band_indices(self) -> Dict[str, tuple]:
        """Calculate FFT frequency band indices"""
        freqs = np.fft.rfftfreq(self.window_size, 1.0/self.sample_rate)
        indices = {}
        
        for band, (low, high) in self.FREQ_BANDS.items():
            start = np.searchsorted(freqs, low)
            end = np.searchsorted(freqs, high)
            indices[band] = (start, end)
            
        return indices
        
    def _normalize_energy(self, band: str, energy: float) -> float:
        """Normalize energy value with adaptive peak tracking"""
        # Update peak with decay
        self.peak_energy[band] *= (1.0 - self.smoothing)
        if energy > self.peak_energy[band]:
            self.peak_energy[band] = energy
            
        # Normalize and scale up for more dynamic range
        if self.peak_energy[band] > 0:
            return min(1.0, (energy / self.peak_energy[band]) * 2.0)
        return 0.0
        
    def analyze_frame(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Analyze a frame of audio data
        
        Args:
            audio_data: Audio frame data
            
        Returns:
            Dictionary containing:
                - band_energies: Dictionary of frequency band energies (0-1)
                - volume_level: Overall volume level (0-1)
        """
        try:
            # Convert to mono if stereo
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
                
            # Apply window function
            windowed = audio_data * self.window
            
            # Compute FFT
            magnitudes = np.abs(np.fft.rfft(windowed))
            magnitudes = magnitudes / len(magnitudes)  # Normalize
            
            # Calculate band energies
            band_energies = {}
            for band, (start, end) in self.band_indices.items():
                # Calculate band energy
                energy = np.sum(magnitudes[start:end] ** 2)
                
                # Normalize energy
                band_energies[band] = self._normalize_energy(band, energy)
                
            # Calculate overall volume level
            volume_level = float(np.sqrt(np.mean(audio_data ** 2)))
            
            return {
                'band_energies': band_energies,
                'volume_level': volume_level
            }
            
        except Exception as e:
            logger.error(f"Error analyzing audio frame: {e}")
            return {
                'band_energies': {band: 0.0 for band in self.FREQ_BANDS.keys()},
                'volume_level': 0.0
            }

class AudioInput:
    """Audio input handler"""
    
    def __init__(self, device_id: Optional[int] = None, callback: Optional[Callable] = None):
        self.device_id = device_id
        self.callback = callback
        self.stream = None
        self.analyzer = AudioAnalyzer()
        self.loop = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._running = True
        
        # List available devices on initialization
        self._list_devices()
        
    def _list_devices(self):
        """Log available audio devices"""
        try:
            devices = sd.query_devices()
            logger.info("Available audio devices:")
            for i, dev in enumerate(devices):
                logger.info(f"[{i}] {dev['name']} (in={dev['max_input_channels']}, out={dev['max_output_channels']})")
        except Exception as e:
            logger.error(f"Error listing audio devices: {e}")
        
    def _run_callback(self, features: Dict[str, Any]):
        """Run callback in the event loop"""
        if not self._running:
            return
            
        if self.callback and self.loop:
            try:
                # Create a task for the callback
                asyncio.run_coroutine_threadsafe(
                    self.callback(features), self.loop
                )
            except Exception as e:
                logger.error(f"Error in callback: {e}")
        
    def audio_callback(self, indata, frames, time_info, status):
        """Handle audio input data"""
        try:
            if status:
                logger.warning(f"Audio status: {status}")
                
            if self.callback:
                # Analyze audio
                features = self.analyzer.analyze_frame(indata)
                
                # Run callback in executor to avoid blocking
                self.executor.submit(self._run_callback, features)
                
        except Exception as e:
            logger.error(f"Error in audio callback: {e}")
            
    def start(self):
        """Start audio capture"""
        try:
            # Store event loop reference
            self.loop = asyncio.get_event_loop()
            
            # Get device info
            if self.device_id is not None:
                device_info = sd.query_devices(self.device_id)
                logger.info(f"Using audio device {self.device_id}: {device_info['name']}")
            
            # Create input stream
            self.stream = sd.InputStream(
                device=self.device_id,
                channels=2,
                samplerate=44100,
                blocksize=2048,
                callback=self.audio_callback
            )
            
            self.stream.start()
            logger.info(f"Started audio capture on device {self.device_id or 'default'}")
            
        except Exception as e:
            logger.error(f"Error starting audio capture: {e}")
            raise
            
    def stop(self):
        """Stop audio capture"""
        self._running = False
        
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                self.stream = None
                logger.info("Stopped audio capture")
            except Exception as e:
                logger.error(f"Error stopping audio capture: {e}")
                
        if self.executor:
            self.executor.shutdown(wait=False)
