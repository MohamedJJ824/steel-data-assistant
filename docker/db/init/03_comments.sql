-- Bilingual FR/EN documentation for every business table and column.
-- The text-to-SQL tool builds its schema context from these comments, so they
-- are functional, not decorative. Keep them accurate.

-- ------------------------------------------------ plant.production_lines ----
COMMENT ON TABLE plant.production_lines IS
  'Lignes de production de l''usine (donnees synthetiques) / Plant production lines (synthetic data)';
COMMENT ON COLUMN plant.production_lines.line_id IS
  'Identifiant de ligne, L1 a L3 / Line identifier, L1 to L3';
COMMENT ON COLUMN plant.production_lines.name_fr IS
  'Nom de la ligne en francais / Line name in French';
COMMENT ON COLUMN plant.production_lines.name_en IS
  'Nom de la ligne en anglais / Line name in English';
COMMENT ON COLUMN plant.production_lines.process IS
  'Procede: hot_rolling, cold_rolling, finishing / Process stage';
COMMENT ON COLUMN plant.production_lines.commissioned_year IS
  'Annee de mise en service / Year the line entered service';

-- ---------------------------------------------------------- plant.shifts ----
COMMENT ON TABLE plant.shifts IS
  'Postes de travail en 3x8 (donnees synthetiques) / Three-shift working pattern (synthetic data)';
COMMENT ON COLUMN plant.shifts.shift_code IS
  'Code du poste: M matin, A apres-midi, N nuit / Shift code: M morning, A afternoon, N night';
COMMENT ON COLUMN plant.shifts.label_fr IS
  'Libelle du poste en francais / Shift label in French';
COMMENT ON COLUMN plant.shifts.label_en IS
  'Libelle du poste en anglais / Shift label in English';
COMMENT ON COLUMN plant.shifts.start_hour IS
  'Heure de debut du poste, 0-23, incluse / Shift start hour, 0-23, inclusive';
COMMENT ON COLUMN plant.shifts.end_hour IS
  'Heure de fin du poste, 0-23, exclue. Le poste de nuit franchit minuit / Shift end hour, 0-23, exclusive. The night shift wraps past midnight';

-- ----------------------------------------------------- plant.fault_types ----
COMMENT ON TABLE plant.fault_types IS
  'Reference des types de defauts de surface, avec gravite et procedure associee / Reference table of surface fault types, with severity and linked procedure';
COMMENT ON COLUMN plant.fault_types.fault_code IS
  'Code du defaut: Pastry, Z_Scratch, K_Scratch, Stains, Dirtiness, Bumps, Other_Faults / Fault code';
COMMENT ON COLUMN plant.fault_types.label_fr IS
  'Libelle du defaut en francais / Fault label in French';
COMMENT ON COLUMN plant.fault_types.label_en IS
  'Libelle du defaut en anglais / Fault label in English';
COMMENT ON COLUMN plant.fault_types.severity IS
  'Gravite de 1 (mineur) a 3 (critique) / Severity from 1 (minor) to 3 (critical)';
COMMENT ON COLUMN plant.fault_types.procedure_doc_id IS
  'doc_id de la procedure de traitement dans le corpus documentaire / doc_id of the handling procedure in the document corpus';

-- ------------------------------------------------- plant.energy_readings ----
COMMENT ON TABLE plant.energy_readings IS
  'Consommation electrique par intervalle de 15 min sur 2018, donnees reelles UCI id=851 (aciérie de Gwangyang, Coree du Sud), 35040 lignes / Electricity consumption per 15-minute interval across 2018, real UCI data id=851 (Gwangyang steel plant, South Korea), 35040 rows';
COMMENT ON COLUMN plant.energy_readings.ts IS
  'Horodatage de FIN de l''intervalle de 15 min / Timestamp marking the END of the 15-minute interval';
COMMENT ON COLUMN plant.energy_readings.usage_kwh IS
  'Consommation active en kWh sur l''intervalle de 15 min / Active energy use in kWh over the 15-minute interval';
COMMENT ON COLUMN plant.energy_readings.lagging_current_reactive_power_kvarh IS
  'Energie reactive inductive en kVarh / Lagging (inductive) reactive energy in kVarh';
COMMENT ON COLUMN plant.energy_readings.leading_current_reactive_power_kvarh IS
  'Energie reactive capacitive en kVarh / Leading (capacitive) reactive energy in kVarh';
COMMENT ON COLUMN plant.energy_readings.co2_tco2 IS
  'Emissions de CO2 en tonnes sur l''intervalle / CO2 emissions in tonnes over the interval';
COMMENT ON COLUMN plant.energy_readings.lagging_current_power_factor IS
  'Facteur de puissance inductif en pourcentage, 0-100 / Lagging power factor as a percentage, 0-100';
COMMENT ON COLUMN plant.energy_readings.leading_current_power_factor IS
  'Facteur de puissance capacitif en pourcentage, 0-100 / Leading power factor as a percentage, 0-100';
COMMENT ON COLUMN plant.energy_readings.nsm IS
  'Nombre de secondes depuis minuit, 0-86400 / Number of seconds from midnight, 0-86400';
COMMENT ON COLUMN plant.energy_readings.week_status IS
  'Weekday ou Weekend / Weekday or Weekend';
COMMENT ON COLUMN plant.energy_readings.day_of_week IS
  'Jour de la semaine en anglais, Monday a Sunday / Day of week in English, Monday to Sunday';
COMMENT ON COLUMN plant.energy_readings.load_type IS
  'Regime de charge: Light_Load, Medium_Load, Maximum_Load / Load regime';

-- ---------------------------------------------- plant.plate_inspections ----
COMMENT ON TABLE plant.plate_inspections IS
  'Inspections de toles: 27 mesures geometriques et de luminosite plus le defaut constate. Donnees reelles UCI id=198, 1941 toles. line_id et inspected_at sont synthetiques / Steel plate inspections: 27 geometric and luminosity measurements plus the observed fault. Real UCI data id=198, 1941 plates. line_id and inspected_at are synthetic';
COMMENT ON COLUMN plant.plate_inspections.plate_id IS
  'Identifiant de la tole, numerotation sequentielle / Plate identifier, sequential numbering';
COMMENT ON COLUMN plant.plate_inspections.line_id IS
  'Ligne sur laquelle la tole a ete inspectee (SYNTHETIQUE) / Line where the plate was inspected (SYNTHETIC)';
COMMENT ON COLUMN plant.plate_inspections.inspected_at IS
  'Date et heure de l''inspection en 2018, ponderee vers les postes de jour (SYNTHETIQUE) / Inspection timestamp in 2018, weighted towards day shifts (SYNTHETIC)';
COMMENT ON COLUMN plant.plate_inspections.steel_grade IS
  'Nuance d''acier, A300 ou A400, issue des colonnes one-hot d''origine / Steel grade, A300 or A400, collapsed from the original one-hot columns';
COMMENT ON COLUMN plant.plate_inspections.fault_code IS
  'Defaut constate, une seule valeur par tole, issu des 7 colonnes one-hot d''origine / Observed fault, exactly one per plate, collapsed from the original 7 one-hot columns';
COMMENT ON COLUMN plant.plate_inspections.x_minimum IS 'Coordonnee X minimale du defaut en pixels / Minimum X coordinate of the fault in pixels';
COMMENT ON COLUMN plant.plate_inspections.x_maximum IS 'Coordonnee X maximale du defaut en pixels / Maximum X coordinate of the fault in pixels';
COMMENT ON COLUMN plant.plate_inspections.y_minimum IS 'Coordonnee Y minimale du defaut en pixels / Minimum Y coordinate of the fault in pixels';
COMMENT ON COLUMN plant.plate_inspections.y_maximum IS 'Coordonnee Y maximale du defaut en pixels / Maximum Y coordinate of the fault in pixels';
COMMENT ON COLUMN plant.plate_inspections.pixels_areas IS 'Surface du defaut en pixels / Fault area in pixels';
COMMENT ON COLUMN plant.plate_inspections.x_perimeter IS 'Perimetre du defaut selon X / Fault perimeter along X';
COMMENT ON COLUMN plant.plate_inspections.y_perimeter IS 'Perimetre du defaut selon Y / Fault perimeter along Y';
COMMENT ON COLUMN plant.plate_inspections.sum_of_luminosity IS 'Somme des luminosites des pixels du defaut / Sum of pixel luminosity over the fault';
COMMENT ON COLUMN plant.plate_inspections.minimum_of_luminosity IS 'Luminosite minimale, 0-255 / Minimum luminosity, 0-255';
COMMENT ON COLUMN plant.plate_inspections.maximum_of_luminosity IS 'Luminosite maximale, 0-255 / Maximum luminosity, 0-255';
COMMENT ON COLUMN plant.plate_inspections.length_of_conveyer IS 'Longueur du convoyeur en mm / Conveyer length in mm';
COMMENT ON COLUMN plant.plate_inspections.steel_plate_thickness IS 'Epaisseur de la tole en mm / Steel plate thickness in mm';
COMMENT ON COLUMN plant.plate_inspections.edges_index IS 'Indice de bord, 0-1 / Edges index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.empty_index IS 'Indice de vide, 0-1 / Empty index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.square_index IS 'Indice de compacite, 0-1 / Squareness index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.outside_x_index IS 'Indice de debordement selon X, 0-1 / Outside X index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.edges_x_index IS 'Indice de bord selon X, 0-1 / Edges X index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.edges_y_index IS 'Indice de bord selon Y, 0-1 / Edges Y index, 0-1';
COMMENT ON COLUMN plant.plate_inspections.outside_global_index IS 'Indice global de debordement, 0, 0.5 ou 1 / Global outside index, 0, 0.5 or 1';
COMMENT ON COLUMN plant.plate_inspections.log_of_areas IS 'Logarithme decimal de la surface / Base-10 logarithm of the area';
COMMENT ON COLUMN plant.plate_inspections.log_x_index IS 'Logarithme decimal de l''extension X / Base-10 logarithm of the X extent';
COMMENT ON COLUMN plant.plate_inspections.log_y_index IS 'Logarithme decimal de l''extension Y / Base-10 logarithm of the Y extent';
COMMENT ON COLUMN plant.plate_inspections.orientation_index IS 'Indice d''orientation, -1 a 1 / Orientation index, -1 to 1';
COMMENT ON COLUMN plant.plate_inspections.luminosity_index IS 'Indice de luminosite, -1 a 1 / Luminosity index, -1 to 1';
COMMENT ON COLUMN plant.plate_inspections.sigmoid_of_areas IS 'Sigmoide de la surface, 0-1 / Sigmoid of the area, 0-1';

-- --------------------------------------------- plant.maintenance_events ----
COMMENT ON TABLE plant.maintenance_events IS
  'Interventions de maintenance et arrets associes en 2018 (ENTIEREMENT SYNTHETIQUE) / Maintenance interventions and associated downtime in 2018 (FULLY SYNTHETIC)';
COMMENT ON COLUMN plant.maintenance_events.event_id IS
  'Identifiant de l''intervention / Intervention identifier';
COMMENT ON COLUMN plant.maintenance_events.line_id IS
  'Ligne concernee par l''intervention / Line the intervention applies to';
COMMENT ON COLUMN plant.maintenance_events.started_at IS
  'Debut de l''arret / Start of the downtime window';
COMMENT ON COLUMN plant.maintenance_events.ended_at IS
  'Fin de l''arret / End of the downtime window';
COMMENT ON COLUMN plant.maintenance_events.downtime_minutes IS
  'Duree d''arret en minutes, coherente avec started_at et ended_at / Downtime in minutes, consistent with started_at and ended_at';
COMMENT ON COLUMN plant.maintenance_events.category IS
  'preventive (planifiee) ou corrective (suite a un defaut) / preventive (planned) or corrective (fault-driven)';
COMMENT ON COLUMN plant.maintenance_events.fault_code IS
  'Defaut a l''origine de l''intervention, NULL pour la maintenance preventive / Fault that triggered the intervention, NULL for preventive maintenance';
COMMENT ON COLUMN plant.maintenance_events.report_doc_id IS
  'doc_id du rapport de maintenance dans le corpus, NULL si aucun rapport n''a ete redige / doc_id of the maintenance report in the corpus, NULL when no report was written';
