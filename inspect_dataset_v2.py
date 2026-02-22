#!/usr/bin/env python3
"""Inspect cleaned_dataset_v2.csv"""
import pandas as pd
import numpy as np

df = pd.read_csv('data/cleaned_dataset_v2.csv')
numeric_cols = df.select_dtypes(include=[np.number]).columns
active = [c for c in numeric_cols if df[c].std() > 0]
dead = [c for c in numeric_cols if df[c].std() == 0]

print("=" * 80)
print("📊 DATASET V2 INSPECTION")
print("=" * 80)
print(f"\n✅ File: data/cleaned_dataset_v2.csv")
print(f"   Records: {len(df)}")
print(f"   Columns: {len(df.columns)}")
print(f"   Active metrics: {len(active)}/{len(numeric_cols)} ({len(active)/len(numeric_cols)*100:.0f}%)")
print(f"   Dead metrics: {len(dead)}/{len(numeric_cols)}")

print(f"\n⏱️  TIMESTAMP RANGE:")
print(f"   Start: {df.iloc[0]['timestamp']}")
print(f"   End: {df.iloc[-1]['timestamp']}")

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

print(f"\n🔍 ACTIVE METRICS:")
for col in active[:15]:
    print(f"   ✅ {col}")
if len(active) > 15:
    print(f"   ... and {len(active)-15} more")

print(f"\n📋 DEAD METRICS (all zeros):")
for col in dead[:10]:
    print(f"   ❌ {col}")
if len(dead) > 10:
    print(f"   ... and {len(dead)-10} more")

print(f"\n📈 SAMPLE DATA (first 5 active metrics, row 0):")
for col in active[:5]:
    val = df[col].iloc[0]
    print(f"   {col}: {val:.4f}")

print("\n" + "=" * 80)
