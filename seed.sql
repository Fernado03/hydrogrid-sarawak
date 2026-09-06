-- Schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS marts;

-- 1. Dimension: Grid Assets
CREATE TABLE IF NOT EXISTS warehouse.dim_asset (
    id SERIAL PRIMARY KEY,
    asset_name VARCHAR(100) NOT NULL UNIQUE,
    asset_type VARCHAR(50) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    capacity_mw DOUBLE PRECISION NOT NULL
);

-- 2. Fact: Telemetry & Hydrology Time-Series
CREATE TABLE IF NOT EXISTS warehouse.fact_telemetry (
    id BIGSERIAL PRIMARY KEY,
    asset_id INT NOT NULL REFERENCES warehouse.dim_asset(id),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    temperature_2m DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    global_tilted_irradiance DOUBLE PRECISION,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Analytical View: SCADA Rollups
CREATE OR REPLACE VIEW warehouse.v_telemetry_analytics AS
SELECT 
    ft.id,
    da.asset_name,
    da.asset_type,
    ft.timestamp,
    ft.temperature_2m,
    ft.relative_humidity_2m,
    ft.precipitation,
    ft.global_tilted_irradiance,
    AVG(ft.precipitation) OVER (
        PARTITION BY ft.asset_id 
        ORDER BY ft.timestamp 
        ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
    ) AS rolling_24h_precip
FROM warehouse.fact_telemetry ft
JOIN warehouse.dim_asset da ON ft.asset_id = da.id;

-- 4. Analytical Mart: Daily Summary
CREATE TABLE IF NOT EXISTS marts.daily_telemetry_summary (
    asset_id INT NOT NULL REFERENCES warehouse.dim_asset(id),
    summary_date DATE NOT NULL,
    avg_temp DOUBLE PRECISION,
    total_precip DOUBLE PRECISION,
    max_irradiance DOUBLE PRECISION,
    PRIMARY KEY (asset_id, summary_date)
);

-- 5. Seed Assets
INSERT INTO warehouse.dim_asset (asset_name, asset_type, latitude, longitude, capacity_mw)
VALUES 
    ('Bakun Dam', 'Hydro', 2.7500, 114.0500, 2400.0),
    ('Murum Dam', 'Hydro', 2.6500, 114.3000, 944.0),
    ('Batang Ai', 'Solar/Hydro', 1.1500, 111.9000, 158.0),
    ('Bintulu H2 Hub', 'Industrial', 3.2000, 113.0500, 100.0)
ON CONFLICT (asset_name) DO NOTHING;

-- 6. Seed Synthetic Telemetry Series (Last 48 Hours)
INSERT INTO warehouse.fact_telemetry (asset_id, timestamp, temperature_2m, relative_humidity_2m, precipitation, global_tilted_irradiance)
SELECT 
    a.id,
    s.ts,
    26.0 + (random() * 6.0),
    75.0 + (random() * 20.0),
    CASE WHEN random() > 0.6 THEN random() * 15.0 ELSE 0.0 END,
    CASE 
        WHEN EXTRACT(HOUR FROM s.ts) BETWEEN 7 AND 18 
        THEN (random() * 800.0) 
        ELSE 0.0 
    END
FROM warehouse.dim_asset a
CROSS JOIN generate_series(
    CURRENT_TIMESTAMP - INTERVAL '48 hours',
    CURRENT_TIMESTAMP,
    INTERVAL '1 hour'
) AS s(ts);

-- 7. Populate Mart Aggregations
INSERT INTO marts.daily_telemetry_summary (asset_id, summary_date, avg_temp, total_precip, max_irradiance)
SELECT 
    asset_id,
    DATE(timestamp),
    ROUND(AVG(temperature_2m)::numeric, 2),
    ROUND(SUM(precipitation)::numeric, 2),
    ROUND(MAX(global_tilted_irradiance)::numeric, 2)
FROM warehouse.fact_telemetry
GROUP BY asset_id, DATE(timestamp)
ON CONFLICT (asset_id, summary_date) DO NOTHING;
