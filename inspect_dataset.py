#!/usr/bin/env python3
"""Quick dataset inspection script"""
import pandas as pd
import numpy as np
from pathlib import Path

csv_path = 'data/cleaned_dataset.csv'

if not Path(csv_path).exists():
    print(f"❌ Dataset not found: {csv_path}")
    exit(1)

df = pd.read_csv(csv_path)
numeric_cols = df.select_dtypes(include=[np.number]).columns

print("="*80)
print("📊 DATASET INSPECTION")
print("="*80)
print(f"\n✅ File: {csv_path}")
print(f"   Size: {Path(csv_path).stat().st_size / 1024:.1f} KB")
print(f"   Records: {len(df)}")
print(f"   Columns: {len(df.columns)}")

print(f"\n⏱️  TIMESTAMP RANGE:")
print(f"   Start: {df.iloc[0]['timestamp']}")
print(f"   End: {df.iloc[-1]['timestamp']}")

print(f"\n📈 METRIC STATUS:")
active_cols = [c for c in numeric_cols if df[c].std() > 0.0]
dead_cols = [c for c in numeric_cols if df[c].std() == 0.0]

print(f"   ✅ Active metrics: {len(active_cols)}/{len(numeric_cols)} ({len(active_cols)/len(numeric_cols)*100:.0f}%)")
print(f"   ❌ Dead metrics: {len(dead_cols)}/{len(numeric_cols)}")

# Categorize by layer
http_cols = [c for c in df.columns if 'http_' in c]
system_cols = [c for c in df.columns if 'system_' in c]
node_cols = [c for c in df.columns if 'node_' in c]
container_cols = [c for c in df.columns if 'container_' in c]

print(f"\n📊 BY LAYER:")
print(f"   HTTP: {len(http_cols)} columns")
print(f"   System: {len(system_cols)} columns")
print(f"   Node: {len(node_cols)} columns")
print(f"   Container: {len(container_cols)} columns")

print(f"\n🔍 SAMPLE DATA (first 3 rows, active metrics only):")
print(df[active_cols].head(3).to_string())

print(f"\n📋 DEAD METRICS (all zeros):")
if len(dead_cols) > 0:
    for col in dead_cols[:10]:
        print(f"   ❌ {col}")
    if len(dead_cols) > 10:
        print(f"   ... and {len(dead_cols)-10} more")
else:
    print(f"   None! All metrics have variance ✅")

print("\n" + "="*80)
