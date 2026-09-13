fn main() {
    println!("cargo:rerun-if-changed=src/macos_native.c");
    if !matches!(std::env::var("CARGO_CFG_TARGET_OS").as_deref(), Ok("macos")) {
        return;
    }

    cc::Build::new()
        .file("src/macos_native.c")
        .flag("-std=c11")
        .flag("-Wconversion")
        .flag("-Wsign-conversion")
        .warnings_into_errors(true)
        .compile("r46h_card_macos_native");
    println!("cargo:rustc-link-lib=framework=CoreFoundation");
    println!("cargo:rustc-link-lib=framework=DiskArbitration");
    println!("cargo:rustc-link-lib=framework=IOKit");
}
