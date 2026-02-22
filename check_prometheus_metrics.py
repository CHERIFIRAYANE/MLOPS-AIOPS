#!/usr/bin/env python3
"""Check what metrics are available in Prometheus"""
import requests
import json

prom_url = "http://localhost:9090"

print("=" * 80)
print("🔍 CHECKING PROMETHEUS FOR DISK METRICS")
print("=" * 80)

# Get all metric names
try:
    resp = requests.get(f"{prom_url}/api/v1/label/__name__/values", timeout=5)
    if resp.status_code == 200:
        all_metrics = resp.json()['data']
        disk_metrics = [m for m in all_metrics if 'disk' in m.lower()]
        
        print(f"\n📊 Disk-related metrics in Prometheus:")
        print(f"   Total metrics: {len(all_metrics)}")
        print(f"   Disk metrics: {len(disk_metrics)}\n")
        
        for metric in sorted(disk_metrics):
            print(f"   - {metric}")
        
        # Check specific ones
        print(f"\n🔧 Checking specific metrics we need:")
        needed = [
            'node_disk_read_bytes_total',
            'node_disk_written_bytes_total',
            'node_disk_io_time_ms_total'
        ]
        
        for metric in needed:
            exists = "✅" if metric in all_metrics else "❌"
            print(f"   {exists} {metric}")
    else:
        print(f"Error: {resp.status_code}")

except Exception as e:
    print(f"Cannot connect to Prometheus: {e}")
    print(f"Make sure Prometheus is running at {prom_url}")

print("\n" + "=" * 80)
