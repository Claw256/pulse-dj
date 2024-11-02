"""LIFX Light Controller using aiolifx"""

import asyncio
import logging
import socket
import ifaddr
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto
from aiolifx import LifxDiscovery
from aiolifx.aiolifx import Light
from zeroconf.asyncio import AsyncZeroconf

logger = logging.getLogger(__name__)

class LightState(Enum):
    """Light power state"""
    OFF = auto()
    ON = auto()

@dataclass
class LightColor:
    """Light color settings"""
    hue: int         # 0-65535
    saturation: int  # 0-65535
    brightness: int  # 0-65535
    kelvin: int     # 1500-9000 (color temperature)

    def validate(self) -> None:
        """Validate color parameters"""
        if not 0 <= self.hue <= 65535:
            raise ValueError(f"Invalid hue: {self.hue}")
        if not 0 <= self.saturation <= 65535:
            raise ValueError(f"Invalid saturation: {self.saturation}")
        if not 0 <= self.brightness <= 65535:
            raise ValueError(f"Invalid brightness: {self.brightness}")
        if not 1500 <= self.kelvin <= 9000:
            raise ValueError(f"Invalid kelvin: {self.kelvin}")

class LIFXController:
    """Controller for LIFX lights using aiolifx"""
    
    def __init__(self):
        self.lights: Dict[str, Light] = {}
        self.loop = asyncio.get_event_loop()
        self._discovery_complete = asyncio.Event()
        self._discovery = None
        self._discovery_task = None
        self._light_lock = asyncio.Lock()
        
    def _on_light_state(self, light: Light, *args):
        """Handle light state updates"""
        mac = light.mac_addr
        if isinstance(mac, bytes):
            mac = mac.hex(':')
        if mac not in self.lights:
            self.lights[mac] = light
            logger.info(f"Found light {mac} at {light.ip_addr}")
            
    async def discover_lights(self):
        """Discover LIFX lights on the network"""
        logger.info("Starting LIFX light discovery...")
        
        # Get all network interfaces
        adapters = ifaddr.get_adapters()
        logger.debug(f"Found {len(adapters)} network adapters")
        
        # Start discovery on each interface
        aiozc = AsyncZeroconf()
        discovery_tasks = []
        
        try:
            for adapter in adapters:
                logger.debug(f"Checking adapter {adapter.nice_name}")
                
                # Check each IP on the adapter
                for ip in adapter.ips:
                    if ip.is_IPv4:
                        ip_str = ip.ip
                        logger.debug(f"Found IPv4 interface: {adapter.nice_name} ({ip_str})")
                        
                        # Skip loopback and link-local addresses
                        if ip_str.startswith('127.') or ip_str.startswith('169.254.'):
                            logger.debug(f"Skipping interface {ip_str}")
                            continue
                            
                        # Create discovery object
                        discovery = LifxDiscovery(
                            self.loop,
                            parent=self,
                            discovery_interval=1
                        )
                        
                        try:
                            # Start discovery service
                            logger.debug(f"Starting discovery on {ip_str}")
                            await discovery.start(listen_ip=ip_str)
                            
                            # Store discovery object to clean up later
                            if not self._discovery:
                                self._discovery = discovery
                                
                        except Exception as e:
                            logger.warning(f"Error starting discovery on {ip_str}: {e}")
                            continue
            
            # Wait for initial discovery period
            logger.debug("Waiting for initial discovery period...")
            await asyncio.sleep(5)  # Give more time for discovery
            
            # Log discovery results
            if not self.lights:
                logger.warning("No lights found during initial discovery")
                logger.debug("Network interfaces used:")
                for adapter in adapters:
                    for ip in adapter.ips:
                        if ip.is_IPv4 and not ip.ip.startswith('127.') and not ip.ip.startswith('169.254.'):
                            logger.debug(f"  {adapter.nice_name} ({ip.ip})")
            else:
                logger.info(f"Found {len(self.lights)} LIFX lights:")
                for mac, light in self.lights.items():
                    logger.info(f"  {mac} at {light.ip_addr}")
            
            # Turn on all lights
            for light in self.lights.values():
                await self.set_power(light, True)
                
        except Exception as e:
            logger.error(f"Error during light discovery: {e}", exc_info=True)
            
        finally:
            await aiozc.async_close()
            
    async def set_power(self, light: Light, power: bool):
        """Set light power state"""
        try:
            async with self._light_lock:
                light.set_power(65535 if power else 0, 0)
                mac = light.mac_addr
                if isinstance(mac, bytes):
                    mac = mac.hex(':')
                logger.info(f"Set power {'on' if power else 'off'} for light {mac}")
                return True
        except Exception as e:
            logger.error(f"Error setting power: {e}")
            return False
            
    async def set_color(self, light: Light, color: LightColor, duration: int = 0):
        """Set light color
        
        Args:
            light: Light to control
            color: Color settings
            duration: Transition time in milliseconds
        """
        try:
            color.validate()
            async with self._light_lock:
                light.set_color([color.hue, color.saturation, color.brightness, color.kelvin], duration)
                return True
        except Exception as e:
            logger.error(f"Error setting color: {e}")
            return False
            
    async def cleanup(self):
        """Clean up resources"""
        # Turn off all lights
        for light in self.lights.values():
            await self.set_power(light, False)
        self.lights = {}
        
        # Clean up discovery
        if self._discovery:
            self._discovery.cleanup()
            self._discovery = None
            
    def register(self, light: Light):
        """Register a light with the controller"""
        mac = light.mac_addr
        if isinstance(mac, bytes):
            mac = mac.hex(':')
        if mac not in self.lights:
            self.lights[mac] = light
            light.get_state_handler = self._on_light_state
            logger.info(f"Registered light {mac} at {light.ip_addr}")
            
    def unregister(self, light: Light):
        """Unregister a light from the controller"""
        mac = light.mac_addr
        if isinstance(mac, bytes):
            mac = mac.hex(':')
        if mac in self.lights:
            del self.lights[mac]
            logger.info(f"Unregistered light {mac}")
