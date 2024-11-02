"""Example usage of PULSE DJ"""

import asyncio
from pulse import PulseController

async def main():
    # Create PULSE controller
    controller = PulseController()
    
    try:
        # Start the system
        print("Starting PULSE DJ...")
        await controller.start()
        
        print("System running! Press Ctrl+C to stop.")
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await controller.close()

if __name__ == "__main__":
    asyncio.run(main())
