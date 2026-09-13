{
  if (index($0, base_uuid)) { gsub(base_uuid, uuid); uuid_changes++ }
  if (index($0, base_systems)) { gsub(base_systems, systems); systems_changes++ }
  if (index($0, "systems=13")) { gsub("systems=13", "systems=14"); count_changes++ }

  if ($0 == "readonly FLYCAST_SYSTEM=/usr/share/r46h/libretro-system/dc") {
    print
    print "readonly GENESISPLUSGX_CORE=/usr/local/libexec/genesis_plus_gx_libretro.so"
    print "readonly GENESISPLUSGX_CORE_SHA256=" core_hash
    constants++
    next
  }
  if ($0 == "  \"$FLYCAST_CORE:$FLYCAST_CORE_SHA256\" \\") {
    print
    print "  \"$GENESISPLUSGX_CORE:$GENESISPLUSGX_CORE_SHA256\" \\"
    pairs++
    next
  }
  if ($0 == "  /usr/local/libexec/flycast_libretro.so; do") {
    print "  /usr/local/libexec/flycast_libretro.so \\"
    print "  /usr/local/libexec/genesis_plus_gx_libretro.so; do"
    runtimes++
    next
  }
  print
}

END {
  if (uuid_changes != 1 || systems_changes != 1 || count_changes != 1 ||
      constants != 1 || pairs != 1 || runtimes != 1) exit 2
}
