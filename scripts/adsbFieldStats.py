#!/usr/bin/env python3
#
# Subscribes to "adsb/vehicles/#" and collects:
#   - Unique values (with counts) for: hex, flight, category, ac_type, ac_desc, emergency
#   - Min/max values for: gs, baro_rate, rssi, alt_baro, alt_geom, r_dst
#
# Writes results to a JSON file periodically and on shutdown.
#
# Usage:
#   python adsbFieldStats.py [username] [password] [broker]
#
# Or set environment variables:
#   MQTT_USER, MQTT_PASSWD, MQTT_BROKER, MQTT_PORT, REPORT_INTERVAL, OUTPUT_FILE

import paho.mqtt.client as mqtt
import json
import threading
import time
import os
import sys
import argparse
from datetime import datetime

DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "adsb/vehicles/#"
DEFAULT_INTERVAL_SECONDS = 600  # 10 minutes
DEFAULT_OUTPUT_FILE = "adsbFieldStats.json"

UNIQUE_FIELDS = ("hex", "flight", "category", "ac_type", "ac_desc", "emergency")
RANGE_FIELDS = ("gs", "baro_rate", "rssi", "alt_baro", "alt_geom", "r_dst")

unique_values = {f: {} for f in UNIQUE_FIELDS}  # value -> count
range_stats = {f: {"min": None, "max": None} for f in RANGE_FIELDS}
lock = threading.Lock()
running = True
report_interval = DEFAULT_INTERVAL_SECONDS
output_file = DEFAULT_OUTPUT_FILE
retained_skipped = 0


def get_config():
    parser = argparse.ArgumentParser(
        description='ADSB Field Stats - Collects unique and range stats from MQTT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Environment Variables:
  MQTT_USER       MQTT username
  MQTT_PASSWD     MQTT password
  MQTT_BROKER     MQTT broker IP address
  MQTT_PORT       MQTT broker port
  REPORT_INTERVAL Report interval in seconds
  OUTPUT_FILE     Path to output JSON file

Examples:
  %(prog)s myuser mypassword 192.168.1.5
  %(prog)s -u myuser -p mypass -b 192.168.1.5 -i 300 -o stats.json
        '''
    )
    parser.add_argument('positional_user', nargs='?', default=None)
    parser.add_argument('positional_password', nargs='?', default=None)
    parser.add_argument('positional_broker', nargs='?', default=None)
    parser.add_argument('-u', '--user', default=None)
    parser.add_argument('-p', '--password', default=None)
    parser.add_argument('-b', '--broker', default=None)
    parser.add_argument('--port', type=int, default=None,
                        help=f'MQTT broker port (default: {DEFAULT_PORT})')
    parser.add_argument('-i', '--interval', type=int, default=None, metavar='SECONDS',
                        help=f'Write interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})')
    parser.add_argument('-o', '--output', default=None, metavar='FILE',
                        help=f'Output JSON file path (default: {DEFAULT_OUTPUT_FILE})')
    args = parser.parse_args()

    username = args.positional_user or args.user or os.environ.get('MQTT_USER')
    password = args.positional_password or args.password or os.environ.get('MQTT_PASSWD')
    broker = (args.positional_broker or args.broker or
              os.environ.get('MQTT_BROKER') or DEFAULT_BROKER)

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

    if interval < 1:
        print(f"Warning: Interval must be at least 1 second, using default {DEFAULT_INTERVAL_SECONDS}")
        interval = DEFAULT_INTERVAL_SECONDS

    out_file = args.output or os.environ.get('OUTPUT_FILE') or DEFAULT_OUTPUT_FILE

    return {
        'username': username,
        'password': password,
        'broker': broker,
        'port': port,
        'interval': interval,
        'output_file': out_file,
    }


def timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def on_connect(client, userdata, flags, reason_code, properties=None):
    rc = reason_code if isinstance(reason_code, int) else reason_code.value
    if rc == 0:
        print(f"[{timestamp()}] Connected to MQTT broker at {userdata.get('broker_info')}")
        client.subscribe(userdata.get('topic', DEFAULT_TOPIC))
        print(f"[{timestamp()}] Subscribed to topic: {userdata.get('topic', DEFAULT_TOPIC)}")
    else:
        print(f"[{timestamp()}] Failed to connect, return code: {reason_code}")


def on_disconnect(client, userdata, disconnect_flags_or_rc, reason_code=None, properties=None):
    code = reason_code if reason_code is not None else disconnect_flags_or_rc
    print(f"[{timestamp()}] Disconnected from broker (code: {code})")


def on_message(client, userdata, msg):
    global retained_skipped

    if msg.retain:
        with lock:
            retained_skipped += 1
        return

    try:
        payload = json.loads(msg.payload.decode('utf-8'))

        with lock:
            for field in UNIQUE_FIELDS:
                value = payload.get(field)
                if value is not None and value != "":
                    unique_values[field][value] = unique_values[field].get(value, 0) + 1

            for field in RANGE_FIELDS:
                value = payload.get(field)
                if value is not None:
                    try:
                        v = float(value)
                        stats = range_stats[field]
                        if stats["min"] is None or v < stats["min"]:
                            stats["min"] = v
                        if stats["max"] is None or v > stats["max"]:
                            stats["max"] = v
                    except (TypeError, ValueError):
                        pass

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[{timestamp()}] Error processing message: {e}")


def write_stats():
    with lock:
        data = {
            "generated": timestamp(),
            "unique_values": {
                f: {v: unique_values[f][v] for v in sorted(unique_values[f])}
                for f in UNIQUE_FIELDS
            },
            "range_stats": {f: dict(range_stats[f]) for f in RANGE_FIELDS},
        }

    try:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[{timestamp()}] Stats written to {output_file}")
    except Exception as e:
        print(f"[{timestamp()}] Error writing stats file: {e}")


def timer_thread_func():
    global running
    while running:
        for _ in range(report_interval):
            if not running:
                return
            time.sleep(1)
        if running:
            write_stats()


def main():
    global running, report_interval, output_file

    config = get_config()
    mqtt_user = config['username']
    mqtt_passwd = config['password']
    mqtt_broker = config['broker']
    mqtt_port = config['port']
    report_interval = config['interval']
    output_file = config['output_file']

    print(f"[{timestamp()}] ADSB Field Stats Starting...")
    print(f"[{timestamp()}] Broker: {mqtt_broker}:{mqtt_port}")
    print(f"[{timestamp()}] Write interval: {report_interval} seconds")
    print(f"[{timestamp()}] Output file: {output_file}")
    print(f"[{timestamp()}] Retained messages: ignored")
    if mqtt_user:
        print(f"[{timestamp()}] Authentication: enabled (user: {mqtt_user})")
    else:
        print(f"[{timestamp()}] Authentication: disabled")
    print(f"[{timestamp()}] Press Ctrl+C to stop\n")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    client.user_data_set({
        'broker_info': f"{mqtt_broker}:{mqtt_port}",
        'topic': DEFAULT_TOPIC,
    })

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
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Ctrl+C received, shutting down...")
    except ConnectionRefusedError:
        print(f"[{timestamp()}] ERROR: Could not connect to broker at {mqtt_broker}:{mqtt_port}")
    except Exception as e:
        print(f"[{timestamp()}] ERROR: {e}")
    finally:
        running = False
        client.disconnect()

        print(f"\n[{timestamp()}] Writing final stats before exit...")
        write_stats()
        print(f"[{timestamp()}] Goodbye!")


if __name__ == "__main__":
    main()
