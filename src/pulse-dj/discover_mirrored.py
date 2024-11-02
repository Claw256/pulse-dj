"""LIFX discovery test using WSL mirrored networking mode"""

import socket
import struct
import time
import sys
import subprocess

BROADCAST_MAC = "00:00:00:00:00:00"
HEADER_SIZE = 36

def check_network():
    """Check network configuration"""
    print("\nChecking Network Configuration")
    print("----------------------------")
    
    try:
        # Get network interfaces
        result = subprocess.run(['ip', 'addr'], capture_output=True, text=True)
        print("\nNetwork interfaces:")
        print(result.stdout)
        
        # Get routing
        result = subprocess.run(['ip', 'route'], capture_output=True, text=True)
        print("\nRouting table:")
        print(result.stdout)
        
        # Try to ping LIFX lights
        print("\nTesting connectivity to LIFX lights:")
        lifx_ips = [
            "192.168.4.14",
            "192.168.4.23",
            "192.168.4.13",
            "192.168.4.15"
        ]
        
        for ip in lifx_ips:
            try:
                result = subprocess.run(['ping', '-c', '1', '-W', '1', ip], 
                                     capture_output=True, text=True)
                print(f"\n{ip}: {'Reachable' if result.returncode == 0 else 'Unreachable'}")
                print(result.stdout)
            except Exception as e:
                print(f"Error pinging {ip}: {e}")
                
    except Exception as e:
        print(f"Error checking network: {e}")

def convert_mac_to_int(addr):
    """Convert MAC address to integer (little endian)"""
    reverse_bytes = addr.split(":")
    reverse_bytes.reverse()
    addr_str = "".join(reverse_bytes)
    return int(addr_str, 16)

def create_discovery_packet():
    """Create a GetService discovery packet according to LIFX protocol"""
    # Frame
    size = HEADER_SIZE  # No payload for GetService
    protocol = 1024
    addressable = 1
    tagged = 1  # Must be 1 for broadcast
    origin = 0
    source_id = 0  # Source identifier
    
    frame = struct.pack(
        "<HHI",
        size,           # 16 bits
        ((origin & 0b11) << 14) |
        ((tagged & 0b1) << 13) |
        ((addressable & 0b1) << 12) |
        (protocol & 0b111111111111),  # 16 bits
        source_id       # 32 bits
    )
    
    # Frame Address
    target_addr = convert_mac_to_int(BROADCAST_MAC)  # Broadcast address
    ack_required = 0
    response_required = 1
    seq_num = 0
    
    frame_addr = struct.pack(
        "<Q6sBB",
        target_addr,    # 64 bits
        b'\x00' * 6,    # Reserved 48 bits
        ((0 & 0b111111) << 2) |
        ((ack_required & 0b1) << 1) |
        (response_required & 0b1),  # 8 bits
        seq_num         # 8 bits
    )
    
    # Protocol Header
    msg_type = 2  # GetService = 2
    
    protocol_header = struct.pack(
        "<QHH",
        0,              # Reserved 64 bits
        msg_type,       # 16 bits
        0               # Reserved 16 bits
    )
    
    packet = frame + frame_addr + protocol_header
    
    # Debug packet contents
    print("\nDiscovery Packet Details:")
    print(f"Size: {len(packet)} bytes")
    print(f"Hex: {' '.join([f'{b:02x}' for b in packet])}")
    
    return packet

def try_discovery():
    """Attempt LIFX discovery"""
    print("\nAttempting LIFX Discovery")
    print("------------------------")
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1)
    
    try:
        # Bind to all interfaces
        sock.bind(('0.0.0.0', 56700))
        print(f"\nBound to all interfaces on port 56700")
        
        # Create discovery packet
        packet = create_discovery_packet()
        
        # Known LIFX lights
        known_lights = {
            "d0:73:d5:6e:44:6b": "192.168.4.14",
            "d0:73:d5:6f:09:00": "192.168.4.23",
            "d0:73:d5:6e:68:46": "192.168.4.13",
            "d0:73:d5:6e:71:d4": "192.168.4.15"
        }
        
        print("\nKnown LIFX lights:")
        for mac, ip in known_lights.items():
            print(f"MAC: {mac} -> IP: {ip}")
        
        # Try broadcast first
        print("\nTrying broadcast discovery...")
        broadcast_addrs = [
            '255.255.255.255',    # Global broadcast
            '192.168.4.255',      # Local subnet broadcast
        ]
        
        for addr in broadcast_addrs:
            print(f"\nSending to {addr}:56700")
            try:
                sock.sendto(packet, (addr, 56700))
                print(f"Broadcast packet sent to {addr}")
                
                # Listen for responses
                start_time = time.time()
                while time.time() - start_time < 2:
                    try:
                        data, (ip, port) = sock.recvfrom(1024)
                        if ip != '192.168.4.17':  # Ignore our own broadcasts
                            print(f"\nReceived {len(data)} bytes from {ip}:{port}")
                            print(f"Response: {' '.join([f'{b:02x}' for b in data])}")
                    except socket.timeout:
                        continue
            except Exception as e:
                print(f"Error with broadcast to {addr}: {e}")
        
        # Try direct connection to each light
        print("\nTrying direct connection to lights...")
        for mac, ip in known_lights.items():
            print(f"\nTrying {mac} at {ip}")
            try:
                # Create unicast packet (not tagged)
                target_addr = convert_mac_to_int(mac)
                frame = struct.pack(
                    "<HHI",
                    HEADER_SIZE,
                    ((0 & 0b11) << 14) |
                    ((0 & 0b1) << 13) |  # tagged = 0 for unicast
                    ((1 & 0b1) << 12) |
                    (1024 & 0b111111111111),
                    0  # source_id
                )
                
                frame_addr = struct.pack(
                    "<Q6sBB",
                    target_addr,
                    b'\x00' * 6,
                    ((0 & 0b111111) << 2) |
                    ((0 & 0b1) << 1) |
                    (1 & 0b1),  # response_required = 1
                    0  # seq_num
                )
                
                protocol_header = struct.pack(
                    "<QHH",
                    0,
                    2,  # GetService
                    0
                )
                
                packet = frame + frame_addr + protocol_header
                
                # Send packet
                sock.sendto(packet, (ip, 56700))
                print(f"Sent packet to {ip}")
                print(f"Packet: {' '.join([f'{b:02x}' for b in packet])}")
                
                # Listen for response
                try:
                    data, addr = sock.recvfrom(1024)
                    if addr[0] != '192.168.4.17':  # Ignore our own broadcasts
                        print(f"Received {len(data)} bytes from {addr[0]}:{addr[1]}")
                        print(f"Response: {' '.join([f'{b:02x}' for b in data])}")
                except socket.timeout:
                    print(f"No response from {ip}")
                except Exception as e:
                    print(f"Error receiving from {ip}: {e}")
            except Exception as e:
                print(f"Error sending to {ip}: {e}")
                
    except Exception as e:
        print(f"\nError during discovery: {e}")
    finally:
        sock.close()

def main():
    """Main function"""
    print("\nLIFX Mirrored Network Discovery Test")
    print("---------------------------------")
    
    # Check network configuration
    check_network()
    
    # Try discovery
    try_discovery()

if __name__ == "__main__":
    main()
