"""Constants for the AVE dominaplus integration."""

DOMAIN = "ave_dominaplus"
BRAND_PREFIX = "AVE dominaplus"

AVE_FAMILY_ONOFFLIGHTS = 1
AVE_FAMILY_DIMMER = 2  # requires LI2
AVE_FAMILY_SHUTTER_ROLLING = 3
AVE_FAMILY_SHUTTER_SLIDING = 16
AVE_FAMILY_SHUTTER_HUNG = 19
AVE_FAMILY_THERMOSTAT = 4
AVE_FAMILY_ECO = 5
AVE_FAMILY_SCENARIO = 6
AVE_FAMILY_ANTITHEFT = 7
AVE_FAMILY_CAMERA = 8
AVE_FAMILY_KEYPAD = 11
AVE_FAMILY_ANTITHEFT_AREA = 12
AVE_FAMILY_P3000 = 13  # P3000 sensor
AVE_FAMILY_VIVALDI = 14  # but onl if name starts with _VIV_
AVE_FAMILY_AVANO = 17
AVE_FAMILY_LIGHTING_RGBW = 22
AVE_FAMILY_MOTION_SENSOR = 1007  # not really a proper family, added in this integration do discriminate motion sensors from other devices


AVE_UNHANDLED_UPD = {
    "GUI": "GUI update",
    "D": "Icon update",
    "HO": "TS1 devices",
    "VMM": "Daikin mode",
    "TAF": "Thermostat anti-freezing",
    "TK": "Thermostat keyboard lock",
    "UMI": "Humidity probe",
    "S": "Tutondo",
    "VI": "Vivaldi",
    "A": "Alarm",
    "CS1": "Alarm",
    "CS2": "Alarm",
    "CS3": "Alarm",
    "abl": "Abano",
    "LL": "Label update",
    "SRE": "Alarm silence",
    "STO": "Alarm silence",
    "RGB": "Colorwheel update",
    "grp": "Group dimmer",
    "epv": "Economizer values",
    "htl": "Hotel",
}
