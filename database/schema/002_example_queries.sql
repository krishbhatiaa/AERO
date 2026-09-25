-- Reference PostGIS queries used by the backend/impact engine (equivalent of ml.impact.geometry.RegionIndex).

-- 1) Which administrative regions does an event's risk polygon intersect, and by how much?
--    Areas are computed on the spheroid (geography cast), never in planar degrees.
--    :event_id and :lead are bind parameters.
SELECT r.id, r.name, r.level,
       ST_Area(ST_Intersection(r.geom, g.geom)::geography) / 1e6                      AS intersect_area_km2,
       ST_Area(ST_Intersection(r.geom, g.geom)::geography) / NULLIF(ST_Area(r.geom::geography), 0) AS fraction_of_region
FROM   geographic_regions r
JOIN   impact_geometries g ON g.event_id = :event_id AND g.kind = 'RISK' AND g.valid_time = :lead
WHERE  ST_Intersects(r.geom, g.geom)            -- uses the GIST indexes on both geometry columns
ORDER  BY intersect_area_km2 DESC;

-- 2) Events whose footprint intersects a bounding box within a time window, most severe first.
SELECT id, event_type, severity, first_valid_time, last_valid_time
FROM   weather_events
WHERE  footprint && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
  AND  first_valid_time <= :to AND last_valid_time >= :from
ORDER  BY severity DESC, last_valid_time DESC;

-- 3) Great-circle distance (km) from an event centroid to a point of interest.
SELECT ST_Distance(centroid::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000.0 AS km
FROM   weather_events WHERE id = :event_id;
