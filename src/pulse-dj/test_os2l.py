"""Test OS2L server implementation

This test verifies that our OS2L server:
1. Properly registers service
2. Accepts connections from VirtualDJ
3. Handles beat/button/command messages
4. Sends feedback correctly
"""

import asyncio
import logging
import sys
import traceback
from typing import Dict, Any, Optional
from pulse.core.os2l.server import OS2LServer
from pulse.core.os2l.protocol import BeatMessage, ButtonMessage, CommandMessage

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OS2LTest:
    """Test OS2L server functionality"""
    
    def __init__(self):
        self.server = OS2LServer()
        self._running = True
        self._shutdown_event = asyncio.Event()
        self._cleanup_complete = asyncio.Event()
        
    def _on_beat(self, beat_info: Dict[str, Any]):
        """Handle beat updates"""
        try:
            logger.info(
                f"Beat: BPM={beat_info['bpm']:.1f}, "
                f"Position={beat_info['position']}, "
                f"Strength={beat_info['strength']:.1f}"
            )
        except Exception as e:
            logger.error(f"Error in beat callback: {e}\n{traceback.format_exc()}")
            
    def _on_button(self, button_info: Dict[str, Any]):
        """Handle button updates"""
        try:
            # Log button press
            state = "pressed" if button_info['state'] else "released"
            logger.info(f"Button {button_info['name']} {state}")
            
            # Send feedback to VirtualDJ
            asyncio.create_task(
                self.server.send_feedback(
                    name=button_info['name'],
                    page=button_info.get('page'),
                    state=button_info['state']
                )
            )
            
        except Exception as e:
            logger.error(f"Error in button callback: {e}\n{traceback.format_exc()}")
            
    def _on_command(self, command_info: Dict[str, Any]):
        """Handle command updates"""
        try:
            # Log command
            logger.info(f"Command {command_info['id']} = {command_info['param']:.1%}")
            
        except Exception as e:
            logger.error(f"Error in command callback: {e}\n{traceback.format_exc()}")
            
    async def start(self):
        """Start the test"""
        try:
            # Set up server callbacks
            self.server.set_beat_callback(self._on_beat)
            self.server.set_button_callback(self._on_button)
            self.server.set_command_callback(self._on_command)
            
            # Start OS2L server
            logger.info("Starting OS2L server...")
            server_task = asyncio.create_task(self.server.start())
            
            # Print instructions
            print("\nOS2L Server Test")
            print("=" * 80)
            print("\n1. Enable OS2L in VirtualDJ:")
            print("   - Open VirtualDJ")
            print("   - Go to Options > Preferences")
            print("   - Select Network tab")
            print("   - Enable OS2L option")
            print("\n2. Test Features:")
            print("   - Play music to test beat detection")
            print("   - Use DMX pads to test buttons")
            print("   - Use faders to test commands")
            print("   - Check VirtualDJ UI for feedback")
            print("\n3. Press Ctrl+C to exit")
            print("\nWaiting for VirtualDJ to connect...\n")
            print("=" * 80 + "\n")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            # Cancel server task
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            
        except Exception as e:
            logger.error(f"Error in test: {e}\n{traceback.format_exc()}")
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources"""
        if not self._running:
            return
            
        self._running = False
        logger.info("Starting cleanup...")
        
        # Stop OS2L server
        try:
            await self.server.stop()
            logger.info("OS2L server stopped")
        except Exception as e:
            logger.error(f"Error stopping server: {e}")
            
        logger.info("Cleanup complete")
        self._cleanup_complete.set()
        
    def request_shutdown(self):
        """Request graceful shutdown"""
        if self._running:
            logger.info("Shutdown requested")
            self._shutdown_event.set()

async def main():
    """Main entry point"""
    test = OS2LTest()
    
    def signal_handler():
        """Handle shutdown signals"""
        if not test._shutdown_event.is_set():
            test.request_shutdown()
    
    try:
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        if sys.platform != "win32":
            # Use signal handlers on non-Windows platforms
            for sig in ('SIGINT', 'SIGTERM'):
                loop.add_signal_handler(getattr(signal, sig), signal_handler)
        else:
            # Windows workaround
            def win_handler(type, frame):
                signal_handler()
                return True
            import signal
            signal.signal(signal.SIGINT, win_handler)
            signal.signal(signal.SIGTERM, win_handler)
        
        # Start test and wait for completion
        await test.start()
        await test._cleanup_complete.wait()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        test.request_shutdown()
        await test._cleanup_complete.wait()
    except Exception as e:
        logger.error(f"Error in main: {e}\n{traceback.format_exc()}")
        test.request_shutdown()
        await test._cleanup_complete.wait()

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
