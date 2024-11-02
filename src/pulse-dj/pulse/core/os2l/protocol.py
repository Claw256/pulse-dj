"""OS2L Protocol Implementation

This module implements the OS2L (Open Sound to Light) protocol for VirtualDJ.
See: https://www.virtualdj.com/wiki/os2l.html
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProtocolError(Exception):
    """Base class for protocol errors"""
    pass

class ValidationError(ProtocolError):
    """Raised when message validation fails"""
    pass

@dataclass
class OS2LMessage:
    """Base class for OS2L messages"""
    evt: str  # Event type
    
    def validate(self):
        """Validate message fields"""
        if not self.evt:
            raise ValidationError("Event type cannot be empty")
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {'evt': self.evt}
        
    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict())

@dataclass
class BeatMessage(OS2LMessage):
    """Beat information from VirtualDJ
    
    Fields:
    - evt: "beat"
    - pos: Beat position
    - bpm: Current BPM (30-300)
    - strength: Beat strength (0-100)
    - change: Whether BPM changed
    """
    pos: int
    bpm: float
    strength: float
    change: bool
    
    def __init__(self, pos: int, bpm: float, strength: float = 100.0, change: bool = False):
        super().__init__(evt="beat")
        self.pos = pos
        self.bpm = bpm
        self.strength = strength
        self.change = change
    
    def validate(self):
        """Validate beat message fields"""
        super().validate()
        if self.evt != "beat":
            raise ValidationError(f"Invalid event type for beat message: {self.evt}")
        if not (30 <= self.bpm <= 300):
            raise ValidationError(f"BPM must be between 30 and 300, got {self.bpm}")
        if not (0 <= self.strength <= 100):
            raise ValidationError(f"Strength must be between 0 and 100, got {self.strength}")
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert beat message to dictionary"""
        return {
            'evt': self.evt,
            'pos': self.pos,
            'bpm': self.bpm,
            'strength': self.strength,
            'change': self.change
        }

@dataclass
class ButtonMessage(OS2LMessage):
    """Button state from VirtualDJ
    
    Fields:
    - evt: "btn"
    - name: Button name/ID
    - page: Optional page name
    - state: Button pressed/released ("on"/"off")
    """
    name: str
    state: str
    page: Optional[str] = None
    
    def __init__(self, name: str, state: str, page: Optional[str] = None):
        super().__init__(evt="btn")
        self.name = name
        self.state = state
        self.page = page
    
    def validate(self):
        """Validate button message fields"""
        super().validate()
        if self.evt != "btn":
            raise ValidationError(f"Invalid event type for button message: {self.evt}")
        if not self.name:
            raise ValidationError("Button name cannot be empty")
        if self.state not in ("on", "off"):
            raise ValidationError(f"Invalid button state: {self.state}")
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert button message to dictionary"""
        msg = {
            'evt': self.evt,
            'name': self.name,
            'state': self.state
        }
        if self.page:
            msg['page'] = self.page
        return msg

@dataclass
class CommandMessage(OS2LMessage):
    """Command value from VirtualDJ
    
    Fields:
    - evt: "cmd"
    - id: Command ID (1-4)
    - param: Parameter value (0-100%)
    """
    id: int
    param: float
    
    def __init__(self, id: int, param: float):
        super().__init__(evt="cmd")
        self.id = id
        self.param = param
    
    def validate(self):
        """Validate command message fields"""
        super().validate()
        if self.evt != "cmd":
            raise ValidationError(f"Invalid event type for command message: {self.evt}")
        if not (1 <= self.id <= 4):
            raise ValidationError(f"Command ID must be between 1 and 4, got {self.id}")
        if not (0 <= self.param <= 100):
            raise ValidationError(f"Parameter must be between 0 and 100%, got {self.param}")
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert command message to dictionary"""
        return {
            'evt': self.evt,
            'id': self.id,
            'param': self.param
        }

@dataclass
class FeedbackMessage(OS2LMessage):
    """Feedback message to VirtualDJ
    
    Fields:
    - evt: "feedback"
    - name: Button name/ID
    - page: Optional page name
    - state: Button state ("on"/"off")
    """
    name: str
    state: str
    page: Optional[str] = None
    
    def __init__(self, name: str, state: bool, page: Optional[str] = None):
        super().__init__(evt="feedback")
        self.name = name
        self.state = "on" if state else "off"
        self.page = page
    
    def validate(self):
        """Validate feedback message fields"""
        super().validate()
        if self.evt != "feedback":
            raise ValidationError(f"Invalid event type for feedback message: {self.evt}")
        if not self.name:
            raise ValidationError("Button name cannot be empty")
        if self.state not in ("on", "off"):
            raise ValidationError(f"Invalid button state: {self.state}")
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert feedback message to dictionary"""
        msg = {
            'evt': self.evt,
            'name': self.name,
            'state': self.state
        }
        if self.page:
            msg['page'] = self.page
        return msg

def parse_message(data: str) -> Optional[OS2LMessage]:
    """Parse OS2L message from JSON string
    
    Args:
        data: JSON string from VirtualDJ
        
    Returns:
        Parsed OS2L message or None if parsing fails
        
    Raises:
        ValidationError: If message validation fails
        ValueError: If message type is unknown
    """
    try:
        msg = json.loads(data)
        logger.debug(f"Parsing message: {msg}")
        
        if 'evt' not in msg:
            raise ValueError("Missing 'evt' field in message")
            
        evt = msg['evt']
        
        # Parse beat message
        if evt == 'beat':
            message = BeatMessage(
                pos=int(msg['pos']),
                bpm=float(msg['bpm']),
                strength=float(msg.get('strength', 100.0)),
                change=bool(msg.get('change', False))
            )
            
        # Parse button message
        elif evt == 'btn':
            message = ButtonMessage(
                name=str(msg['name']),
                state=str(msg['state']),
                page=msg.get('page')
            )
            
        # Parse command message
        elif evt == 'cmd':
            message = CommandMessage(
                id=int(msg['id']),
                param=float(msg['param'])
            )
            
        else:
            raise ValueError(f"Unknown event type: {evt}")
            
        # Validate message
        message.validate()
        return message
        
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {e}")
        return None
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"Invalid message format: {e}")
        return None
    except ValidationError as e:
        logger.warning(f"Message validation failed: {e}")
        return None
