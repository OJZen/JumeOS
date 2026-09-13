{
  if (index($0, base_uuid)) { gsub(base_uuid, uuid); uuid_changes++ }
  if (index($0, base_systems)) { gsub(base_systems, systems); systems_changes++ }
  if (index($0, "systems=12")) { gsub("systems=12", "systems=13"); count_changes++ }

  if ($0 == "readonly PPSSPP_ASSETS_MANIFEST_SHA256=" assets_hash) {
    print
    print "readonly FLYCAST_CORE=/usr/local/libexec/flycast_libretro.so"
    print "readonly FLYCAST_CORE_SHA256=" core_hash
    print "readonly FLYCAST_SYSTEM=/usr/share/r46h/libretro-system/dc"
    constants++
    next
  }
  if ($0 ~ /PPSSPP_ASSETS_MANIFEST:.*PPSSPP_ASSETS_MANIFEST_SHA256/) {
    print
    print "  \"$FLYCAST_CORE:$FLYCAST_CORE_SHA256\" \\"
    pairs++
    next
  }
  if ($0 == "  die 'PPSSPP asset identity mismatch'") {
    print
    print "[[ -d $FLYCAST_SYSTEM && ! -L $FLYCAST_SYSTEM ]] || die 'Flycast system directory is missing'"
    print "[[ $(stat -c '%u:%g:%a' \"$FLYCAST_SYSTEM\") == 1000:1000:700 ]] || \\"
    print "  die 'Flycast system directory metadata is unsafe'"
    state_checks++
    next
  }
  if ($0 == "  /usr/local/libexec/ppsspp_libretro.so; do") {
    print "  /usr/local/libexec/ppsspp_libretro.so \\"
    print "  /usr/local/libexec/flycast_libretro.so; do"
    runtimes++
    next
  }
  print
}

END {
  if (uuid_changes != 1 || systems_changes != 1 || count_changes != 1 ||
      constants != 1 || pairs != 1 || state_checks != 1 || runtimes != 1) exit 2
}
