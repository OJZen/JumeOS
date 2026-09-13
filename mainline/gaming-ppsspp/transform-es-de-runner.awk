{
  if (index($0, base_uuid)) { gsub(base_uuid, uuid); uuid_changes++ }
  if (index($0, base_systems)) { gsub(base_systems, systems); systems_changes++ }
  if (index($0, base_append)) { gsub(base_append, append); append_changes++ }
  if (index($0, "systems=11")) { gsub("systems=11", "systems=12"); count_changes++ }

  if ($0 == "readonly FBNEO_FULL_CORE_SHA256=" fbneo_hash) {
    print
    print "readonly PPSSPP_CORE=/usr/local/libexec/ppsspp_libretro.so"
    print "readonly PPSSPP_CORE_SHA256=" core_hash
    print "readonly PPSSPP_ASSETS=/usr/share/r46h/libretro-system/PPSSPP"
    print "readonly PPSSPP_ASSETS_MANIFEST=/usr/share/r46h/libretro-system/PPSSPP.ASSETS.sha256"
    print "readonly PPSSPP_ASSETS_MANIFEST_SHA256=" assets_hash
    constants++
    next
  }
  if ($0 ~ /FBNEO_FULL_CORE:.*FBNEO_FULL_CORE_SHA256/) {
    print
    print "  \"$PPSSPP_CORE:$PPSSPP_CORE_SHA256\" \\"
    print "  \"$PPSSPP_ASSETS_MANIFEST:$PPSSPP_ASSETS_MANIFEST_SHA256\" \\"
    pairs++
    next
  }
  if ($0 == "  die 'RetroArch Chinese font alias changed'") {
    print
    print "(cd \"$PPSSPP_ASSETS\" && sha256sum -c \"$PPSSPP_ASSETS_MANIFEST\" >/dev/null) || \\"
    print "  die 'PPSSPP asset identity mismatch'"
    asset_checks++
    next
  }
  if ($0 == "  /usr/local/libexec/fbneo_libretro.so; do") {
    print "  /usr/local/libexec/fbneo_libretro.so \\"
    print "  /usr/local/libexec/ppsspp_libretro.so; do"
    runtimes++
    next
  }
  print
}

END {
  if (uuid_changes != 1 || systems_changes != 1 || append_changes != 1 ||
      count_changes != 1 || constants != 1 || pairs != 1 || asset_checks != 1 ||
      runtimes != 1) exit 2
}
