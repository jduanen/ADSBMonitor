# Constants for dump1090-fa ADS-B messages

ADSB_MSG_FIELDS = (
  hex, type, flight, alt_baro, alt_geom, gs, ias, tas, mach, track, track_rate,
  roll, mag_heading, true_heading, baro_rate, geom_rate, squawk, emergency,
  category, nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading,
  nav_modes, lat, lon, nic, rc, seen_pos, version, nic_baro, nac_p, nac_v,
  sil, sil_type, gva, sda, modea, modec, mlat, tisb, messages, seen, rssi
)

ADSB_MSG_TYPE_FIELDS = (
  adsb_icao,
  adsb_icao_nt,
  adsr_icao,
  tisb_icao,
  adsb_other,
  adsr_other,
  tisb_other,
  tisb_trackfile
)
