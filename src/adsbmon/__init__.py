# Constants for dump1090-fa ADS-B messages

'''
ADSB_MSG_FIELDS = (
  hex, type, flight, alt_baro, alt_geom, gs, ias, tas, mach, track, track_rate,
    roll, mag_heading, true_heading, baro_rate, geom_rate, squawk, emergency,
    category, nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading,
    nav_modes, lat, lon, nic, rc, seen_pos, version, nic_baro, nac_p, nac_v,
    sil, sil_type, gva, sda, modea, modec, mlat, tisb, messages, seen, rssi
)
'''

ADSB_MSG_TYPE_FIELDS = (
    "adsb_icao",
    "adsb_icao_nt",
    "adsr_icao",
    "tisb_icao",
    "adsb_other",
    "adsr_other",
    "tisb_other",
    "tisb_trackfile"
)

ADSB_MSGS_FIELDS_SORTED = [
    "alt_baro",          # uint | "ground"
    "alt_geom",          # uint
    "baro_rate",         # int
    "category",          # '[A-D][0-7]'
    "emergency",         # ?
    "flight",            # "none"
    "geom_rate",         # int
    "gs",                # float %f.1
    "gva",               # ???? (1, 2)
    "hex",               # six lowercase hex characters
    "lat",               # float %f.6
    "lon",               # float %f.6
    "messages",          # uint
    "mlat",              # []
    "nac_p",             # uint ????
    "nac_v",             # uint ????
    "nav_altitude_fms",  # uint
    "nav_altitude_mcp",  # uint
    "nav_heading",       #
    "nav_modes",         # []
    "nav_qnh",           # float %f.1 [0-360]
    "nic",               # uint ????
    "nic_baro",          # uint ????
    "rc",                # uint ????
    "rssi",              # float -%f.1 (negative)
    "sda",               # uint ????
    "seen",              # float %f.1
    "seen_pos",          # float %f.1
    "seenPosTime",       # float %f.7 (unix time)
    "seenTime",          # float %f.7 (unix time)
    "sil",               # uint ????
    "sil_type",          # {"perhour"| "unknown"} ????
    "squawk",            # uint %4d
    "tisb",              # {"tisb_other" | []) -- list of these keys????
    "track",             # float %f.1 [0.0-360.0??]
    "type",              # ???? ("adsr_icao", tisb_other", "unknown")
    "updateTime",        # float %f.6 (unix time)
    "version"            # uint (0, 2)
]

ICAO_EMERGENCY_SQUAWK_CODES = {
    7500: "Hijack/Unlawful Interference",  # silent
    7600: "Radio Failure",  # can hear but can't transmit
    7700: "Emergency"       # immediate priority, ATC clears airspace, emergency services alerted
}

COMMON_NON_EMERGENCY_SPECIAL_CODES = {
    1200: "VFR flight",          # US/Canada
    2000: "IFR entering controlled airspace from uncontrolled",  # Global
    7000: "VFR flight",          # Europe/UK
    7600: "Radio comms failure", # Global
    7777: "Military"            # intercept operations
}

#### TODO make these values all formatting strings
MLAT_TISB_FORMAT = [
    {"lat": "float"},        # latitude (decimal degrees)
    {"lon": "float"},        # longitude (decimal degrees)
    {"altitude": "float"},   # barometric altitude (feet)
    {"track": "float"},      # true heading (degrees)
    {"timestamp": "float"},  # unix timestamp of calculation
    {"nucp": "int"}          # Navigation Uncertainty Category Position [0-9]
]
