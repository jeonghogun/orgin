# Observability Guide (Prometheus + Grafana)

This document explains how to set up and use the local monitoring stack for the Origin Project API.

## 1. Overview

The project is instrumented with OpenTelemetry and exposes Prometheus metrics at the `/metrics` endpoint. We use a local Prometheus and Grafana stack, defined in `docker-compose.monitoring.yml`, to scrape these metrics and visualize them in a dashboard.

This provides real-time insight into the application's health, performance, and resource usage.

## 2. How to Run the Monitoring Stack

### Step 1: Run the Main Application
First, ensure the main application is running, as Prometheus needs to connect to it.
```bash
# From the project root, start the main application
docker-compose up -d
```

### Step 2: Run the Monitoring Stack
In a separate terminal, start the Prometheus and Grafana services.
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

### Step 3: Access the Tools
- **Prometheus:** Navigate to `http://localhost:9090` in your browser. You can use the expression browser to query metrics like `http_requests_total`.
- **Grafana:** Navigate to `http://localhost:3000` in your browser.
  - **Login:** Use the default credentials `admin` / `admin`. You will be prompted to change the password on first login.
  - **Dashboard:** The "Origin API Dashboard" should be automatically provisioned and available on the home page.

## 3. Key Dashboard Metrics Explained

The default dashboard provides a high-level overview of the API's health:

- **API RPS (Requests Per Second):** Shows the total number of requests the API is handling. A sudden drop to zero could indicate a crash.
- **API Error Rate (%):** The percentage of requests that are resulting in a 5xx server error. This is a critical indicator of application health. Any value greater than 0 should be investigated.
- **API Latency P95 (seconds):** The 95th percentile of request duration. This tells you that 95% of users are getting a response time at or below this value. It's a better indicator of "worst-case" performance than an average.
- **Memory Usage (Bytes):** Tracks the Resident Set Size (RSS) memory of the main API process. This can be useful for detecting memory leaks over time.

## 4. Extending and Customizing

The provided setup is a minimal baseline. It can be extended in several ways:
- **Adding More Panels:** You can edit the dashboard directly in the Grafana UI and save your changes. To make them permanent, you can export the JSON model and update the `config/grafana/provisioning/dashboards/origin_dashboard.json` file.
- **Adding More Metrics:** The application can be instrumented to expose custom metrics (e.g., Celery queue length, number of active reviews) using the OpenTelemetry Metrics API.
- **Adding Logging and Tracing:** For a full observability picture, you would typically forward application logs to a system like Loki and traces to a system like Tempo/Jaeger, and then link them all in Grafana. The `OTEL_EXPORTER_OTLP_ENDPOINT` setting is the hook for exporting trace data.
