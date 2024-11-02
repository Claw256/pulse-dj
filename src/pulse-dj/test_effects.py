"""Test light effects implementation

This test validates:
1. Basic light control and waveforms
2. Beat synchronization
3. Audio analysis
4. Effect transitions
"""

import asyncio
import logging
import math
import time
from typing import Dict, Any, List, Tuple
from pulse.core.lights.controller import LIFXController, LIFXLight, Waveform, LIFXError
from pulse.core.lights.effects import VirtualDJEffect
from pulse.core.os2l.protocol import BeatMessage, ButtonMessage, CommandMessage

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_color(color: Tuple[int, int, int, int]) -> bool:
    """Validate LIFX color values
    
    Args:
        color: (hue, saturation, brightness, kelvin)
        
    Returns:
        True if valid, False otherwise
    """
    try:
        hue, sat, bri, kel = color
        if not (0 <= hue <= 65535):
            raise ValueError(f"Hue must be between 0 and 65535, got {hue}")
        if not (0 <= sat <= 65535):
            raise ValueError(f"Saturation must be between 0 and 65535, got {sat}")
        if not (0 <= bri <= 65535):
            raise ValueError(f"Brightness must be between 0 and 65535, got {bri}")
        if not (1500 <= kel <= 9000):
            raise ValueError(f"Kelvin must be between 1500 and 9000, got {kel}")
        return True
    except Exception as e:
        logger.error(f"Invalid color values: {e}")
        return False

def create_test_beat(bpm: float, position: int, strength: float) -> Dict[str, Any]:
    """Create test beat information
    
    Args:
        bpm: Beats per minute
        position: Beat position (1-4)
        strength: Beat strength (0-100)
    """
    return {
        'bpm': bpm,
        'position': position,
        'strength': strength,
        'change': False
    }

def create_test_audio_features(t: float) -> Dict[str, Any]:
    """Create test audio features with frequency bands
    
    Args:
        t: Time value (0-1) for oscillation
    """
    # Create oscillating energy values for each frequency band
    return {
        'band_energies': {
            'sub_bass': abs(math.sin(t * 2 * math.pi)),
            'bass': abs(math.sin(t * 3 * math.pi)),
            'low_mid': abs(math.sin(t * 4 * math.pi)),
            'mid': abs(math.sin(t * 5 * math.pi)),
            'high_mid': abs(math.sin(t * 6 * math.pi)),
            'high': abs(math.sin(t * 7 * math.pi))
        }
    }

async def test_waveforms(controller: LIFXController):
    """Test LIFX waveform capabilities
    
    Tests:
    1. Sine wave
    2. Half sine
    3. Triangle
    4. Saw
    5. Pulse
    """
    logger.info("\nTesting waveforms...")
    
    # Test each waveform
    waveforms = [
        (Waveform.SINE, "Sine wave"),
        (Waveform.HALF_SINE, "Half sine"),
        (Waveform.TRIANGLE, "Triangle"),
        (Waveform.SAW, "Saw"),
        (Waveform.PULSE, "Pulse")
    ]
    
    # Define test color (bright red)
    red = (0, 65535, 65535, 3500)
    
    # Validate color
    if not validate_color(red):
        return
        
    for waveform, name in waveforms:
        try:
            logger.info(f"\nTesting {name} waveform")
            
            # Set all lights to off first
            off = (0, 0, 0, 3500)  # Off state
            tasks = [light.set_color(off, duration=0) for light in controller.lights]
            await asyncio.gather(*tasks)
            await asyncio.sleep(1)
            
            # Apply waveform to all lights
            tasks = [
                light.set_waveform(
                    color=red,            # Target color
                    period=2000,          # 2 second period
                    cycles=3.0,           # 3 cycles
                    waveform=waveform,    # Current waveform
                    transient=True,       # Return to original
                    skew_ratio=0x8000    # 50% duty cycle
                )
                for light in controller.lights
            ]
            await asyncio.gather(*tasks)
            
            # Wait for effect to complete
            await asyncio.sleep(6)  # 2 seconds * 3 cycles
            
            # Set back to off
            tasks = [light.set_color(off, duration=0) for light in controller.lights]
            await asyncio.gather(*tasks)
            await asyncio.sleep(1)  # Pause between effects
            
        except Exception as e:
            logger.error(f"Error during {name} test: {e}")

async def test_bpm_sequence(effect: VirtualDJEffect):
    """Test effect response to different BPMs
    
    Tests:
    1. Slow BPM (60) - Relaxed timing
    2. Medium BPM (120) - Standard timing
    3. Fast BPM (180) - High energy
    """
    logger.info("\nTesting BPM response...")
    
    bpm_sequences = [
        (60, "Slow"),    # 60 BPM
        (120, "Medium"), # 120 BPM
        (180, "Fast")    # 180 BPM
    ]
    
    for bpm, speed in bpm_sequences:
        logger.info(f"\nTesting {speed} BPM ({bpm})")
        
        # Run for 5 seconds at each BPM
        start_time = time.time()
        beat_count = 0
        
        while time.time() - start_time < 5:
            # Calculate phase for this moment
            t = (time.time() - start_time) / 5.0  # 0 to 1 over 5 seconds
            
            # Create beat info (4 beats per measure)
            beat_position = (beat_count % 4) + 1
            features = {
                'beat_info': create_test_beat(
                    bpm=bpm,
                    position=beat_position,
                    strength=80.0 if beat_position == 1 else 60.0  # Stronger on downbeat
                ),
                'band_energies': create_test_audio_features(t)['band_energies']
            }
            
            # Update effect
            await effect.update(features)
            
            # Wait appropriate time for current BPM
            beat_duration = 60.0 / bpm
            await asyncio.sleep(beat_duration)
            beat_count += 1

async def test_frequency_response(effect: VirtualDJEffect):
    """Test effect response to frequency content
    
    Tests:
    1. Frequency band isolation
    2. Energy level response
    3. Color mapping
    """
    logger.info("\nTesting frequency response...")
    
    # Run through frequency sweep
    for i in range(50):  # 5 seconds (10 updates per second)
        t = i / 50.0  # 0 to 1 over 5 seconds
        
        # Create features with steady beat but varying frequencies
        features = {
            'beat_info': create_test_beat(
                bpm=120.0,
                position=1,
                strength=70.0
            ),
            'band_energies': create_test_audio_features(t)['band_energies']
        }
        
        # Update effect
        await effect.update(features)
        await asyncio.sleep(0.1)  # 100ms between updates

async def test_scene_transitions(effect: VirtualDJEffect):
    """Test scene transitions
    
    Tests:
    1. Scene activation/deactivation
    2. Parameter changes
    3. Smooth transitions
    """
    logger.info("\nTesting scene transitions...")
    
    scenes = [
        "pulse",
        "strobe",
        "rainbow",
        "chase",
        "music"
    ]
    
    for scene in scenes:
        logger.info(f"\nTesting scene: {scene}")
        
        # Activate scene
        await effect.handle_button({
            'name': scene,
            'page': None,
            'state': True
        })
        
        # Test with different parameters
        for brightness in [0.3, 0.6, 1.0]:
            await effect.handle_command({
                'id': 1,  # Brightness
                'param': brightness
            })
            await asyncio.sleep(1)
            
        # Deactivate scene
        await effect.handle_button({
            'name': scene,
            'page': None,
            'state': False
        })
        await asyncio.sleep(0.5)

async def main():
    """Run effect tests"""
    controller = LIFXController()
    
    try:
        # Discover lights
        logger.info("Discovering LIFX lights...")
        await controller.discover_lights()
        
        if not controller.lights:
            logger.error("No lights found!")
            return
            
        logger.info(f"Found {len(controller.lights)} lights")
        
        # Test basic light control
        logger.info("\nTesting basic light control...")
        await test_waveforms(controller)
        
        # Create effect for advanced tests
        effect = VirtualDJEffect(controller.lights)
        
        # Run advanced tests
        logger.info("\nStarting effect tests...")
        
        # Test BPM response
        await test_bpm_sequence(effect)
        
        # Test frequency response
        await test_frequency_response(effect)
        
        # Test scene transitions
        await test_scene_transitions(effect)
        
        logger.info("\nTests complete!")
        
    except Exception as e:
        logger.error(f"Error during testing: {e}")
    finally:
        await controller.cleanup()

if __name__ == "__main__":
    try:
        # Set up event loop policy for Windows
        if asyncio.get_event_loop_policy().__class__.__name__ == 'WindowsProactorEventLoopPolicy':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
