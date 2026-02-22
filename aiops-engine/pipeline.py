#!/usr/bin/env python3
"""
AIOps Data Pipeline:
1. Query Prometheus API every 5 seconds
2. Collect metrics from 3 layers (App, Container, Node)
3. Apply sliding window (12 points = 1 minute)
4. Clean & normalize data
5. Save cleaned dataset for ML training
"""

import requests
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime
import json
import time
import logging
import os
import pickle
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

# ── Model monitor (exposes Prometheus metrics) ───────────────────────────────
try:
    from model_monitor import monitor as _monitor
except ImportError:
    _monitor = None

# ── Model paths ───────────────────────────────────────────────────────────────
MODELS_DIR   = Path(os.getenv('MODELS_DIR', '/app/models'))
MODEL_PKL    = MODELS_DIR / 'anomaly_detector.pkl'
SCALER_PKL   = MODELS_DIR / 'scaler.pkl'
FEATURE_JSON = MODELS_DIR / 'feature_list.json'

METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PrometheusQueryEngine:
    """Query Prometheus API for metrics from all 3 layers"""
    
    def __init__(self, prometheus_url='http://prometheus:9090'):
        self.prom_url = prometheus_url
        self.data_buffer = deque(maxlen=1000)
        self.connection_retries = 0
        self.max_retries = 30
        self.available_metrics = set()  # Track which metrics are available
        
        # Wait for Prometheus to be ready
        self._wait_for_prometheus()
        self._probe_available_metrics()
    
    def _wait_for_prometheus(self):
        """Wait for Prometheus to be accessible"""
        while self.connection_retries < self.max_retries:
            try:
                response = requests.get(f'{self.prom_url}/api/v1/query', params={'query': 'up'}, timeout=2)
                if response.status_code == 200:
                    logger.info("Connected to Prometheus")
                    return
            except Exception as e:
                self.connection_retries += 1
                logger.warning(f"Waiting for Prometheus... ({self.connection_retries}/{self.max_retries})")
                time.sleep(2)
        
        logger.error("❌ Could not connect to Prometheus after retries")
        raise Exception("Prometheus not available")
    
    def _probe_available_metrics(self):
        """Check which metric types are actually available in Prometheus"""
        logger.info("🔍 Probing available metrics...")
        try:
            response = requests.get(
                f'{self.prom_url}/api/v1/label/__name__/values',
                timeout=5
            )
            if response.status_code == 200:
                self.available_metrics = set(response.json()['data'])
                
                # Categorize and report
                http_metrics = [m for m in self.available_metrics if 'http_' in m]
                node_metrics = [m for m in self.available_metrics if 'node_' in m]
                container_metrics = [m for m in self.available_metrics if 'container_' in m]
                
                logger.info(f"   📊 HTTP metrics: {len(http_metrics)} available")
                logger.info(f"   🖥️  Node metrics: {len(node_metrics)} available")
                logger.info(f"   📦 Container metrics: {len(container_metrics)} available")
                
                if len(http_metrics) == 0:
                    logger.error("   ❌ NO HTTP METRICS! Is echo-server running?")
                if len(node_metrics) == 0:
                    logger.error("   ❌ NO NODE METRICS! Is node-exporter deployed?")
                if len(container_metrics) == 0:
                    logger.warning("   No container metrics (cAdvisor may not be available)")
        except Exception as e:
            logger.warning(f"Could not probe metrics: {e}")

    
    def query_metrics(self, timestamp):
        """Query metrics from 3 distinct layers"""
        metrics = {'timestamp': timestamp}
        
        # Layer 1: Application Level Metrics (HTTP/App performance) ✓ WORKING CORRECTLY
        app_queries = {
            'http_request_rate': 'rate(http_requests_total[1m])',
            'http_p95_latency': 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))',
            'http_p99_latency': 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[1m]))',
            'http_p50_latency': 'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[1m]))',
        }
        
        for metric_name, query in app_queries.items():
            metrics[metric_name] = self._execute_query(query, metric_name)
        
        # Layer 2: System CPU & Memory Metrics (from node-exporter) ✓ FIXED: Use rate() for CPU
        # CPU is a counter of seconds, so rate() = CPU utilization
        # Memory is a gauge, so query directly
        system_queries = {
            'system_cpu_usage_percent': 'rate(node_cpu_seconds_total[5m]) * 100',  # FIXED: rate() for counter
            'system_cpu_user': 'rate(node_cpu_seconds_total{mode="user"}[5m])',     # User mode CPU
            'system_cpu_system': 'rate(node_cpu_seconds_total{mode="system"}[5m])', # System mode CPU
            'system_memory_available_bytes': 'node_memory_MemAvailable_bytes / 1024',  # Convert to KB
            'system_memory_used_bytes': '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / 1024',
            'system_load_avg_1m': 'node_load1',
            'system_load_avg_5m': 'node_load5',
        }
        
        for metric_name, query in system_queries.items():
            metrics[metric_name] = self._execute_query(query, metric_name)
        
        # Layer 3: Node Level Metrics (Hardware/OS - Network, Disk, Load) ✓ FIXED: Use rate()
        # These are counters (monotonically increasing), so rate() = throughput
        node_queries = {
            'node_network_transmit_bytes_per_sec': 'rate(node_network_transmit_bytes_total[5m])',  # FIXED: rate()
            'node_network_receive_bytes_per_sec': 'rate(node_network_receive_bytes_total[5m])',    # FIXED: rate()
            'node_network_transmit_packets_per_sec': 'rate(node_network_transmit_packets_total[5m])',
            'node_network_receive_packets_per_sec': 'rate(node_network_receive_packets_total[5m])',
            'node_disk_read_bytes_per_sec': 'rate(node_disk_read_bytes_total[5m])',    # FIXED: rate()
            'node_disk_write_bytes_per_sec': 'rate(node_disk_written_bytes_total[5m])',  # FIXED: rate()
            'node_disk_io_time_ms': 'rate(node_disk_io_time_ms_total[5m])',
        }
        
        for metric_name, query in node_queries.items():
            metrics[metric_name] = self._execute_query(query, metric_name)
        
        # Layer 4: Container Metrics (from cAdvisor via kubelet) ✓ NEW: Container metrics
        # These metrics aggregate across all pods in the cluster
        container_queries = {
            'container_cpu_usage_percent': 'sum(rate(container_cpu_usage_seconds_total{pod_name!="",pod_name!="POD"}[5m])) * 100',
            'container_memory_working_set_bytes': 'sum(container_memory_working_set_bytes{pod_name!="",pod_name!="POD"})',
            'container_network_receive_bytes_per_sec': 'sum(rate(container_network_receive_bytes_total{pod_name!="",pod_name!="POD"}[5m]))',
            'container_network_transmit_bytes_per_sec': 'sum(rate(container_network_transmit_bytes_total{pod_name!="",pod_name!="POD"}[5m]))',
            'container_fs_usage_bytes': 'sum(container_fs_usage_bytes{pod_name!="",pod_name!="POD"})',
        }
        
        for metric_name, query in container_queries.items():
            metrics[metric_name] = self._execute_query(query, metric_name)
        
        self.data_buffer.append(metrics)
        return metrics
    
    def _execute_query(self, query, metric_name):
        """Execute single PromQL query with error handling and validation"""
        try:
            response = requests.get(
                f'{self.prom_url}/api/v1/query',
                params={'query': query},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()['data']['result']
                
                if data:
                    # Successfully retrieved metric
                    value = float(data[0]['value'][1])
                    
                    # Validate value is not NaN/Inf but allow zero (legit for rates)
                    if np.isnan(value) or np.isinf(value):
                        logger.warning(f"Invalid value for {metric_name}: {value}, using 0.0")
                        return 0.0
                    
                    return value
                else:
                    # Query returned no results (metric may not exist yet)
                    logger.debug(f"No data for {metric_name} (query: {query}) - metric may not exist yet")
                    return 0.0
            else:
                logger.warning(f"Query failed for {metric_name}: Status {response.status_code}")
                logger.debug(f"   Query: {query}")
                logger.debug(f"   Response: {response.text[:200]}")
                return 0.0
        
        except requests.exceptions.Timeout:
            logger.warning(f"Query timeout for {metric_name}: {query}")
            return 0.0
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error querying Prometheus for {metric_name}")
            return 0.0
        except (KeyError, ValueError, IndexError) as e:
            logger.warning(f"Parse error for {metric_name}: {str(e)}")
            return 0.0
        except Exception as e:
            logger.warning(f"Unexpected error querying {metric_name}: {str(e)}")
            return 0.0

class SlidingWindowProcessor:
    """Create windowed features (12 points = 1 minute sliding window)"""
    
    def __init__(self, window_size=12):
        self.window_size = window_size
        self.window = deque(maxlen=window_size)
    
    def process(self, metric_dict):
        """Add to window and return features if window is full"""
        self.window.append(metric_dict)
        
        if len(self.window) < self.window_size:
            return None
        
        return self._extract_features()
    
    def _extract_features(self):
        """Extract statistical features from window"""
        df = pd.DataFrame(list(self.window))
        features = {'timestamp': df['timestamp'].iloc[-1]}
        
        # Skip timestamp column
        numeric_cols = [col for col in df.columns if col != 'timestamp' and df[col].dtype in ['float64', 'int64']]
        
        for col in numeric_cols:
            values = pd.to_numeric(df[col], errors='coerce').dropna()
            
            if len(values) > 0:
                features[f'{col}_mean'] = values.mean()
                features[f'{col}_std'] = values.std()
                features[f'{col}_min'] = values.min()
                features[f'{col}_max'] = values.max()
                features[f'{col}_p95'] = values.quantile(0.95)
                features[f'{col}_trend'] = values.iloc[-1] - values.iloc[0]
        
        return features

class DataCleaner:
    """Clean and normalize data for ML training"""
    
    @staticmethod
    def clean(features_dict):
        """Handle NaN, infinite values, and normalization"""
        cleaned = {}
        
        for key, value in features_dict.items():
            if key == 'timestamp':
                cleaned[key] = value
            else:
                try:
                    val = float(value)
                    # Replace inf and extremely large values
                    if np.isinf(val) or np.isnan(val):
                        cleaned[key] = 0.0
                    elif abs(val) > 1e10:  # Clip extreme outliers
                        cleaned[key] = 1e10 if val > 0 else -1e10
                    else:
                        cleaned[key] = val
                except (ValueError, TypeError):
                    cleaned[key] = 0.0
        
        return cleaned

class AnomalyDetector:
    """Real-time anomaly detection using ensemble methods"""
    
    def __init__(self, min_samples=20, contamination=0.05):
        self.min_samples = min_samples
        self.contamination = contamination
        self.features_history = []
        self.scaler = StandardScaler()
        self.iso_forest = None
        self.lof = None
        self.is_trained = False
    
    def add_sample(self, features_dict):
        """Add sample to history for training"""
        # Remove timestamp for training
        feature_values = {k: v for k, v in features_dict.items() if k != 'timestamp'}
        self.features_history.append(feature_values)
    
    def train(self):
        """Train anomaly detection models once we have enough samples"""
        if len(self.features_history) < self.min_samples:
            return False
        
        try:
            # Convert to DataFrame for easier handling
            df = pd.DataFrame(self.features_history)
            X = df.values
            
            # Normalize features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train Isolation Forest
            self.iso_forest = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=100
            )
            self.iso_forest.fit(X_scaled)
            
            # Train Local Outlier Factor
            self.lof = LocalOutlierFactor(
                n_neighbors=min(20, len(self.features_history)//2),
                contamination=self.contamination,
                novelty=False
            )
            self.lof.fit(X_scaled)
            
            self.is_trained = True
            logger.info(f"Anomaly detection models trained on {len(self.features_history)} samples")
            return True
        except Exception as e:
            logger.warning(f"Failed to train anomaly detectors: {str(e)}")
            return False
    
    def detect(self, features_dict):
        """Detect anomalies in new sample. Returns anomaly score 0-1 (1 = anomalous)"""
        if not self.is_trained or self.iso_forest is None or self.lof is None:
            return {'is_anomaly': False, 'score': 0.0, 'confidence': 0.0, 'reason': 'Models not trained yet'}
        
        try:
            # Prepare feature vector
            feature_values = np.array([features_dict.get(k, 0.0) for k in sorted(features_dict.keys()) if k != 'timestamp']).reshape(1, -1)
            X_scaled = self.scaler.transform(feature_values)
            
            # Get anomaly scores from both models
            iso_score = self.iso_forest.score_samples(X_scaled)[0]
            iso_prediction = self.iso_forest.predict(X_scaled)[0]
            
            # Normalize isolation forest score to 0-1 range
            iso_anomaly_prob = 1.0 / (1.0 + np.exp(iso_score))
            
            lof_score = self.lof.negative_outlier_factor_[0] if hasattr(self.lof, 'negative_outlier_factor_') else -1
            lof_prediction = self.lof.predict(X_scaled)[0]
            
            # Normalize LOF score to 0-1 range
            lof_anomaly_prob = 1.0 / (1.0 + np.exp(lof_score)) if lof_score != -1 else 0.5
            
            # Ensemble vote: confidence = % of models that agree
            votes = (1 if iso_prediction == -1 else 0) + (1 if lof_prediction == -1 else 0)
            confidence = votes / 2.0  # 0.0 (both say normal) to 1.0 (both say anomaly)
            
            # Overall anomaly score (average of both models' probabilities)
            anomaly_score = (iso_anomaly_prob + lof_anomaly_prob) / 2.0
            
            # Flag as anomaly if both models agree or score is very high
            is_anomaly = votes >= 1.5 or anomaly_score > 0.7
            
            return {
                'is_anomaly': is_anomaly,
                'score': float(anomaly_score),
                'confidence': float(confidence),
                'iso_vote': int(iso_prediction == -1),
                'lof_vote': int(lof_prediction == -1),
            }
        except Exception as e:
            logger.warning(f"Anomaly detection error: {str(e)}")
            return {'is_anomaly': False, 'score': 0.0, 'confidence': 0.0, 'error': str(e)}


# ── Prometheus /metrics HTTP handler ─────────────────────────────────────────
class MetricsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves Prometheus-format /metrics."""
    def do_GET(self):
        if self.path == '/metrics':
            body = _monitor.prometheus_metrics().encode() if _monitor else b'# monitor unavailable\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args):  # silence access log
        pass


class AIOpsDataPipeline:
    """End-to-end pipeline: Ingest → Window → Clean → Infer → Save"""
    
    def __init__(self, prometheus_url='http://prometheus:9090', output_file='/data/cleaned_dataset.csv'):
        self.query_engine = PrometheusQueryEngine(prometheus_url)
        self.window_processor = SlidingWindowProcessor(window_size=12)
        self.cleaner = DataCleaner()
        self.output_file = output_file
        self.all_features = []

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Load existing CSV so data survives pod restarts
        if os.path.exists(output_file):
            try:
                existing = pd.read_csv(output_file)
                self.all_features = existing.to_dict('records')
                logger.info(f"📂 Resumed from existing dataset: {len(self.all_features)} rows")
            except Exception as e:
                logger.warning(f"Could not load existing dataset: {e}")

        # Load pre-trained model if available
        self.model_bundle  = None
        self.scaler        = None
        self.feature_cols  = None
        self._load_model()

        # Start /metrics HTTP server in background thread
        self._start_metrics_server()

    def _load_model(self):
        """Load trained model bundle from /app/models/ (if present)."""
        if MODEL_PKL.exists() and SCALER_PKL.exists() and FEATURE_JSON.exists():
            try:
                with open(MODEL_PKL, 'rb') as f:
                    self.model_bundle = pickle.load(f)
                with open(SCALER_PKL, 'rb') as f:
                    self.scaler = pickle.load(f)
                with open(FEATURE_JSON) as f:
                    self.feature_cols = json.load(f)
                logger.info(f"Model loaded: {self.model_bundle.get('version','?')} "
                            f"({self.model_bundle.get('n_training_samples','?')} training samples, "
                            f"{len(self.feature_cols)} features)")
                if _monitor:
                    _monitor.model_version = self.model_bundle.get('version', '1.0')
                    _monitor.training_mean = self.scaler.mean_
                    _monitor.training_std  = self.scaler.scale_
            except Exception as e:
                logger.warning(f"Could not load model: {e}. Running in data-collection mode.")
        else:
            logger.warning("No model found — running in data-collection mode (no scoring).")

    def _start_metrics_server(self):
        """Start Prometheus /metrics HTTP server on METRICS_PORT."""
        try:
            server = HTTPServer(('0.0.0.0', METRICS_PORT), MetricsHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            logger.info(f"📡 Prometheus metrics → http://0.0.0.0:{METRICS_PORT}/metrics")
        except Exception as e:
            logger.warning(f"Could not start metrics server: {e}")

    # ── Human-readable feature name helper ───────────────────────────────────
    _FEATURE_LABELS = [
        ('http_request_rate',  'Request Rate'),
        ('http_p50_latency',   'Median Latency (p50)'),
        ('http_p95_latency',   '95th Pct Latency'),
        ('http_p99_latency',   '99th Pct Latency'),
        ('http_error_rate',    'HTTP Error Rate'),
        ('http_5xx',           '5xx Error Rate'),
        ('system_cpu',         'CPU Usage'),
        ('node_cpu',           'Node CPU'),
        ('node_load',          'System Load'),
        ('system_memory',      'Memory Usage'),
        ('node_memory',        'Node Memory'),
        ('http_active',        'Active Connections'),
    ]

    @staticmethod
    def _human_label(feature_name: str) -> str:
        for key, label in AIOpsDataPipeline._FEATURE_LABELS:
            if key in feature_name:
                stat = feature_name.rsplit('_', 1)[-1]  # mean/std/min/max/trend
                return f"{label} ({stat})"
        return feature_name.replace('_', ' ').title()

    def _classify_anomaly(self, features_dict: dict) -> tuple:
        """Return (anomaly_type, top_features) using RF importances x |z-score|."""
        if self.model_bundle is None or 'classifier' not in self.model_bundle:
            return 'unknown', []
        try:
            clf = self.model_bundle['classifier']
            vec = np.array([features_dict.get(c, 0.0) for c in self.feature_cols])
            vec_scaled = self.scaler.transform(vec.reshape(1, -1))[0]
            contribs = clf.feature_importances_ * np.abs(vec_scaled)
            top_idx  = np.argsort(contribs)[::-1][:3]
            top_feats = [
                (self.feature_cols[i],
                 self._human_label(self.feature_cols[i]),
                 float(contribs[i]))
                for i in top_idx
            ]
            top_name = top_feats[0][0] if top_feats else ''
            if any(k in top_name for k in ('request_rate', 'active_conn')):
                atype = 'ddos'
            elif any(k in top_name for k in ('p50_latency', 'p95_latency', 'p99_latency', 'latency')):
                atype = 'slow_response'
            elif any(k in top_name for k in ('error_rate', '5xx', 'error')):
                atype = 'error_rate'
            elif any(k in top_name for k in ('cpu', 'load')):
                atype = 'cpu_stress'
            else:
                atype = 'unknown'
            return atype, top_feats
        except Exception as e:
            logger.warning(f"classify_anomaly error: {e}")
            return 'unknown', []

    def score_window(self, features_dict: dict) -> dict:
        """Run anomaly detection on one windowed+cleaned feature dict.
        Returns a dict with is_anomaly, score, and iso_score keys.
        """
        result = {'is_anomaly': 0, 'anomaly_score': 0.0, 'iso_score': 0.0}
        if self.model_bundle is None or self.scaler is None or self.feature_cols is None:
            return result
        try:
            vec = np.array([features_dict.get(c, 0.0) for c in self.feature_cols]).reshape(1, -1)
            vec_scaled = self.scaler.transform(vec)

            if 'classifier' in self.model_bundle:
                # ── Supervised RandomForest (v2.0) ──────────────────────────
                clf = self.model_bundle['classifier']
                is_anomaly    = int(clf.predict(vec_scaled)[0])
                anomaly_score = float(clf.predict_proba(vec_scaled)[0][1])  # P(anomaly)
            else:
                # ── Legacy unsupervised IsolationForest + LOF (v1.0) ────────
                iso = self.model_bundle['iso_forest']
                lof = self.model_bundle['lof']
                iso_pred      = iso.predict(vec_scaled)[0]
                anomaly_score = float(-iso.score_samples(vec_scaled)[0])
                lof_pred      = lof.predict(vec_scaled)[0]
                is_anomaly    = int(iso_pred == -1 and lof_pred == -1)

            result = {
                'is_anomaly': is_anomaly,
                'anomaly_score': anomaly_score,
                'iso_score': anomaly_score,
            }

            # Classify type + root causes when anomaly detected
            anomaly_type, top_features = 'none', []
            if is_anomaly:
                anomaly_type, top_features = self._classify_anomaly(features_dict)
                logger.info(
                    f"   🔍 Type: {anomaly_type.upper()}  "
                    f"Top causes: {', '.join(f[1] for f in top_features[:3])}"
                )

            if _monitor:
                _monitor.record(
                    is_anomaly=is_anomaly,
                    score=anomaly_score,
                    features=[features_dict.get(c, 0.0) for c in self.feature_cols],
                    anomaly_type=anomaly_type,
                    top_features=top_features,
                )

        except Exception as e:
            logger.warning(f"Scoring error: {e}")
        return result
    
    def run(self, duration_seconds=600, query_interval=5):
        """Run pipeline for X seconds, querying Prometheus every ~5 seconds"""
        logger.info(f"🚀 AIOps Pipeline started for {duration_seconds}s (window: 12×5s = 60s)")
        start_time = time.time()
        query_count = 0
        window_count = 0
        
        while time.time() - start_time < duration_seconds:
            try:
                # Step 1: Query Prometheus
                current_time = datetime.now()
                metrics = self.query_engine.query_metrics(current_time)
                query_count += 1
                
                # Step 2: Sliding Window (12 data points)
                windowed_features = self.window_processor.process(metrics)
                
                if windowed_features:
                    # Step 3: Clean Data
                    cleaned_features = self.cleaner.clean(windowed_features)

                    # Step 3b: Score with pre-trained model (if available)
                    score_result = self.score_window(cleaned_features)
                    cleaned_features.update(score_result)

                    self.all_features.append(cleaned_features)
                    window_count += 1

                    anomaly_flag = 'ANOMALY' if score_result['is_anomaly'] else ''
                    if window_count % 10 == 0 or score_result['is_anomaly']:
                        logger.info(
                            f"📊 window={window_count:4d}  "
                            f"score={score_result['anomaly_score']:.4f}  {anomaly_flag}"
                        )

                    # Save incrementally every 5 windows (~5 min) so the CSV
                    # is always up to date for retraining without waiting for run end
                    if window_count % 5 == 0:
                        self._save_dataset()
                
                logger.debug(f"✓ Ingested metrics (query #{query_count})")
                
            except KeyboardInterrupt:
                logger.info("Pipeline interrupted by user")
                break
            except Exception as e:
                logger.error(f"Pipeline error: {str(e)}")
            
            time.sleep(query_interval)
        
        # Step 4: Save Dataset
        self._save_dataset()
        logger.info(f"✨ Pipeline complete!")
        logger.info(f"   Total queries: {query_count}")
        logger.info(f"   Windowed records: {len(self.all_features)}")
    
    def _save_dataset(self):
        """Save cleaned dataset to CSV for ML training"""
        if not self.all_features:
            logger.warning("No data to save")
            return
        
        df = pd.DataFrame(self.all_features)
        df.to_csv(self.output_file, index=False)
        
        # Analyze data quality
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        zero_variance_cols = numeric_cols[df[numeric_cols].std() == 0]
        active_cols = numeric_cols[df[numeric_cols].std() > 0]
        
        logger.info(f"\n📈 Dataset saved to: {self.output_file}")
        logger.info(f"   Records: {len(df)}")
        logger.info(f"   Total features: {len(df.columns)}")
        logger.info(f"   Active features (variance > 0): {len(active_cols)}")
        logger.info(f"   Dead metrics (all zeros): {len(zero_variance_cols)}")
        
        if len(zero_variance_cols) > 0:
            logger.warning(f"\n   Dead metrics detected:")
            for col in zero_variance_cols:
                logger.warning(f"      ❌ {col}: all values = {df[col].iloc[0]}")
        
        logger.info(f"   Memory size: {df.memory_usage(deep=True).sum() / 1024:.2f} KB")
        
        logger.info(f"\n📊 Feature breakdown:")
        logger.info(f"   HTTP metrics (working): {len([c for c in df.columns if 'http_' in c])}")
        logger.info(f"   System metrics (working): {len([c for c in df.columns if 'system_' in c])}")
        logger.info(f"   Node metrics (working): {len([c for c in df.columns if 'node_' in c])}")
        logger.info(f"   Container metrics (partial): {len([c for c in df.columns if 'container_' in c])}")
        
        logger.info(f"\n🔍 Data preview:")
        logger.info(f"\n{df[active_cols].head(3).to_string()}")
        
        logger.info(f"\nIf dead metrics detected, check:")
        logger.info(f"   1. Prometheus is scraping correct targets")
        logger.info(f"   2. Rate window (5m) has enough data points")
        logger.info(f"   3. Metric exists: curl http://prometheus:9090/api/v1/label/__name__/values")

if __name__ == '__main__':
    # Run indefinitely (restart handled by Kubernetes if needed)
    pipeline = AIOpsDataPipeline()
    pipeline.run(duration_seconds=86400)  # 24h — Kubernetes restarts if it exits
