#!/usr/bin/env python3
#
# Script to print the number of seconds that each unique vehicle is in the
#  tracking volume per hour.
#
#
# Usage:
#    python adsb_counter.py [username] [password]
#    
# Or set environment variables:
#  export MQTT_USER=myuser
#  export MQTT_PASSWD=mypassword
#  python adsb_counter.py
#
# Command line arguments take precedence over environment variables

import paho.mqtt.client as mqtt
import json
import threading
import time
import os
import sys
import argparse
from collections import defaultdict
from datetime import datetime

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "adsb/vehicles/#"
PRINT_INTERVAL_SECONDS = 60   # 1 minutes

hex_counts = defaultdict(int)
lock = threading.Lock()
running = True


def get_credentials():
    """
    Get MQTT credentials from command line args or environment variables.
    Command line arguments take precedence.
    
    Returns:
        tuple: (username, password) - either or both may be None
    """
    parser = argparse.ArgumentParser(
        description='ADSB Vehicle Counter - Counts MQTT messages by hex ID',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Environment Variables:
  MQTT_USER     MQTT username (used if not provided via command line)
  MQTT_PASSWD   MQTT password (used if not provided via command line)

Examples:
  %(prog)s myuser mypassword
  %(prog)s --user myuser --password mypassword
  MQTT_USER=myuser MQTT_PASSWD=mypassword %(prog)s
        '''
    )
    parser.add_argument(
        'positional_user',
        nargs='?',
        default=None,
        help='MQTT username (positional argument)'
    )
    parser.add_argument(
        'positional_password',
        nargs='?',
        default=None,
        help='MQTT password (positional argument)'
    )
    parser.add_argument(
        '-u', '--user',
        default=None,
        help='MQTT username (alternative to positional argument)'
    )
    parser.add_argument(
        '-p', '--password',
        default=None,
        help='MQTT password (alternative to positional argument)'
    )
    parser.add_argument(
        '-b', '--broker',
        default=None,
        help=f'MQTT broker address (default: {MQTT_BROKER})'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help=f'MQTT broker port (default: {MQTT_PORT})'
    )
    args = parser.parse_args()

    # determine username: positional > flag > environment variable
    username = (
        args.positional_user or 
        args.user or 
        os.environ.get('MQTT_USER')
    )

    # determine password: positional > flag > environment variable
    password = (
        args.positional_password or 
        args.password or 
        os.environ.get('MQTT_PASSWD')
    )
    broker = args.broker or MQTT_BROKER
    port = args.port or MQTT_PORT
    return username, password, broker, port

def on_connect(client, userdata, flags, reason_code, properties=None):
    """Callback when connected to MQTT broker."""
    broker_info = userdata.get('broker_info', 'broker')
    if reason_code == 0:
        print(f"[{timestamp()}] Connected to MQTT broker at {broker_info}")
        client.subscribe(MQTT_TOPIC)
        print(f"[{timestamp()}] Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"[{timestamp()}] Failed to connect, return code: {reason_code}")

def on_disconnect(client, userdata, reason_code, properties=None):
    """Callback when disconnected from MQTT broker."""
    print(f"[{timestamp()}] Disconnected from broker (code: {reason_code})")

def on_message(client, userdata, msg):
    """Callback when a message is received."""
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        hex_value = payload.get('hex')

        if hex_value:
            with lock:
                hex_counts[hex_value] += 1

    except json.JSONDecodeError:
        pass  # Silently ignore malformed JSON
    except Exception as e:
        print(f"[{timestamp()}] Error processing message: {e}")

def timestamp():
    """Return current timestamp string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def print_report_and_reset():
    """Print the counts report and reset the counter."""
    global hex_counts

    with lock:
        print(f"\n{'='*60}")
        print(f"  ADSB VEHICLE COUNT REPORT")
        print(f"  Generated: {timestamp()}")
        print(f"{'='*60}")

        if hex_counts:
            # Sort by count (descending), then by hex ID
            sorted_counts = sorted(hex_counts.items(), 
                                   key=lambda x: (-x[1], x[0]))

            print(f"{'HEX ID':<15} {'MESSAGE COUNT':>15}")
            print(f"{'-'*30}")

            for hex_val, count in sorted_counts:
                print(f"{hex_val:<15} {count:>15}")

            print(f"{'-'*30}")
            print(f"{'TOTAL UNIQUE AIRCRAFT:':<20} {len(hex_counts):>10}")
            print(f"{'TOTAL MESSAGES:':<20} {sum(hex_counts.values()):>10}")
        else:
            print("  No messages received during this period.")

        print(f"{'='*60}")
        print(f"  Resetting counters. Next report in {PRINT_INTERVAL_SECONDS // 60} minutes...")
        print(f"{'='*60}\n")

        # Clear the counts for the next period
        hex_counts.clear()

def timer_thread_func():
    """Thread function that triggers reports every PRINT_INTERVAL_SECONDS."""
    global running

    while running:
        # Sleep in small increments to allow faster shutdown
        for _ in range(PRINT_INTERVAL_SECONDS):
            if not running:
                return
            time.sleep(1)

        if running:
            print_report_and_reset()

def main():
    global running

    mqtt_user, mqtt_passwd, mqtt_broker, mqtt_port = get_credentials()

    print(f"[{timestamp()}] ADSB Vehicle Counter Starting...")
    print(f"[{timestamp()}] Broker: {mqtt_broker}:{mqtt_port}")

    if mqtt_user:
        # Determine source of credentials
        if len(sys.argv) > 1 and sys.argv[1] == mqtt_user:
            source = "command line (positional)"
        elif '--user' in sys.argv or '-u' in sys.argv:
            source = "command line (flag)"
        else:
            source = "environment variable"
        print(f"[{timestamp()}] Authentication: enabled (user: {mqtt_user}, source: {source})")
    else:
        print(f"[{timestamp()}] Authentication: disabled (no credentials provided)")

    print(f"[{timestamp()}] Report interval: {PRINT_INTERVAL_SECONDS // 60} minutes")
    print(f"[{timestamp()}] Press Ctrl+C to stop\n")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        # Fallback for paho-mqtt < 2.0
        client = mqtt.Client()

    client.user_data_set({'broker_info': f"{mqtt_broker}:{mqtt_port}"})

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    if mqtt_user and mqtt_passwd:
        client.username_pw_set(mqtt_user, mqtt_passwd)
    elif mqtt_user:
        client.username_pw_set(mqtt_user)

    timer_thread = threading.Thread(target=timer_thread_func, daemon=True)
    timer_thread.start()

    try:
        print(f"[{timestamp()}] Connecting to {mqtt_broker}:{mqtt_port}...")
        client.connect(mqtt_broker, mqtt_port, keepalive=60)
        client.loop_forever()  # blocking loop - processes network traffic and callbacks
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Ctrl+C received, shutting down...")
    except ConnectionRefusedError:
        print(f"[{timestamp()}] ERROR: Could not connect to broker at {mqtt_broker}:{mqtt_port}")
        print(f"[{timestamp()}] Make sure the MQTT broker is running and accessible.")
    except Exception as e:
        print(f"[{timestamp()}] ERROR: {e}")
        
    finally:
        running = False
        client.disconnect()

        print(f"\n[{timestamp()}] Final report before exit:")
        print_report_and_reset()

        print(f"[{timestamp()}] Goodbye!")

if __name__ == "__main__":
    main()
