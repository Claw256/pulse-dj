"""Test audio analysis functionality

This test validates:
1. Audio device handling
2. Audio capture
3. Frequency analysis
4. Beat detection
"""

import asyncio
import logging
import math
import sys
import time
from typing import Dict, Any, Optional
from pulse.core.audio.analyzer import AudioInput
import sounddevice as sd
import numpy as np

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioTester:
    """Test audio analysis functionality"""
    
    def __init__(self, device_id: Optional[int] = None):
        self.device_id = device_id
        self.audio = None
        self.latest_features = {}
        self._running = True
        
    @staticmethod
    def format_energy(e: float) -> str:
        """Format energy value for display"""
        if e < 0.01:
            return f"{e:.2e}"
        return f"{e:.2f}"
        
    @staticmethod
    def format_bar(value: float, max_length: int = 20) -> str:
        """Create a visual bar representation of a value"""
        # Normalize value to 0-1 range using log scale
        if value <= 0:
            normalized = 0
        else:
            normalized = min(1.0, np.log10(value + 1) / 5)  # Adjust divisor to change scaling
            
        # Create bar
        bar_length = int(normalized * max_length)
        return '[' + '█' * bar_length + '·' * (max_length - bar_length) + ']'
        
    @staticmethod
    def format_band_name(name: str, width: int = 10) -> str:
        """Format band name with consistent width"""
        return f"{name:<{width}}"
        
    def print_levels(self, features: Dict[str, Any]):
        """Print audio levels and beat information"""
        # Clear line and print header
        print("\r", end="")
        
        # Print each frequency band
        for band, energy in features.get('band_energies', {}).items():
            bar = self.format_bar(energy)
            name = self.format_band_name(band)
            print(f"{name}{bar} {self.format_energy(energy)} | ", end="")
            
        # Print volume level
        volume = features.get('volume_level', 0)
        print(f"Vol: {self.format_bar(volume)} {self.format_energy(volume)}", end="")
        
        # Print beat information if detected
        if features.get('is_beat', False):
            print(f"\nBEAT! Strength: {features.get('beat_strength', 0):.2f}")
            
        sys.stdout.flush()
        
    @staticmethod
    def list_devices():
        """List available audio devices"""
        devices = sd.query_devices()
        print("\nAvailable audio devices:")
        print("-" * 80)
        print(f"{'ID':<4} {'Name':<40} {'In':<4} {'Out':<4} {'Default':<8}")
        print("-" * 80)
        
        default_input = sd.query_devices(kind='input')
        for i, dev in enumerate(devices):
            is_default = "*" if dev['name'] == default_input['name'] else ""
            print(
                f"{i:<4} {dev['name'][:40]:<40} "
                f"{dev['max_input_channels']:<4} "
                f"{dev['max_output_channels']:<4} "
                f"{is_default:<8}"
            )
        print("-" * 80)
        return len(devices)
        
    async def handle_audio(self, features: Dict[str, Any]):
        """Handle audio analysis updates"""
        if not self._running:
            return
            
        try:
            self.latest_features = features
            self.print_levels(features)
            
        except Exception as e:
            logger.error(f"Error handling audio: {e}")
            
    async def start(self):
        """Start audio testing"""
        try:
            # Print instructions
            print("\nAudio Analysis Test")
            print("=" * 80)
            print("\n1. Audio Input:")
            print("   - Make sure audio is playing")
            print("   - Check frequency response")
            print("   - Monitor band energies")
            print("\n2. Test Features:")
            print("   - Frequency analysis")
            print("   - Energy detection")
            print("   - Band isolation")
            print("\n3. Press Ctrl+C to exit")
            print("\nStarting audio capture...\n")
            print("=" * 80 + "\n")
            
            # Set up audio input
            logger.info("Starting audio input...")
            if self.device_id is not None:
                device_info = sd.query_devices(self.device_id)
                logger.info(f"Using audio device: {device_info['name']}")
            else:
                device_info = sd.query_devices(kind='input')
                logger.info(f"Using default input device: {device_info['name']}")
                
            self.audio = AudioInput(
                device_id=self.device_id,
                callback=self.handle_audio
            )
            
            # Start audio capture
            self.audio.start()
            
            # Keep running until interrupted
            while self._running:
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("\nStopping audio capture...")
        except Exception as e:
            logger.error(f"Error in audio test: {e}")
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources"""
        self._running = False
        
        if self.audio:
            try:
                self.audio.stop()
                logger.info("Audio input stopped")
            except Exception as e:
                logger.error(f"Error stopping audio: {e}")

async def main(device_id: Optional[int] = None):
    """Main test function"""
    tester = AudioTester(device_id)
    
    try:
        await tester.start()
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Audio analyzer test')
    parser.add_argument(
        '-d', '--device',
        type=int,
        help='Input device ID (run with -l to list devices)'
    )
    parser.add_argument(
        '-l', '--list-devices',
        action='store_true',
        help='List available audio devices'
    )
    
    args = parser.parse_args()
    
    try:
        if args.list_devices:
            AudioTester.list_devices()
        else:
            if sys.platform == 'win32':
                # Set up event loop policy for Windows
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(main(args.device))
    except KeyboardInterrupt:
        pass  # Handle Ctrl+C gracefully
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
