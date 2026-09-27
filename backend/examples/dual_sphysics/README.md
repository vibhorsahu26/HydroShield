# DualSPHysics 5.4.3 input template

HydroShield uses a user-supplied DualSPHysics `Case_Def.xml` as the native model definition. The adapter copies that XML into the run directory, validates it, and substitutes supported HydroShield placeholders before invoking the native toolchain.

Supported placeholders:

- `{HYDROSHIELD_TIME_MAX_S}`
- `{HYDROSHIELD_TIME_OUT_S}`
- `{HYDROSHIELD_BREACH_WIDTH_M}`
- `{HYDROSHIELD_BREACH_DEPTH_M}`
- `{HYDROSHIELD_BREACH_FORMATION_TIME_S}`
- `{HYDROSHIELD_INITIAL_DISCHARGE_M3S}`
- `{HYDROSHIELD_CONTROLLED_RELEASE_DISCHARGE_M3S}`
- `{HYDROSHIELD_RESERVOIR_WATER_LEVEL_M}`
- `{HYDROSHIELD_RESERVOIR_VOLUME_M3}`
- `{HYDROSHIELD_BATHYMETRY_FILE}`

The bathymetry placeholder is intended for a `<drawfilecsv file="..." mode="bathymetry" />` for automatic cases; expert/custom cases may still use `<drawbathymetry>` / `<zpoints file="..." />` section. The adapter converts the Phase 4 DEM into XYZ points for that input.

HydroShield does not invent the dam geometry or breach geometry inside the XML. The project-specific `Case_Def.xml` remains the authoritative native representation; scenario parameters are injected only where the template explicitly asks for them.
