# Pulse DJ 🎵💡

Real-time LIFX light synchronization with VirtualDJ, featuring audio-reactive effects and beat detection.

## Features

- **VirtualDJ Integration**: Seamless synchronization with VirtualDJ through OS2L protocol
- **Audio Analysis**: Real-time frequency analysis with customizable bands
- **Light Effects**: Multiple effect types including:
  - Beat-synchronized pulses
  - Audio-reactive colors
  - Rainbow cycles
  - Chase patterns
  - Strobe effects
- **Smart Discovery**: Automatic LIFX light discovery across network interfaces
- **Adaptive Brightness**: Dynamic brightness adjustment based on beat strength
- **Multi-Light Support**: Control multiple LIFX lights simultaneously

## Requirements

- Python 3.7+
- VirtualDJ with OS2L enabled
- LIFX lights on the local network
- Windows/Linux/macOS

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/pulse-dj.git
cd pulse-dj
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

1. Enable OS2L in VirtualDJ:
   - Open VirtualDJ
   - Go to Settings -> Options
   - Search for "os2l"
   - Set OS2L option to "auto"

2. Run Pulse DJ:
```bash
python src/pulse-dj/test_virtualdj_sync.py
```

3. Play music in VirtualDJ and watch your lights sync to the beat!

## Configuration

The system provides several ways to customize behavior:

### Audio Analysis
- Adjustable frequency bands
- Configurable sample rate and window size
- Adaptive peak normalization

### Light Effects
- Customizable effect parameters:
  - Speed
  - Intensity
  - Color settings
  - Transition timing

### Network Settings
- Configurable OS2L server host/port
- Multi-interface light discovery
- Connection retry handling

## Architecture

Pulse DJ is built with a modular architecture:

- `audio`: Real-time audio analysis
- `lights`: LIFX light control
- `effects`: Effect system and implementations
- `os2l`: VirtualDJ protocol integration

## Development

### Project Structure
```
pulse-dj/
├── pulse/
│   ├── core/
│   │   ├── audio/      # Audio analysis
│   │   ├── lights/     # Light control
│   │   └── os2l/       # VirtualDJ integration
│   └── __init__.py
└── test_virtualdj_sync.py
```

### Running Tests
```bash
python -m pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- VirtualDJ for the OS2L protocol
- LIFX for their lighting API
- Python sounddevice library

## GitHub Repository Description

Audio-reactive LIFX light controller that synchronizes with VirtualDJ using real-time beat detection and customizable effects. Features multi-light support, frequency analysis, and an extensible effect system.
