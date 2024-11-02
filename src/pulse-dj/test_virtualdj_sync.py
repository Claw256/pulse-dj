"""VirtualDJ Light Sync

This module synchronizes LIFX lights with VirtualDJ using the OS2L protocol.
It handles beat detection to control light effects in real-time.
"""

import asyncio
import logging
import signal
import sys
import traceback
from typing import Dict, Any, Optional, Set
from contextlib import AsyncExitStack

from pulse.core.lights.controller import LIFXController
from pulse.core.os2l.server import OS2LServer
from pulse.core.os2l.protocol import BeatMessage, ButtonMessage, CommandMessage
from pulse.core.lights.effects import EffectManager, EffectType, EffectParams

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Enable debug logging for all modules
logging.getLogger('pulse').setLevel(logging.DEBUG)
logging.getLogger('aiolifx').setLevel(logging.DEBUG)

class VirtualDJSync:
    """Synchronizes LIFX lights with Virtual DJ"""
    
    def __init__(self):
        """Initialize sync"""
        self.controller = LIFXController()
        self.os2l_server = OS2LServer()
        self.effect_manager = EffectManager(self.controller)
        
        # State
        self._running = True
        self._shutdown_event = asyncio.Event()
        self._cleanup_complete = asyncio.Event()
        self._tasks: Set[asyncio.Task] = set()
        self._exit_stack = AsyncExitStack()
        
    def _on_beat(self, beat: Dict[str, Any]) -> None:
        """Handle beat updates from Virtual DJ
        
        Args:
            beat: Beat message from VirtualDJ
        """
        if not self._running:
            return
            
        try:
            logger.debug(
                f"Beat: BPM={beat['bpm']:.1f}, "
                f"Pos={beat['position']}, "
                f"Strength={beat['strength']:.1f}, "
                f"Change={beat['change']}"
            )
            
            # Update effect timing
            self.effect_manager.update_timing(beat['bpm'])
            
            # Start or update pulse effect
            params = EffectParams(
                intensity=beat['strength'] / 100.0  # Convert 0-100 to 0-1
            )
            
            # Create task to start effect
            task = asyncio.create_task(
                self.effect_manager.start_effect(EffectType.PULSE, params)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            
        except Exception as e:
            logger.error(f"Error in beat callback: {e}\n{traceback.format_exc()}")
            
    def _on_button(self, button: Dict[str, Any]) -> None:
        """Handle button updates from Virtual DJ
        
        Args:
            button: Button message from VirtualDJ
        """
        if not self._running:
            return
            
        try:
            # Log button press
            state = "pressed" if button['state'] else "released"
            logger.info(f"Button {button['name']} {state}")
            
            # Send feedback to VirtualDJ
            task = asyncio.create_task(
                self.os2l_server.send_feedback(
                    name=button['name'],
                    page=button.get('page'),
                    state=button['state']
                )
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            
        except Exception as e:
            logger.error(f"Error in button callback: {e}\n{traceback.format_exc()}")
            
    def _on_command(self, cmd: Dict[str, Any]) -> None:
        """Handle command updates from Virtual DJ
        
        Args:
            cmd: Command message from VirtualDJ
        """
        if not self._running:
            return
            
        try:
            # Log command
            logger.info(f"Command {cmd['id']} = {cmd['param']:.1%}")
            
        except Exception as e:
            logger.error(f"Error in command callback: {e}\n{traceback.format_exc()}")
            
    async def start(self) -> None:
        """Start the Virtual DJ sync"""
        try:
            # Print setup instructions
            self._print_instructions()
            
            # Discover LIFX lights
            logger.info("Discovering LIFX lights...")
            await self.controller.discover_lights()
            
            if not self.controller.lights:
                logger.error("No lights found!")
                return
                
            logger.info(f"Found {len(self.controller.lights)} lights")
            
            # Set up OS2L server callbacks
            self.os2l_server.set_beat_callback(self._on_beat)
            self.os2l_server.set_button_callback(self._on_button)
            self.os2l_server.set_command_callback(self._on_command)
            
            # Start OS2L server
            logger.info("Starting OS2L server...")
            server_task = asyncio.create_task(self.os2l_server.start())
            self._tasks.add(server_task)
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            # Cancel server task
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            
        except Exception as e:
            logger.error(f"Error in Virtual DJ sync: {e}\n{traceback.format_exc()}")
            await self.cleanup()
            
    async def cleanup(self) -> None:
        """Clean up resources"""
        if not self._running:
            return
            
        self._running = False
        logger.info("Starting cleanup...")
        
        # Cancel all pending tasks
        for task in self._tasks:
            task.cancel()
            
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Clean up resources
        await self._exit_stack.aclose()
        
        # Stop OS2L server
        try:
            await self.os2l_server.stop()
            logger.info("OS2L server stopped")
        except Exception as e:
            logger.error(f"Error stopping OS2L server: {e}")
        
        # Clean up effect manager
        try:
            await self.effect_manager.cleanup()
            logger.info("Effect manager cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up effect manager: {e}")
        
        # Clean up LIFX controller
        try:
            await self.controller.cleanup()
            logger.info("LIFX controller cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up LIFX controller: {e}")
            
        logger.info("Cleanup complete")
        self._cleanup_complete.set()
        
    def request_shutdown(self) -> None:
        """Request graceful shutdown"""
        if self._running:
            logger.info("Shutdown requested")
            self._shutdown_event.set()
            
    def _print_instructions(self) -> None:
        """Print setup instructions"""
        print("\nVirtualDJ Light Sync")
        print("=" * 80)
        
        print("\n1. Enable OS2L in VirtualDJ:")
        print("   - Open VirtualDJ")
        print("   - Go to Options > Preferences")
        print("   - Select Network tab")
        print("   - Enable OS2L option")
        
        print("\n2. Using the System:")
        print("   - Play music in VirtualDJ")
        print("   - Lights will automatically pulse in sync with the beat")
        print("   - Beat strength controls pulse intensity")
        
        print("\nStarting up...\n")
        print("=" * 80 + "\n")

async def main() -> None:
    """Main entry point"""
    sync = VirtualDJSync()
    
    def signal_handler() -> None:
        """Handle shutdown signals"""
        if not sync._shutdown_event.is_set():
            sync.request_shutdown()
    
    try:
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        if sys.platform != "win32":
            # Use signal handlers on non-Windows platforms
            for sig in ('SIGINT', 'SIGTERM'):
                loop.add_signal_handler(getattr(signal, sig), signal_handler)
        else:
            # Windows workaround
            def win_handler(type: Any, frame: Any) -> bool:
                signal_handler()
                return True
            signal.signal(signal.SIGINT, win_handler)
            signal.signal(signal.SIGTERM, win_handler)
        
        # Start sync and wait for completion
        await sync.start()
        await sync._cleanup_complete.wait()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        sync.request_shutdown()
        await sync._cleanup_complete.wait()
    except Exception as e:
        logger.error(f"Error in main: {e}\n{traceback.format_exc()}")
        sync.request_shutdown()
        await sync._cleanup_complete.wait()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            # Set up event loop policy for Windows
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Handle Ctrl+C gracefully
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
        sys.exit(1)
