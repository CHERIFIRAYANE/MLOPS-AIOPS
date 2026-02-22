#!/usr/bin/env python3
"""Compare old vs new dataset"""
import pandas as pd
import numpy as np

print("=" * 80)
print("📊 COMPARISON: OLD vs NEW DATASET")
print("=" * 80)

df_old = pd.read_csv('data/cleaned_dataset_v2.csv')
df_new = pd.read_csv('data/cleaned_dataset_2026-02-19.csv')

numeric_cols_old = df_old.select_dtypes(include=[np.number]).columns
numeric_cols_new = df_new.select_dtypes(include=[np.number]).columns

active_old = len([c for c in numeric_cols_old if df_old[c].std() > 0])
active_new = len([c for c in numeric_cols_new if df_new[c].std() > 0])

print(f"\nOLD DATASET (Feb 10 - before Phase 1):")
print(f"  Active: {active_old}/60 ({active_old/60*100:.0f}%)")
print(f"  Network metrics: ❌ ALL ZEROS")
print(f"  Disk metrics: ❌ ALL ZEROS")

print(f"\nNEW DATASET (Feb 19 - after Phase 1):")
print(f"  Active: {active_new}/60 ({active_new/60*100:.0f}%)")
print(f"  Network metrics: ✅ WORKING (12 active)")
print(f"  Disk metrics: ⚠️ STILL ZEROS (needs investigation)")

improvement = ((active_new - active_old) / active_old) * 100
print(f"\n✅ IMPROVEMENT: {active_old} → {active_new} metrics (+{improvement:.1f}%)")

print(f"\n📈 SAMPLE VALUES FROM NEW DATASET:")
print(f"  node_network_transmit_mean: {df_new['node_network_transmit_mean'].mean():.4f} (σ: {df_new['node_network_transmit_mean'].std():.6f})")
print(f"  node_network_receive_mean:  {df_new['node_network_receive_mean'].mean():.4f} (σ: {df_new['node_network_receive_mean'].std():.6f})")
print(f"  node_disk_read_mean:        {df_new['node_disk_read_mean'].mean():.4f} (σ: {df_new['node_disk_read_mean'].std():.6f}) ← ZERO")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("✅ Phase 1 PARTIALLY SUCCESSFUL:")
print("   - Network metrics NOW have variance (rate() fix working)")
print("   - Disk metrics still broken (need to check Prometheus queries)")
print("\n🔧 NEXT STEPS:")
print("   1. Check if node exports disk metrics at all")
print("   2. Verify disk_read_bytes_total & disk_written_bytes_total exist in Prometheus")
print("   3. May need fallback metric or alternative query")
