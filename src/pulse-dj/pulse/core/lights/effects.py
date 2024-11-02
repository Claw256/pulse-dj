"""Light Effects System

This module provides a system for creating and managing light effects
that can be synchronized with music beats and controlled via parameters.
Effects can be chained and transitioned smoothly.
"""

import asyncio
import logging
import math
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass
from enum import Enum, auto
from contextlib import AsyncExitStack

from .controller import LIFXController, LightColor, LightState

logger = logging.getLogger(__name__)

class EffectType(Enum):
    """Types of light effects"""
    PULSE = auto()    # Pulse on beat
    STROBE = auto()   # Rapid on/off
    RAINBOW = auto()  # Color cycle
    CHASE = auto()    # Moving light pattern
    MUSIC = auto()    # Audio reactive colors
    STATIC = auto()   # Static color

@dataclass
class EffectParams:
    """Effect parameters"""
    speed: float = 1.0          # Effect speed multiplier
    intensity: float = 1.0      # Effect intensity (0-1)
    color: Optional[LightColor] = None    # Base color (optional)
    
    def validate(self) -> None:
        """Validate parameters
        
        Raises:
            ValueError: If parameters are invalid
        """
        if not 0 <= self.speed <= 10:
            raise ValueError(f"Invalid speed: {self.speed}")
        if not 0 <= self.intensity <= 1:
            raise ValueError(f"Invalid intensity: {self.intensity}")
        if self.color:
            self.color.validate()

class Effect:
    """Base class for light effects"""
    
    def __init__(
        self,
        effect_type: EffectType,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        """Initialize effect
        
        Args:
            effect_type: Type of effect
            controller: Light controller
            params: Optional effect parameters
        """
        self.type = effect_type
        self.controller = controller
        self.params = params or EffectParams()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the effect"""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._run())
        
    async def stop(self) -> None:
        """Stop the effect"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
    async def _run(self) -> None:
        """Run the effect (override in subclasses)"""
        raise NotImplementedError

class PulseEffect(Effect):
    """Pulse lights on beat"""
    
    def __init__(
        self,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        super().__init__(EffectType.PULSE, controller, params)
        self._last_beat = 0
        self._beat_interval = 0.5  # Default 120 BPM
        
    async def _run(self) -> None:
        """Run pulse effect"""
        try:
            while self._running:
                # Calculate pulse brightness
                max_brightness = 65535  # 100%
                min_brightness = 16384  # 25%
                
                # Pulse brightness based on intensity
                pulse = min_brightness + (max_brightness - min_brightness) * self.params.intensity
                
                # Set colors
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        color = LightColor(0, 0, int(pulse), 3500)
                        await self.controller.set_color(light, color)
                        
                # Wait for fade
                await asyncio.sleep(self._beat_interval * 0.25)
                
                # Return to base brightness
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        color = LightColor(0, 0, 32767, 3500)  # 50%
                        await self.controller.set_color(light, color, int(self._beat_interval * 250))
                        
                # Wait for next beat
                await asyncio.sleep(self._beat_interval * 0.75)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in pulse effect: {e}")
            
    def update_timing(self, bpm: float) -> None:
        """Update beat timing
        
        Args:
            bpm: Beats per minute
        """
        self._beat_interval = 60.0 / bpm

class StrobeEffect(Effect):
    """Rapid on/off effect"""
    
    def __init__(
        self,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        super().__init__(EffectType.STROBE, controller, params)
        
    async def _run(self) -> None:
        """Run strobe effect"""
        try:
            while self._running:
                # Calculate timing
                period = 0.1 / self.params.speed  # Base 0.1s period
                on_time = period * 0.5  # 50% duty cycle
                
                # Strobe on
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        color = LightColor(0, 0, 65535, 3500)  # 100%
                        await self.controller.set_color(light, color)
                        
                await asyncio.sleep(on_time)
                
                # Strobe off
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        color = LightColor(0, 0, 0, 3500)  # 0%
                        await self.controller.set_color(light, color)
                        
                await asyncio.sleep(period - on_time)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in strobe effect: {e}")

class RainbowEffect(Effect):
    """Color cycle effect"""
    
    def __init__(
        self,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        super().__init__(EffectType.RAINBOW, controller, params)
        
    async def _run(self) -> None:
        """Run rainbow effect"""
        try:
            hue = 0
            while self._running:
                # Calculate color
                color = LightColor(
                    hue=hue,
                    saturation=65535,  # 100%
                    brightness=int(32767 * self.params.intensity),  # 50% * intensity
                    kelvin=3500
                )
                
                # Update lights
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        await self.controller.set_color(light, color, 100)
                        
                # Update hue
                hue = (hue + 1000) % 65535
                
                # Wait based on speed
                await asyncio.sleep(0.05 / self.params.speed)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in rainbow effect: {e}")

class ChaseEffect(Effect):
    """Moving light pattern effect"""
    
    def __init__(
        self,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        super().__init__(EffectType.CHASE, controller, params)
        
    async def _run(self) -> None:
        """Run chase effect"""
        try:
            lights = list(self.controller.lights.values())
            if not lights:
                return
                
            position = 0
            while self._running:
                # Calculate colors
                for i, light in enumerate(lights):
                    # Calculate distance from chase position
                    dist = abs(i - position)
                    intensity = max(0, 1 - (dist / len(lights)))
                    
                    # Set color based on intensity
                    color = LightColor(
                        hue=0,
                        saturation=0,
                        brightness=int(65535 * intensity * self.params.intensity),
                        kelvin=3500
                    )
                    
                    async with self.controller._light_lock:
                        await self.controller.set_color(light, color, 50)
                        
                # Update position
                position = (position + 1) % len(lights)
                
                # Wait based on speed
                await asyncio.sleep(0.2 / self.params.speed)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in chase effect: {e}")

class MusicEffect(Effect):
    """Audio reactive color effect"""
    
    def __init__(
        self,
        controller: LIFXController,
        params: Optional[EffectParams] = None
    ):
        super().__init__(EffectType.MUSIC, controller, params)
        self._features: Dict[str, float] = {}
        
    async def _run(self) -> None:
        """Run music effect"""
        try:
            while self._running:
                if not self._features:
                    await asyncio.sleep(0.1)
                    continue
                    
                # Calculate colors based on audio features
                bass = self._features.get('bass', 0)
                mids = self._features.get('mids', 0)
                highs = self._features.get('highs', 0)
                
                # Map frequencies to colors
                hue = int(bass * 21845)  # 0-21845 (red-yellow)
                saturation = int(mids * 65535)  # 0-65535
                brightness = int(highs * 65535 * self.params.intensity)
                
                color = LightColor(hue, saturation, brightness, 3500)
                
                # Update lights
                async with self.controller._light_lock:
                    for light in self.controller.lights.values():
                        await self.controller.set_color(light, color)
                        
                await asyncio.sleep(0.05)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in music effect: {e}")
            
    def update_features(self, features: Dict[str, float]) -> None:
        """Update audio features
        
        Args:
            features: Audio analysis features
        """
        self._features = features

class EffectManager:
    """Manages light effects"""
    
    def __init__(self, controller: LIFXController):
        """Initialize manager
        
        Args:
            controller: Light controller
        """
        self.controller = controller
        self._effects: Dict[EffectType, Effect] = {}
        self._active_effect: Optional[Effect] = None
        self._exit_stack = AsyncExitStack()
        
    async def start_effect(
        self,
        effect_type: EffectType,
        params: Optional[EffectParams] = None
    ) -> None:
        """Start an effect
        
        Args:
            effect_type: Type of effect to start
            params: Optional effect parameters
        """
        # Stop current effect
        if self._active_effect:
            await self._active_effect.stop()
            
        # Create effect if needed
        if effect_type not in self._effects:
            effect = self._create_effect(effect_type, params)
            if not effect:
                return
            self._effects[effect_type] = effect
            
        # Start new effect
        effect = self._effects[effect_type]
        if params:
            effect.params = params
        await effect.start()
        self._active_effect = effect
        
    def _create_effect(
        self,
        effect_type: EffectType,
        params: Optional[EffectParams] = None
    ) -> Optional[Effect]:
        """Create a new effect
        
        Args:
            effect_type: Type of effect to create
            params: Optional effect parameters
            
        Returns:
            Created effect or None if invalid type
        """
        if effect_type == EffectType.PULSE:
            return PulseEffect(self.controller, params)
        elif effect_type == EffectType.STROBE:
            return StrobeEffect(self.controller, params)
        elif effect_type == EffectType.RAINBOW:
            return RainbowEffect(self.controller, params)
        elif effect_type == EffectType.CHASE:
            return ChaseEffect(self.controller, params)
        elif effect_type == EffectType.MUSIC:
            return MusicEffect(self.controller, params)
        else:
            logger.error(f"Unknown effect type: {effect_type}")
            return None
            
    async def stop_effect(self) -> None:
        """Stop the current effect"""
        if self._active_effect:
            await self._active_effect.stop()
            self._active_effect = None
            
    def update_timing(self, bpm: float) -> None:
        """Update effect timing
        
        Args:
            bpm: Beats per minute
        """
        if isinstance(self._active_effect, PulseEffect):
            self._active_effect.update_timing(bpm)
            
    def update_features(self, features: Dict[str, float]) -> None:
        """Update audio features
        
        Args:
            features: Audio analysis features
        """
        if isinstance(self._active_effect, MusicEffect):
            self._active_effect.update_features(features)
            
    async def cleanup(self) -> None:
        """Clean up resources"""
        # Stop all effects
        for effect in self._effects.values():
            await effect.stop()
            
        self._effects.clear()
        self._active_effect = None
        
        # Clean up resources
        await self._exit_stack.aclose()
