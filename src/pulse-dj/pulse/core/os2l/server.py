"""OS2L Server Implementation

This module implements the server side of the OS2L protocol.
It acts as a DMX software that VirtualDJ can connect to.
"""

import asyncio
import json
import logging
import traceback
import socket
from typing import Dict, Any, Optional, Callable, Set
from zeroconf.asyncio import AsyncZeroconf
from zeroconf import ServiceInfo
from .protocol import (
    BeatMessage,
    ButtonMessage,
    CommandMessage,
    FeedbackMessage,
    parse_message,
    ProtocolError,
    ValidationError
)

logger = logging.getLogger(__name__)

class OS2LProtocol(asyncio.Protocol):
    """OS2L TCP Protocol Handler"""
    
    def __init__(self, server: 'OS2LServer'):
        self.server = server
        self.transport = None
        self.buffer = ""
        self.peername = None
        
    def connection_made(self, transport: asyncio.Transport):
        """Handle new connection"""
        self.transport = transport
        self.peername = transport.get_extra_info('peername')
        logger.info(f"Client connected from {self.peername}")
        self.server.connections.add(self)
        
    def connection_lost(self, exc):
        """Handle connection lost"""
        logger.info(f"Client disconnected from {self.peername}")
        self.server.connections.remove(self)
        
    def data_received(self, data: bytes):
        """Handle received data
        
        Args:
            data: Received bytes
        """
        try:
            # Log raw data for debugging
            logger.debug(f"Received data from {self.peername}: {data}")
            
            # Add to buffer
            self.buffer += data.decode('utf-8')
            
            # Process complete messages
            while True:
                # Find start of next message
                try:
                    start = self.buffer.index('{')
                except ValueError:
                    # No start of message found
                    self.buffer = ""
                    break
                    
                # Find end of message
                try:
                    end = self.buffer.index('}', start) + 1
                except ValueError:
                    # Incomplete message
                    self.buffer = self.buffer[start:]
                    break
                    
                # Extract and parse message
                message = self.buffer[start:end]
                self.buffer = self.buffer[end:]
                
                logger.debug(f"Processing message: {message}")
                
                asyncio.create_task(
                    self.server.handle_message(self, message)
                )
                
        except Exception as e:
            logger.error(f"Error handling data: {e}")
            self.buffer = ""  # Clear buffer on error
            
    def send_message(self, message: str):
        """Send message to client
        
        Args:
            message: Message string to send
        """
        try:
            if self.transport and not self.transport.is_closing():
                logger.debug(f"Sending message to {self.peername}: {message}")
                self.transport.write(f"{message}\n".encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending message: {e}")

class OS2LServer:
    """OS2L server implementation
    
    This class:
    1. Runs a TCP server
    2. Registers OS2L service via DNS-SD
    3. Accepts connections from VirtualDJ
    4. Handles OS2L messages
    5. Sends feedback to VirtualDJ
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        """Initialize server
        
        Args:
            host: Server hostname
            port: Server port
        """
        self.host = host
        self.port = port
        self.server = None
        self.connections: Set[OS2LProtocol] = set()
        self._running = True
        self._aiozc = None
        self._service_info = None
        
        # Callbacks
        self._beat_callback = None
        self._button_callback = None
        self._command_callback = None
        
    def set_beat_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback for beat messages"""
        self._beat_callback = callback
        
    def set_button_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback for button messages"""
        self._button_callback = callback
        
    def set_command_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback for command messages"""
        self._command_callback = callback
        
    async def handle_message(self, protocol: OS2LProtocol, msg_str: str):
        """Handle incoming OS2L message
        
        Args:
            protocol: Protocol instance that received the message
            msg_str: Message string
        """
        try:
            # Parse message
            message = parse_message(msg_str)
            if not message:
                return
                
            # Handle based on message type
            if isinstance(message, BeatMessage):
                if self._beat_callback:
                    self._beat_callback({
                        'bpm': message.bpm,
                        'position': message.pos,
                        'strength': message.strength,
                        'change': message.change
                    })
                    
            elif isinstance(message, ButtonMessage):
                if self._button_callback:
                    self._button_callback({
                        'name': message.name,
                        'page': message.page,
                        'state': message.state == "on"
                    })
                    
            elif isinstance(message, CommandMessage):
                if self._command_callback:
                    self._command_callback({
                        'id': message.id,
                        'param': message.param / 100.0  # Convert to 0-1 range
                    })
                    
        except (ProtocolError, ValidationError) as e:
            logger.warning(f"Invalid message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}\n{traceback.format_exc()}")
            
    async def send_feedback(self, name: str, page: Optional[str], state: bool):
        """Send feedback to VirtualDJ
        
        Args:
            name: Button name
            page: Page name (optional)
            state: Button state
        """
        try:
            # Create feedback message
            message = FeedbackMessage(name=name, page=page, state=state)
            
            # Send to all connections
            if self.connections:
                for conn in self.connections:
                    conn.send_message(message.to_json())
                    
        except Exception as e:
            logger.error(f"Error sending feedback: {e}\n{traceback.format_exc()}")
            
    async def register_service(self):
        """Register OS2L service via DNS-SD"""
        try:
            self._aiozc = AsyncZeroconf()
            
            # Convert IP address to proper format
            addr_bytes = socket.inet_pton(socket.AF_INET, self.host)
            
            # Create service info
            self._service_info = ServiceInfo(
                "_os2l._tcp.local.",
                "LIFX Light Sync._os2l._tcp.local.",
                addresses=[addr_bytes],
                port=self.port,
                properties={},
                server="lifx-sync.local."
            )
            
            # Register service
            await self._aiozc.async_register_service(self._service_info)
            logger.info("Registered OS2L service via DNS-SD")
            
        except Exception as e:
            logger.error(f"Error registering service: {e}")
            raise
            
    async def start(self):
        """Start the OS2L server"""
        try:
            # Create server
            loop = asyncio.get_running_loop()
            self.server = await loop.create_server(
                lambda: OS2LProtocol(self),
                self.host,
                self.port
            )
            
            # Register service
            await self.register_service()
            
            logger.info(f"OS2L server running at {self.host}:{self.port}")
            
            # Keep running
            async with self.server:
                await self.server.serve_forever()
                
        except Exception as e:
            logger.error(f"Error starting server: {e}\n{traceback.format_exc()}")
            
    async def stop(self):
        """Stop the OS2L server"""
        self._running = False
        
        # Unregister service
        if self._aiozc and self._service_info:
            await self._aiozc.async_unregister_service(self._service_info)
            await self._aiozc.async_close()
            
        # Close connections
        for conn in self.connections:
            if conn.transport:
                conn.transport.close()
        self.connections.clear()
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        logger.info("OS2L server stopped")
