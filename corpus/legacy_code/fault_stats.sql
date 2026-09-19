-- Requêtes qualité utilisées par le rapport mensuel.
-- Chaque requête est précédée d'un commentaire qui lui donne un nom.
-- Le script de reporting les extrait par ce nom.

-- name: fault_counts_by_line
-- Nombre de défauts par ligne et par type, du plus fréquent au moins fréquent.
SELECT
    l.line_id,
    l.name_fr AS ligne,
    p.fault_code,
    f.label_fr AS libelle_defaut,
    f.severity,
    count(*) AS nb_toles
FROM plant.plate_inspections p
JOIN plant.production_lines l ON l.line_id = p.line_id
JOIN plant.fault_types f ON f.fault_code = p.fault_code
GROUP BY l.line_id, l.name_fr, p.fault_code, f.label_fr, f.severity
ORDER BY nb_toles DESC;

-- name: monthly_fault_trend
-- Tendance mensuelle des défauts critiques (gravité 3) sur l'année.
SELECT
    date_trunc('month', p.inspected_at) AS mois,
    count(*) FILTER (WHERE f.severity = 3) AS defauts_critiques,
    count(*) AS defauts_total,
    round(
        100.0 * count(*) FILTER (WHERE f.severity = 3) / nullif(count(*), 0),
        2
    ) AS part_critiques_pct
FROM plant.plate_inspections p
JOIN plant.fault_types f ON f.fault_code = p.fault_code
GROUP BY 1
ORDER BY 1;

-- name: downtime_by_fault
-- Minutes d'arrêt cumulées par type de défaut, maintenance corrective seule.
SELECT
    m.fault_code,
    f.label_fr AS libelle_defaut,
    count(*) AS nb_interventions,
    sum(m.downtime_minutes) AS minutes_arret,
    round(avg(m.downtime_minutes), 1) AS moyenne_minutes
FROM plant.maintenance_events m
JOIN plant.fault_types f ON f.fault_code = m.fault_code
WHERE m.category = 'corrective'
GROUP BY m.fault_code, f.label_fr
ORDER BY minutes_arret DESC;

-- name: peak_energy_intervals
-- Intervalles dépassant le seuil d'alerte de pointe (99 kWh sur 15 min).
SELECT
    ts,
    usage_kwh,
    load_type,
    lagging_current_power_factor
FROM plant.energy_readings
WHERE usage_kwh > 99.0
ORDER BY usage_kwh DESC;

-- name: energy_by_load_type
-- Consommation et CO2 agrégés par régime de charge.
SELECT
    load_type,
    count(*) AS nb_intervalles,
    round(sum(usage_kwh)::numeric, 1) AS total_kwh,
    round(sum(co2_tco2)::numeric, 3) AS total_tco2,
    round(avg(usage_kwh)::numeric, 2) AS moyenne_kwh
FROM plant.energy_readings
GROUP BY load_type
ORDER BY total_kwh DESC;

-- name: plates_on_hold
-- Tôles mises en attente qualité: gravité >= 2 ou rayure traversante.
-- TODO(cm): aligner cette règle sur quality_hold.py, la liste ALWAYS_HOLD
-- y est codée en dur et les deux peuvent diverger.
SELECT
    p.plate_id,
    p.line_id,
    p.inspected_at,
    p.fault_code,
    f.severity
FROM plant.plate_inspections p
JOIN plant.fault_types f ON f.fault_code = p.fault_code
WHERE f.severity >= 2
   OR p.fault_code IN ('Z_Scratch', 'K_Scratch')
ORDER BY p.inspected_at;
