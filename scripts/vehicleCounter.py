#!/usr/bin/env python3
#
# Script to print the number of messages from each unique vehicle that is in
#  the tracking volume per interval.
# Since messages are sent around once a second, these counts are a proxy for
#  number of plane-seconds per hour.
#
#
# Usage:
#    python adsb_counter.py [username] [password] [brokerIPA]
#    
# Or set environment variables:
#  export MQTT_USER=myuser
#  export MQTT_PASSWD=mypassword
#  export MQTT_BROKER=mybroker
#
# Usage:
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

DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "adsb/vehicles/#"
DEFAULT_INTERVAL_SECONDS = 600  # 10 minutes

hex_counts = defaultdict(int)
lock = threading.Lock()
running = True
report_interval = DEFAULT_INTERVAL_SECONDS
retained_skipped = 0


def get_config():
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
  MQTT_BROKER   MQTT broker IP address (used if not provided via command line)
  MQTT_PORT       MQTT broker port (used if not provided via command line)
  REPORT_INTERVAL Report interval in seconds (used if not provided via command line)

Examples:
  %(prog)s myuser mypassword
  %(prog)s --user myuser --password mypassword
  %(prog)s -u myuser -p mypass -i 300
  %(prog)s --interval 60
  MQTT_USER=myuser MQTT_PASSWD=mypassword %(prog)s
  REPORT_INTERVAL=300 %(prog)s
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
        'positional_broker',
        nargs='?',
        default=None,
        help='MQTT broker address (positional argument)'
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
        help=f'MQTT broker address (alternative to positional argument)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help=f'MQTT broker port (default: {DEFAULT_PORT})'
    )
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=None,
        metavar='SECONDS',
        help=f'Report interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})'
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

    # determine password: positional > flag > environment variable
    broker = (
        args.positional_broker or
        args.broker or
        os.environ.get('MQTT_BROKER') or
        DEFAULT_BROKER
    )

    # get port: flag > environment variable > default
    port_env = os.environ.get('MQTT_PORT')
    if args.port:
        port = args.port
    elif port_env:
        try:
            port = int(port_env)
        except ValueError:
            print(f"Warning: Invalid MQTT_PORT '{port_env}', using default {DEFAULT_PORT}")
            port = DEFAULT_PORT
    else:
        port = DEFAULT_PORT

    # get interval: flag > environment variable > default
    interval_env = os.environ.get('REPORT_INTERVAL')
    if args.interval:
        interval = args.interval
    elif interval_env:
        try:
            interval = int(interval_env)
        except ValueError:
            print(f"Warning: Invalid REPORT_INTERVAL '{interval_env}', using default {DEFAULT_INTERVAL_SECONDS}")
            interval = DEFAULT_INTERVAL_SECONDS
    else:
        interval = DEFAULT_INTERVAL_SECONDS

    # validate interval
    if interval < 1:
        print(f"Warning: Interval must be at least 1 second, using default {DEFAULT_INTERVAL_SECONDS}")
        interval = DEFAULT_INTERVAL_SECONDS

    return {
        'username': username,
        'password': password,
        'broker': broker,
        'port': port,
        'interval': interval
    }

def on_connect(client, userdata, flags, reason_code, properties=None):
    """Callback when connected to MQTT broker"""
    broker_info = userdata.get('broker_info', 'broker')
    topic = userdata.get('topic', DEFAULT_TOPIC)

    # handle both paho-mqtt v1.x (rc is int) and v2.x (reason_code object)
    rc = reason_code if isinstance(reason_code, int) else reason_code.value

    if rc == 0:
        print(f"[{timestamp()}] Connected to MQTT broker at {broker_info}")
        client.subscribe(topic) # options=SubscribeOptions(retain_as_subscribed=False))
        print(f"[{timestamp()}] Subscribed to topic: {topic}")
    else:
        print(f"[{timestamp()}] Failed to connect, return code: {reason_code}")

def on_disconnect(client, userdata, disconnect_flags_or_rc, reason_code=None, properties=None):
    """
    Handles both paho-mqtt v1.x and v2.x callback signatures:
    - v1.x: on_disconnect(client, userdata, rc)
    - v2.x: on_disconnect(client, userdata, disconnect_flags, reason_code, properties)
    """
    if reason_code is not None:
        # v2.x style
        code = reason_code
    else:
        # v1.x style
        code = disconnect_flags_or_rc
    print(f"[{timestamp()}] Disconnected from broker (code: {code})")

def on_message(client, userdata, msg):
    """Callback when a message is received"""
    global retained_skipped

    # skip retained messages - we only want live data
    if msg.retain:
        with lock:
            retained_skipped += 1
        return

    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        hex_value = payload.get('hex')

        if hex_value:
            with lock:
                hex_counts[hex_value] += 1

    except json.JSONDecodeError:
        pass  # silently ignore malformed JSON
    except Exception as e:
        print(f"[{timestamp()}] Error processing message: {e}")

def timestamp():
    """Return current timestamp string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def format_interval(seconds):
    """Format seconds into a human-readable string"""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        minutes = seconds / 60
        if minutes == int(minutes):
            minutes = int(minutes)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        if hours == int(hours):
            hours = int(hours)
            return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            return f"{hours:.1f} hours"

def print_report_and_reset():
    """Print the counts report and reset the counter."""
    global hex_counts, retained_skipped

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
            print(f"{'TOTAL UNIQUE AIRCRAFT:':<20} {len(hex_counts):>8}")
            print(f"{'TOTAL MESSAGES:':<20} {sum(hex_counts.values()):>10}")
        else:
            print("  No messages received during this period.")

        if retained_skipped > 0:
            print(f"{'RETAINED SKIPPED:':<20} {retained_skipped:>10}")

        print(f"{'='*60}")
        print(f"  Resetting counters. Next report in {format_interval(report_interval)}...")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # Clear the counts for the next period
        hex_counts.clear()
        retained_skipped = 0

def timer_thread_func():
    """Thread function that triggers reports every report_interval seconds"""
    global running

    while running:
        # Sleep in small increments to allow faster shutdown
        for _ in range(report_interval):
            if not running:
                return
            time.sleep(1)

        if running:
            print_report_and_reset()

def main():
    global running, report_interval

    # get configuration from command line or environment
    config = get_config()

    mqtt_user = config['username']
    mqtt_passwd = config['password']
    mqtt_broker = config['broker']
    mqtt_port = config['port']
    report_interval = config['interval']

    print(f"[{timestamp()}] ADSB Vehicle Counter Starting...")
    print(f"[{timestamp()}] Broker: {mqtt_broker}:{mqtt_port}")
    print(f"[{timestamp()}] Report interval: {format_interval(report_interval)} ({report_interval} seconds)")
    print(f"[{timestamp()}] Retained messages: ignored")

    # show credential source info (without revealing password)
    if mqtt_user:
        # determine source of credentials
        if len(sys.argv) > 1 and sys.argv[1] == mqtt_user:
            source = "command line (positional)"
        elif '--user' in sys.argv or '-u' in sys.argv:
            source = "command line (flag)"
        else:
            source = "environment variable"
        print(f"[{timestamp()}] Authentication: enabled (user: {mqtt_user}, source: {source})")
    else:
        print(f"[{timestamp()}] Authentication: disabled (no credentials provided)")
    print(f"[{timestamp()}] Press Ctrl+C to stop\n")

    # create MQTT client with version 2 callback API (paho-mqtt >= 2.0)
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        # Fallback for paho-mqtt < 2.0
        client = mqtt.Client()

    # store broker info in userdata for callbacks
    client.user_data_set({
        'broker_info': f"{mqtt_broker}:{mqtt_port}",
        'topic': DEFAULT_TOPIC
    })

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    if mqtt_user and mqtt_passwd:
        client.username_pw_set(mqtt_user, mqtt_passwd)
    elif mqtt_user:
        # Username only, no password
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
