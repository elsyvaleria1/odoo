from .geodesy import has_fix, haversine_km, haversine_m

# Shared by the trail analytics and the daily report so both surfaces filter
# GPS drift and cap signal gaps identically.
GPS_DRIFT_THRESHOLD_KM = 0.025
GPS_MAX_GAP_SECONDS = 1200
