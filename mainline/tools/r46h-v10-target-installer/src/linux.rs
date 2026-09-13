use r46h_v10_target_installer::{
    freeze_sources, install_candidate_files, verify_boot_state, BootState, Contract,
    DurableFilesystem, Error, FileSpec, LinuxDurability, Result,
};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicI32, Ordering};

const TOOL_ID: &str = "r46h-v10-one-shot-target-installer-v0.1";
const EXPECTED_RUNNING_RELEASE: &str = "6.12.99-r46h-mainline-v0.8-bootloader-handoff";
const TARGET_RELEASE: &str = "6.12.99-r46h-mainline-v0.10-adc-full-range";
const CONFIRM_TOKEN: &str = "install-v0.10-one-shot-keep-v0.8-active";
const EXPECTED_EXECUTABLE: &str = "/run/r46h-v10-one-shot-installer";
const LOCK_PATH: &str = "/run/r46h-v10-one-shot-installer.lock";
const WHOLE_DEVICE: &str = "/dev/mmcblk0";
const BOOT_DEVICE: &str = "/dev/mmcblk0p1";
const ROOT_DEVICE: &str = "/dev/mmcblk0p2";
const ROMS_DEVICE: &str = "/dev/mmcblk0p3";
const WHOLE_SIZE: u64 = 62_534_975_488;
const SECTOR_SIZE: u64 = 512;
const BOOT_SIZE: u64 = 117_440_512;
const PREFIX_SIZE: u64 = 16_777_216;
const EXPECTED_PREFIX_SHA256: &str =
    "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3";
const EXPECTED_P1_BASE_SHA256: &str =
    "5784db8171c096b9f6289bcb7914d5d7f05051a50434149080660544f1ab81f5";
const EXPECTED_P1_INSTALLED_SHA256: &str =
    "ef62200bb7a245239c34ae65a992e897a160e4301fbd90634626dbe0b967fc88";
const EXPECTED_FIRSTBOOT: &str = "release=debian13-p2-mvp-v0.1";
const MODULE_CONFIRM_TOKEN: &str = "install-v0.10-modules-from-fast-card";
const MODULE_PACKAGE_NAME: &str = "r46h-mainline-test-v0.10-adc-full-range";
const MODULE_TAR_NAME: &str = "r46h-mainline-test-v0.10-adc-full-range.tar.gz";
const MODULE_TAR_SIZE: u64 = 33_258_814;
const MODULE_TAR_SHA256: &str = "c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780";
const MODULE_TREE_SHA256: &str = "a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16";
const MODULE_COUNT: usize = 1_276;
const MODULE_FILE_COUNT: usize = 1_290;
const MODULE_EXTRACTION_BYTES: u64 = 113_447_508;
const FALLBACK_MODULE_TREE_SHA256: &str =
    "2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210";
const FALLBACK_MODULE_COUNT: usize = 1_276;
const FALLBACK_MODULE_FILE_COUNT: usize = 1_290;
const MODULES_PARENT: &str = "/lib/modules";
const MODULE_STAGE_NAME: &str = ".r46h-v10-modules.stage";
const MODULE_RECEIPT_PARENT: &str = "/var/lib/r46h";
const MODULE_RECEIPT_NAME: &str = "v0.10-modules-installed";
const MODULE_RECEIPT_STAGE_NAME: &str = ".v0.10-modules-installed.stage";
const MODULE_RECEIPT_BYTES: &[u8] = b"format_version=1\n\
tool_id=r46h-v10-module-installer-v0.1\n\
status=complete\n\
installed_from=6.12.99-r46h-mainline-v0.8-bootloader-handoff\n\
installed_release=6.12.99-r46h-mainline-v0.10-adc-full-range\n\
payload_tar_sha256=c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780\n\
module_tree_sha256=a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16\n\
module_count=1276\n\
module_tree_file_count=1290\n\
p1_sha256=ef62200bb7a245239c34ae65a992e897a160e4301fbd90634626dbe0b967fc88\n\
prefix_sha256=3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3\n";
const JOURNAL_BYTES: &[u8] = b"format_version=1\n\
tool_id=r46h-v10-one-shot-target-installer-v0.1\n\
baseline_p1_sha256=5784db8171c096b9f6289bcb7914d5d7f05051a50434149080660544f1ab81f5\n\
fallback_release=6.12.99-r46h-mainline-v0.8-bootloader-handoff\n\
target_release=6.12.99-r46h-mainline-v0.10-adc-full-range\n\
state=in-progress\n";

static STOP_SIGNAL: AtomicI32 = AtomicI32::new(0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    Preflight,
    Install,
    Recover,
    ModulesPreflight,
    InstallModules,
    RecoverModules,
}

#[derive(Debug)]
struct MountRecord {
    major: u64,
    minor: u64,
    mount_point: String,
    options: BTreeSet<String>,
    filesystem: String,
}

fn spec(name: &'static str, size: u64, sha256: &'static str) -> FileSpec {
    FileSpec { name, size, sha256 }
}

fn production_contract() -> Contract {
    let stable_top_level = [
        "USE_DTB_SELECT_TO_SELECT_DEVICE",
        "boot.ini",
        "uInitrd",
        "clone_log.txt",
        "consoles",
        "rk3326-r46h-linux.dtb",
        "Image",
        "firstboot.sh",
        "System Volume Information",
        "logo.bmp",
        "boot.log",
        ".console",
        ".Spotlight-V100",
        "boot.ini.vendor",
        "arkos4clone-uboot.dtb",
        "dtb_selector_macos",
        "dtb_selector_linux32",
        "dtb_selector_win32.exe",
        "error.log",
        "boot.ini.v0.8-bootloader-handoff",
        "Image.mainline-v0.8-bootloader-handoff.gz",
        "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb",
    ]
    .into_iter()
    .collect();
    let stable_directories = ["consoles", "System Volume Information", ".Spotlight-V100"]
        .into_iter()
        .collect();
    Contract {
        payload_name: "r46h-v0.10-adc-full-range",
        payload_manifest: spec(
            "DEPLOY-MANIFEST",
            5_148,
            "7413a2faa9503c448c84ace1dce248c67cc9bb3b983d3ccdb479007911488379",
        ),
        payload_complete: spec(
            "STAGE-COMPLETE",
            562,
            "be3c9a670999cc91617aac5ff1ee6467d963576cd5a3d6c9cc53192912668b5e",
        ),
        source_image: spec(
            "Image.mainline-v0.10-adc-full-range.gz",
            14_921_256,
            "736549a919eee0342a2bae961a85b59337ad8de3c901c2e5f193aa15fdead954",
        ),
        source_dtb: spec(
            "rk3326-r46h-mainline-v0.10-adc-full-range.dtb",
            49_481,
            "04868feae2678cbee5073f93250dafb0219e560b0f1131526ac89930a8791cee",
        ),
        source_boot: spec(
            "boot.ini.v0.10-adc-full-range",
            1_400,
            "017dc2211c71d3396b46afb265b046e63e4ba3c764541c1af48e53d32031f773",
        ),
        final_boot: spec(
            "boot.ini.v0.10-adc-full-range",
            1_408,
            "915039bf17dea6aa2ba42701195510c346c70c8c81117151e7d153073fa1ceab",
        ),
        boot_fallback_old: b"boot.ini.v0.2-known-good",
        boot_fallback_new: b"boot.ini.v0.8-bootloader-handoff",
        old_files: vec![
            spec(
                "Image.mainline-v0.9-adc-joystick-fix.gz",
                14_921_320,
                "8cf19559f3c55b5bfa7e77d556ad64667070e2e5be0c9c3305b0fdffb0101de2",
            ),
            spec(
                "boot.ini.v0.9-adc-joystick-fix",
                1_419,
                "cc4d1f7347a93985dcba027908325611cd530bf3bc1929bb2fbdeac43f8e12ce",
            ),
        ],
        anchors: vec![
            spec(
                "boot.ini",
                1_427,
                "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb",
            ),
            spec(
                "boot.ini.v0.8-bootloader-handoff",
                1_427,
                "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb",
            ),
            spec(
                "Image.mainline-v0.8-bootloader-handoff.gz",
                14_920_864,
                "d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa",
            ),
            spec(
                "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb",
                49_481,
                "7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc",
            ),
        ],
        stable_top_level,
        stable_directories,
        stage_suffix: ".r46h-stage",
        journal: spec(
            ".r46h-v10-one-shot-install.stage",
            288,
            "a71a331f6a64c0558fffcf5ada2a6ba6679e9b795a066a60b745965ce4b6c4e0",
        ),
        journal_bytes: JOURNAL_BYTES,
        minimum_free_bytes: 512 * 1024,
        source_date_epoch: 1_785_369_600,
    }
}

fn parse_arguments() -> Result<Mode> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [mode] if mode == "--preflight" => Ok(Mode::Preflight),
        [mode, confirm, token]
            if mode == "--install" && confirm == "--confirm" && token == CONFIRM_TOKEN =>
        {
            Ok(Mode::Install)
        }
        [mode, confirm, token]
            if mode == "--recover-partial" && confirm == "--confirm" && token == CONFIRM_TOKEN =>
        {
            Ok(Mode::Recover)
        }
        [mode] if mode == "--modules-preflight" => Ok(Mode::ModulesPreflight),
        [mode, confirm, token]
            if mode == "--install-modules"
                && confirm == "--confirm"
                && token == MODULE_CONFIRM_TOKEN =>
        {
            Ok(Mode::InstallModules)
        }
        [mode, confirm, token]
            if mode == "--recover-modules"
                && confirm == "--confirm"
                && token == MODULE_CONFIRM_TOKEN =>
        {
            Ok(Mode::RecoverModules)
        }
        _ => Err(Error(format!(
            "usage: {EXPECTED_EXECUTABLE} --preflight | --install --confirm {CONFIRM_TOKEN} | \
             --recover-partial --confirm {CONFIRM_TOKEN} | --modules-preflight | \
             --install-modules --confirm {MODULE_CONFIRM_TOKEN} | \
             --recover-modules --confirm {MODULE_CONFIRM_TOKEN}"
        ))),
    }
}

fn mount_unescape(mut value: String) -> String {
    for (encoded, decoded) in [
        ("\\040", " "),
        ("\\011", "\t"),
        ("\\012", "\n"),
        ("\\134", "\\"),
    ] {
        value = value.replace(encoded, decoded);
    }
    value
}

fn read_mountinfo() -> Result<Vec<MountRecord>> {
    let text = fs::read_to_string("/proc/self/mountinfo")
        .map_err(|error| Error(format!("read mountinfo: {error}")))?;
    let mut records = Vec::new();
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or_else(|| Error("malformed mountinfo separator".into()))?;
        let fields: Vec<&str> = left.split_whitespace().collect();
        let tail: Vec<&str> = right.split_whitespace().collect();
        if fields.len() < 6 || tail.len() < 2 {
            return Err(Error("malformed mountinfo fields".into()));
        }
        let (major, minor) = fields[2]
            .split_once(':')
            .ok_or_else(|| Error("malformed mountinfo device number".into()))?;
        records.push(MountRecord {
            major: major
                .parse()
                .map_err(|_| Error("malformed mountinfo major".into()))?,
            minor: minor
                .parse()
                .map_err(|_| Error("malformed mountinfo minor".into()))?,
            mount_point: mount_unescape(fields[4].to_owned()),
            options: fields[5].split(',').map(str::to_owned).collect(),
            filesystem: tail[0].to_owned(),
        });
    }
    Ok(records)
}

fn block_identity(path: &Path) -> Result<(u64, u64)> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| Error(format!("stat block device {}: {error}", path.display())))?;
    if !metadata.file_type().is_block_device() {
        return Err(Error(format!(
            "not a direct block device: {}",
            path.display()
        )));
    }
    Ok((
        u64::from(libc::major(metadata.rdev())),
        u64::from(libc::minor(metadata.rdev())),
    ))
}

fn ensure_unmounted(paths: &[&str]) -> Result<()> {
    let mounted: BTreeMap<(u64, u64), String> = read_mountinfo()?
        .into_iter()
        .map(|record| ((record.major, record.minor), record.mount_point))
        .collect();
    for path in paths {
        let identity = block_identity(Path::new(path))?;
        if let Some(mount_point) = mounted.get(&identity) {
            return Err(Error(format!("{path} is mounted at {mount_point}")));
        }
    }
    Ok(())
}

fn mount_matches_block(record: &MountRecord, identity: (u64, u64), filesystem: &str) -> bool {
    (record.major, record.minor) == identity
        && record.filesystem == filesystem
        && record.options.contains("rw")
}

fn verify_partition_alias(alias: &str, expected_device: &str) -> Result<()> {
    let alias_metadata = fs::symlink_metadata(alias)
        .map_err(|error| Error(format!("stat partition alias {alias}: {error}")))?;
    if !alias_metadata.file_type().is_symlink() {
        return Err(Error(format!("partition alias is not a symlink: {alias}")));
    }
    let resolved = fs::canonicalize(alias)
        .map_err(|error| Error(format!("resolve partition alias {alias}: {error}")))?;
    let observed = block_identity(&resolved)?;
    let expected = block_identity(Path::new(expected_device))?;
    if observed != expected {
        return Err(Error(format!(
            "partition alias identity mismatch: {alias} does not identify {expected_device}"
        )));
    }
    Ok(())
}

fn read_small_regular(path: &Path, maximum: u64) -> Result<String> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut file = options
        .open(path)
        .map_err(|error| Error(format!("open {}: {error}", path.display())))?;
    let metadata = file
        .metadata()
        .map_err(|error| Error(format!("fstat {}: {error}", path.display())))?;
    if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() > maximum {
        return Err(Error(format!("unsafe small file: {}", path.display())));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.read_to_end(&mut bytes)
        .map_err(|error| Error(format!("read {}: {error}", path.display())))?;
    if bytes.len() as u64 != metadata.len() {
        return Err(Error(format!("short read: {}", path.display())));
    }
    String::from_utf8(bytes)
        .map(|value| value.trim().to_owned())
        .map_err(|_| Error(format!("non-UTF-8 file: {}", path.display())))
}

fn read_pseudo_regular(path: &Path, maximum: u64) -> Result<String> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let file = options
        .open(path)
        .map_err(|error| Error(format!("open {}: {error}", path.display())))?;
    let metadata = file
        .metadata()
        .map_err(|error| Error(format!("fstat {}: {error}", path.display())))?;
    if !metadata.is_file() || metadata.nlink() != 1 {
        return Err(Error(format!("unsafe pseudo file: {}", path.display())));
    }
    let mut bytes = Vec::with_capacity(maximum.min(4096) as usize);
    file.take(maximum + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| Error(format!("read {}: {error}", path.display())))?;
    if bytes.is_empty() || bytes.len() as u64 > maximum {
        return Err(Error(format!(
            "empty or oversized pseudo file: {}",
            path.display()
        )));
    }
    String::from_utf8(bytes)
        .map(|value| value.trim().to_owned())
        .map_err(|_| Error(format!("non-UTF-8 file: {}", path.display())))
}

fn verify_production_identity() -> Result<()> {
    if unsafe { libc::geteuid() } != 0 {
        return Err(Error("production installer requires root".into()));
    }
    let executable = fs::canonicalize("/proc/self/exe")
        .map_err(|error| Error(format!("resolve current executable: {error}")))?;
    if executable != Path::new(EXPECTED_EXECUTABLE) {
        return Err(Error(format!(
            "installer must run from {EXPECTED_EXECUTABLE}"
        )));
    }
    let metadata = fs::symlink_metadata(EXPECTED_EXECUTABLE)
        .map_err(|error| Error(format!("stat installer: {error}")))?;
    if !metadata.is_file()
        || metadata.uid() != 0
        || metadata.gid() != 0
        || metadata.mode() & 0o7777 != 0o700
        || metadata.nlink() != 1
    {
        return Err(Error(
            "installer identity, owner, mode, or link count mismatch".into(),
        ));
    }
    let run: Vec<_> = read_mountinfo()?
        .into_iter()
        .filter(|record| record.mount_point == "/run")
        .collect();
    if run.len() != 1 || run[0].filesystem != "tmpfs" || !run[0].options.contains("rw") {
        return Err(Error("/run must be one writable tmpfs mount".into()));
    }
    if read_pseudo_regular(Path::new("/proc/sys/kernel/osrelease"), 256)?
        != EXPECTED_RUNNING_RELEASE
    {
        return Err(Error("running release mismatch".into()));
    }
    let root: Vec<_> = read_mountinfo()?
        .into_iter()
        .filter(|record| record.mount_point == "/")
        .collect();
    let root_identity = block_identity(Path::new(ROOT_DEVICE))?;
    if root.len() != 1 || !mount_matches_block(&root[0], root_identity, "ext4") {
        return Err(Error("root filesystem identity or state mismatch".into()));
    }
    if read_small_regular(Path::new("/var/lib/r46h/firstboot-complete"), 256)? != EXPECTED_FIRSTBOOT
    {
        return Err(Error("firstboot completion marker mismatch".into()));
    }
    if read_pseudo_regular(Path::new("/sys/fs/ext4/mmcblk0p2/errors_count"), 64)? != "0" {
        return Err(Error("ext4 error counter is nonzero".into()));
    }
    let output = Command::new("/usr/bin/systemctl")
        .args(["--failed", "--no-legend", "--plain"])
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .stdin(Stdio::null())
        .output()
        .map_err(|error| Error(format!("query failed units: {error}")))?;
    if !output.status.success() || !output.stdout.is_empty() {
        return Err(Error("systemd has failed units or the query failed".into()));
    }
    let dmesg = Command::new("/usr/bin/dmesg")
        .arg("--color=never")
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .stdin(Stdio::null())
        .output()
        .map_err(|error| Error(format!("read kernel log: {error}")))?;
    if !dmesg.status.success() {
        return Err(Error("kernel log query failed".into()));
    }
    let log = String::from_utf8(dmesg.stdout)
        .map_err(|_| Error("kernel log is not valid UTF-8".into()))?
        .to_ascii_lowercase();
    if let Some(fault) = storage_fault_marker(&log) {
        return Err(Error(format!(
            "current boot contains a storage fault marker: {fault}"
        )));
    }
    Ok(())
}

fn storage_fault_marker(log: &str) -> Option<&'static str> {
    [
        "mmc0: error",
        "mmc0: timeout",
        "mmcblk0: error",
        "buffer i/o error",
        "blk_update_request: i/o error",
        "ext4-fs error",
    ]
    .into_iter()
    .find(|fault| log.contains(fault))
}

fn read_decimal(path: &str) -> Result<u64> {
    let value = read_pseudo_regular(Path::new(path), 128)?;
    value
        .parse()
        .map_err(|_| Error(format!("malformed decimal value at {path}")))
}

fn verify_geometry() -> Result<()> {
    if read_decimal("/sys/class/block/mmcblk0/size")?
        .checked_mul(SECTOR_SIZE)
        .ok_or_else(|| Error("whole-card size overflow".into()))?
        != WHOLE_SIZE
    {
        return Err(Error("whole-card size mismatch".into()));
    }
    if read_decimal("/sys/class/block/mmcblk0/queue/logical_block_size")? != SECTOR_SIZE {
        return Err(Error("logical block size mismatch".into()));
    }
    for (name, start, size) in [
        ("mmcblk0p1", 32_768, 229_376),
        ("mmcblk0p2", 262_144, 20_931_401),
        ("mmcblk0p3", 21_193_545, 100_945_079),
    ] {
        if read_decimal(&format!("/sys/class/block/{name}/start"))? != start
            || read_decimal(&format!("/sys/class/block/{name}/size"))? != size
        {
            return Err(Error(format!("partition geometry mismatch: {name}")));
        }
    }
    let identities: BTreeSet<_> = [WHOLE_DEVICE, BOOT_DEVICE, ROOT_DEVICE, ROMS_DEVICE]
        .into_iter()
        .map(|path| block_identity(Path::new(path)))
        .collect::<Result<_>>()?;
    if identities.len() != 4 {
        return Err(Error("block-device identities are not unique".into()));
    }
    for (partuuid, device) in [
        ("c9f931c9-01", BOOT_DEVICE),
        ("c9f931c9-02", ROOT_DEVICE),
        ("c9f931c9-03", ROMS_DEVICE),
    ] {
        verify_partition_alias(&format!("/dev/disk/by-partuuid/{partuuid}"), device)?;
    }
    Ok(())
}

extern "C" fn signal_handler(signal: libc::c_int) {
    STOP_SIGNAL.store(signal, Ordering::SeqCst);
}

struct SignalGuard {
    previous: Vec<(libc::c_int, libc::sigaction)>,
}

impl SignalGuard {
    fn install() -> Result<Self> {
        let mut previous = Vec::new();
        for signal in [libc::SIGHUP, libc::SIGINT, libc::SIGTERM] {
            let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
            action.sa_sigaction = signal_handler as usize;
            unsafe { libc::sigemptyset(&mut action.sa_mask) };
            let mut old: libc::sigaction = unsafe { std::mem::zeroed() };
            if unsafe { libc::sigaction(signal, &action, &mut old) } != 0 {
                for (installed_signal, installed_action) in previous.iter().rev() {
                    unsafe {
                        libc::sigaction(*installed_signal, installed_action, std::ptr::null_mut())
                    };
                }
                return Err(Error(format!(
                    "install signal handler: {}",
                    std::io::Error::last_os_error()
                )));
            }
            previous.push((signal, old));
        }
        Ok(Self { previous })
    }

    fn begin_write(&self) -> Result<()> {
        let mut blocked: libc::sigset_t = unsafe { std::mem::zeroed() };
        unsafe { libc::sigemptyset(&mut blocked) };
        for signal in [libc::SIGHUP, libc::SIGINT, libc::SIGTERM] {
            unsafe { libc::sigaddset(&mut blocked, signal) };
        }
        let mut previous_mask: libc::sigset_t = unsafe { std::mem::zeroed() };
        if unsafe { libc::pthread_sigmask(libc::SIG_BLOCK, &blocked, &mut previous_mask) } != 0 {
            return Err(Error("block signals before write-started failed".into()));
        }
        if let Err(error) = check_signal() {
            unsafe {
                libc::pthread_sigmask(libc::SIG_SETMASK, &previous_mask, std::ptr::null_mut())
            };
            return Err(error);
        }
        for signal in [libc::SIGHUP, libc::SIGINT, libc::SIGTERM] {
            let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
            action.sa_sigaction = libc::SIG_IGN;
            unsafe { libc::sigemptyset(&mut action.sa_mask) };
            if unsafe { libc::sigaction(signal, &action, std::ptr::null_mut()) } != 0 {
                unsafe {
                    libc::pthread_sigmask(libc::SIG_SETMASK, &previous_mask, std::ptr::null_mut())
                };
                return Err(Error(format!(
                    "ignore signal after write-started: {}",
                    std::io::Error::last_os_error()
                )));
            }
        }
        if unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &previous_mask, std::ptr::null_mut()) }
            != 0
        {
            return Err(Error(
                "restore signal mask after write-started failed".into(),
            ));
        }
        Ok(())
    }
}

impl Drop for SignalGuard {
    fn drop(&mut self) {
        for (signal, action) in self.previous.iter().rev() {
            unsafe { libc::sigaction(*signal, action, std::ptr::null_mut()) };
        }
    }
}

fn check_signal() -> Result<()> {
    let signal = STOP_SIGNAL.load(Ordering::SeqCst);
    if signal != 0 {
        return Err(Error(format!(
            "interrupted by signal {signal} before write-started"
        )));
    }
    Ok(())
}

fn hash_block(path: &Path, expected_size: u64, label: &str) -> Result<String> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut file = options
        .open(path)
        .map_err(|error| Error(format!("open {}: {error}", path.display())))?;
    if !file
        .metadata()
        .map_err(|error| Error(format!("fstat {}: {error}", path.display())))?
        .file_type()
        .is_block_device()
    {
        return Err(Error(format!("not a block device: {}", path.display())));
    }
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 4 * 1024 * 1024];
    let mut total = 0_u64;
    file.seek(SeekFrom::Start(0))
        .map_err(|error| Error(format!("seek {}: {error}", path.display())))?;
    while total < expected_size {
        check_signal()?;
        let desired = usize::try_from((expected_size - total).min(buffer.len() as u64))
            .map_err(|_| Error("block hash size overflow".into()))?;
        let count = file
            .read(&mut buffer[..desired])
            .map_err(|error| Error(format!("read {}: {error}", path.display())))?;
        if count == 0 {
            return Err(Error(format!(
                "short block read: expected {expected_size}, got {total}"
            )));
        }
        digest.update(&buffer[..count]);
        total += count as u64;
        if total == expected_size || total % (64 * 1024 * 1024) == 0 {
            println!("R46H_V10_TARGET stage=raw-hash source={label} bytes={total}/{expected_size}");
        }
    }
    Ok(format!("{:x}", digest.finalize()))
}

struct LockGuard {
    file: File,
    identity: (u64, u64),
    finished: bool,
}

impl LockGuard {
    fn acquire() -> Result<Self> {
        let mut options = OpenOptions::new();
        options
            .read(true)
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
        let file = options
            .open(LOCK_PATH)
            .map_err(|error| Error(format!("open installer lock: {error}")))?;
        let metadata = file
            .metadata()
            .map_err(|error| Error(format!("fstat installer lock: {error}")))?;
        let named = fs::symlink_metadata(LOCK_PATH)
            .map_err(|error| Error(format!("stat installer lock: {error}")))?;
        if !metadata.is_file()
            || metadata.uid() != 0
            || metadata.gid() != 0
            || metadata.mode() & 0o7777 != 0o600
            || metadata.nlink() != 1
            || (metadata.dev(), metadata.ino()) != (named.dev(), named.ino())
        {
            return Err(Error("unsafe installer lock identity".into()));
        }
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(Error("another target installer is running".into()));
        }
        Ok(Self {
            file,
            identity: (metadata.dev(), metadata.ino()),
            finished: false,
        })
    }

    fn finish(&mut self) -> Result<()> {
        let metadata = fs::symlink_metadata(LOCK_PATH)
            .map_err(|error| Error(format!("revalidate installer lock: {error}")))?;
        if (metadata.dev(), metadata.ino()) != self.identity {
            return Err(Error("installer lock path identity changed".into()));
        }
        fs::remove_file(LOCK_PATH)
            .map_err(|error| Error(format!("remove installer lock: {error}")))?;
        self.finished = true;
        Ok(())
    }
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        if self.finished {
            return;
        }
        let _ = self.file.as_raw_fd();
        match fs::symlink_metadata(LOCK_PATH) {
            Ok(metadata) if (metadata.dev(), metadata.ino()) == self.identity => {
                if let Err(error) = fs::remove_file(LOCK_PATH) {
                    eprintln!("WARNING: cannot remove installer lock: {error}");
                }
            }
            Ok(_) => eprintln!("WARNING: installer lock identity changed; preserving path"),
            Err(error) => eprintln!("WARNING: cannot revalidate installer lock: {error}"),
        }
    }
}

fn random_hex() -> Result<String> {
    let mut random = [0_u8; 16];
    let mut file =
        File::open("/dev/urandom").map_err(|error| Error(format!("open /dev/urandom: {error}")))?;
    file.read_exact(&mut random)
        .map_err(|error| Error(format!("read /dev/urandom: {error}")))?;
    Ok(random.iter().map(|byte| format!("{byte:02x}")).collect())
}

struct WorkGuard {
    root: PathBuf,
    finished: bool,
}

impl WorkGuard {
    fn create() -> Result<Self> {
        let root = PathBuf::from(format!("/run/r46h-v10-one-shot.{}", random_hex()?));
        fs::DirBuilder::new()
            .mode(0o700)
            .create(&root)
            .map_err(|error| Error(format!("create private work directory: {error}")))?;
        let mut created = Vec::new();
        for child in ["roms", "boot", "source"] {
            let path = root.join(child);
            if let Err(error) = fs::DirBuilder::new().mode(0o700).create(&path) {
                for created_path in created.iter().rev() {
                    let _ = fs::remove_dir(created_path);
                }
                let _ = fs::remove_dir(&root);
                return Err(Error(format!("create private {child} directory: {error}")));
            }
            created.push(path);
        }
        Ok(Self {
            root,
            finished: false,
        })
    }

    fn path(&self, child: &str) -> PathBuf {
        self.root.join(child)
    }

    fn cleanup(&mut self, contract: &Contract) -> Result<()> {
        let canonical = fs::canonicalize(&self.root)
            .map_err(|error| Error(format!("resolve private work directory: {error}")))?;
        let prefix = format!("{}/", canonical.display());
        if read_mountinfo()?.iter().any(|record| {
            record.mount_point == canonical.to_string_lossy()
                || record.mount_point.starts_with(&prefix)
        }) {
            return Err(Error(format!(
                "preserving private work directory because a mount remains below it: {}",
                self.root.display()
            )));
        }
        for spec in contract.final_files() {
            let path = self.path("source").join(spec.name);
            match fs::remove_file(&path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(Error(format!("remove {}: {error}", path.display()))),
            }
        }
        let module_package = self.path("source").join(MODULE_TAR_NAME);
        match fs::remove_file(&module_package) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(Error(format!(
                    "remove {}: {error}",
                    module_package.display()
                )))
            }
        }
        for child in ["source", "boot", "roms"] {
            fs::remove_dir(self.path(child))
                .map_err(|error| Error(format!("remove private {child} directory: {error}")))?;
        }
        fs::remove_dir(&self.root)
            .map_err(|error| Error(format!("remove private work directory: {error}")))?;
        self.finished = true;
        Ok(())
    }
}

impl Drop for WorkGuard {
    fn drop(&mut self) {
        if !self.finished {
            eprintln!(
                "WARNING: private recovery work may remain at {}",
                self.root.display()
            );
        }
    }
}

struct MountedFilesystem {
    device: &'static str,
    mount_point: PathBuf,
    mounted: bool,
}

impl MountedFilesystem {
    fn mount(
        device: &'static str,
        mount_point: PathBuf,
        filesystem: &str,
        writable: bool,
    ) -> Result<Self> {
        let source = CString::new(device).unwrap();
        let target = CString::new(mount_point.as_os_str().as_encoded_bytes())
            .map_err(|_| Error("NUL in mount point".into()))?;
        let filesystem_c = CString::new(filesystem).unwrap();
        let data = CString::new(if writable { "umask=0077,flush" } else { "" }).unwrap();
        let mut flags = libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC;
        if !writable {
            flags |= libc::MS_RDONLY;
        }
        if unsafe {
            libc::mount(
                source.as_ptr(),
                target.as_ptr(),
                filesystem_c.as_ptr(),
                flags,
                data.as_ptr().cast(),
            )
        } != 0
        {
            return Err(Error(format!(
                "mount {device}: {}",
                std::io::Error::last_os_error()
            )));
        }
        let mut mounted = Self {
            device,
            mount_point,
            mounted: true,
        };
        if let Err(error) = mounted.verify(filesystem, writable) {
            let rollback = mounted.unmount();
            return match rollback {
                Ok(()) => Err(error),
                Err(cleanup) => Err(Error(format!(
                    "{error}; mount rollback also failed: {cleanup}"
                ))),
            };
        }
        Ok(mounted)
    }

    fn verify(&self, filesystem: &str, writable: bool) -> Result<()> {
        let identity = block_identity(Path::new(self.device))?;
        let mount_point = fs::canonicalize(&self.mount_point)
            .map_err(|error| Error(format!("resolve mount point: {error}")))?;
        let matches: Vec<_> = read_mountinfo()?
            .into_iter()
            .filter(|record| {
                (record.major, record.minor) == identity
                    && record.mount_point == mount_point.to_string_lossy()
            })
            .collect();
        let expected = if writable { "rw" } else { "ro" };
        let rejected = if writable { "ro" } else { "rw" };
        if matches.len() != 1
            || matches[0].filesystem != filesystem
            || !matches[0].options.contains(expected)
            || matches[0].options.contains(rejected)
        {
            return Err(Error(format!(
                "mount verification failed for {}",
                self.device
            )));
        }
        Ok(())
    }

    fn unmount(&mut self) -> Result<()> {
        if !self.mounted {
            return Ok(());
        }
        let target = CString::new(self.mount_point.as_os_str().as_encoded_bytes())
            .map_err(|_| Error("NUL in unmount path".into()))?;
        if unsafe { libc::umount2(target.as_ptr(), 0) } != 0 {
            return Err(Error(format!(
                "unmount {}: {}",
                self.device,
                std::io::Error::last_os_error()
            )));
        }
        self.mounted = false;
        Ok(())
    }
}

impl Drop for MountedFilesystem {
    fn drop(&mut self) {
        if let Err(error) = self.unmount() {
            eprintln!("WARNING: {error}");
        }
    }
}

fn flush_boot_block() -> Result<()> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let file = options
        .open(BOOT_DEVICE)
        .map_err(|error| Error(format!("open BOOT for BLKFLSBUF: {error}")))?;
    const BLKFLSBUF: libc::c_ulong = 0x1261;
    if unsafe { libc::ioctl(file.as_raw_fd(), BLKFLSBUF) } != 0 {
        return Err(Error(format!(
            "BLKFLSBUF failed: {}",
            std::io::Error::last_os_error()
        )));
    }
    Ok(())
}

fn open_trusted_directory(path: &Path, expected_mode: u32) -> Result<File> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_DIRECTORY);
    let directory = options.open(path).map_err(|error| {
        Error(format!(
            "open trusted directory {}: {error}",
            path.display()
        ))
    })?;
    let descriptor = directory.metadata().map_err(|error| {
        Error(format!(
            "fstat trusted directory {}: {error}",
            path.display()
        ))
    })?;
    let named = fs::symlink_metadata(path).map_err(|error| {
        Error(format!(
            "stat trusted directory {}: {error}",
            path.display()
        ))
    })?;
    if !descriptor.is_dir()
        || descriptor.uid() != 0
        || descriptor.gid() != 0
        || descriptor.mode() & 0o7777 != expected_mode
        || (descriptor.dev(), descriptor.ino()) != (named.dev(), named.ino())
    {
        return Err(Error(format!(
            "trusted directory identity mismatch: {}",
            path.display()
        )));
    }
    Ok(directory)
}

fn path_present(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(Error(format!("inspect path {}: {error}", path.display()))),
    }
}

fn ensure_no_nested_mounts(path: &Path) -> Result<()> {
    let canonical = fs::canonicalize(path).map_err(|error| {
        Error(format!(
            "resolve mount boundary {}: {error}",
            path.display()
        ))
    })?;
    let prefix = format!("{}/", canonical.display());
    if read_mountinfo()?.iter().any(|record| {
        record.mount_point == canonical.to_string_lossy() || record.mount_point.starts_with(&prefix)
    }) {
        return Err(Error(format!(
            "unexpected mount at or below {}",
            canonical.display()
        )));
    }
    Ok(())
}

fn hash_regular_path(path: &Path, expected_size: u64) -> Result<String> {
    let named = fs::symlink_metadata(path)
        .map_err(|error| Error(format!("stat regular file {}: {error}", path.display())))?;
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut file = options
        .open(path)
        .map_err(|error| Error(format!("open regular file {}: {error}", path.display())))?;
    let descriptor = file
        .metadata()
        .map_err(|error| Error(format!("fstat regular file {}: {error}", path.display())))?;
    if !descriptor.is_file()
        || descriptor.nlink() != 1
        || descriptor.len() != expected_size
        || (descriptor.dev(), descriptor.ino()) != (named.dev(), named.ino())
    {
        return Err(Error(format!(
            "regular file identity mismatch: {}",
            path.display()
        )));
    }
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    let mut total = 0_u64;
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| Error(format!("hash {}: {error}", path.display())))?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| Error("regular file byte count overflow".into()))?;
        if total > expected_size {
            return Err(Error(format!("regular file grew: {}", path.display())));
        }
        digest.update(&buffer[..count]);
    }
    if total != expected_size {
        return Err(Error(format!(
            "regular file short read: expected {expected_size}, got {total}: {}",
            path.display()
        )));
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn freeze_module_package(roms_mount: &Path, destination: &Path) -> Result<()> {
    let payload = roms_mount.join("r46h-v0.10-adc-full-range");
    let payload_metadata = fs::symlink_metadata(&payload)
        .map_err(|error| Error(format!("stat v0.10 payload directory: {error}")))?;
    if !payload_metadata.is_dir() || payload_metadata.file_type().is_symlink() {
        return Err(Error("unsafe v0.10 payload directory".into()));
    }
    let source = payload.join(MODULE_TAR_NAME);
    let source_metadata = fs::symlink_metadata(&source)
        .map_err(|error| Error(format!("stat module package: {error}")))?;
    if !source_metadata.is_file()
        || source_metadata.file_type().is_symlink()
        || source_metadata.nlink() != 1
        || source_metadata.len() != MODULE_TAR_SIZE
    {
        return Err(Error("module package identity or size mismatch".into()));
    }
    let mut source_options = OpenOptions::new();
    source_options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut source_file = source_options
        .open(&source)
        .map_err(|error| Error(format!("open module package: {error}")))?;
    let source_descriptor = source_file
        .metadata()
        .map_err(|error| Error(format!("fstat module package: {error}")))?;
    if (source_descriptor.dev(), source_descriptor.ino())
        != (source_metadata.dev(), source_metadata.ino())
    {
        return Err(Error("module package path identity changed".into()));
    }
    let mut destination_options = OpenOptions::new();
    destination_options
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut destination_file = destination_options
        .open(destination)
        .map_err(|error| Error(format!("create frozen module package: {error}")))?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    let mut total = 0_u64;
    loop {
        check_signal()?;
        let count = source_file
            .read(&mut buffer)
            .map_err(|error| Error(format!("read module package: {error}")))?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| Error("module package byte count overflow".into()))?;
        if total > MODULE_TAR_SIZE {
            return Err(Error("module package grew while freezing".into()));
        }
        digest.update(&buffer[..count]);
        destination_file
            .write_all(&buffer[..count])
            .map_err(|error| Error(format!("write frozen module package: {error}")))?;
    }
    if total != MODULE_TAR_SIZE || format!("{:x}", digest.finalize()) != MODULE_TAR_SHA256 {
        return Err(Error("module package size or SHA-256 mismatch".into()));
    }
    destination_file
        .sync_all()
        .map_err(|error| Error(format!("fsync frozen module package: {error}")))?;
    drop(destination_file);
    if hash_regular_path(destination, MODULE_TAR_SIZE)? != MODULE_TAR_SHA256 {
        return Err(Error("frozen module package SHA-256 mismatch".into()));
    }
    Ok(())
}

fn collect_module_tree(
    root: &Path,
    relative: &Path,
    depth: usize,
    files: &mut BTreeMap<String, String>,
    directories: &mut usize,
) -> Result<()> {
    if depth > 32 || files.len() > 4_096 || *directories > 2_048 {
        return Err(Error("module tree exceeds bounded traversal limits".into()));
    }
    let directory = if relative.as_os_str().is_empty() {
        root.to_path_buf()
    } else {
        root.join(relative)
    };
    let metadata = fs::symlink_metadata(&directory).map_err(|error| {
        Error(format!(
            "stat module directory {}: {error}",
            directory.display()
        ))
    })?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != 0
        || metadata.gid() != 0
        || metadata.mode() & 0o7777 != 0o755
    {
        return Err(Error(format!(
            "unsafe module directory: {}",
            directory.display()
        )));
    }
    *directories += 1;
    let mut entries = fs::read_dir(&directory)
        .map_err(|error| {
            Error(format!(
                "read module directory {}: {error}",
                directory.display()
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|error| Error(format!("enumerate module directory: {error}")))?;
    entries.sort_by(|left, right| {
        left.file_name()
            .as_bytes()
            .cmp(right.file_name().as_bytes())
    });
    for entry in entries {
        let name = entry.file_name();
        let name_bytes = name.as_bytes();
        if name_bytes.is_empty()
            || name_bytes == b"."
            || name_bytes == b".."
            || name_bytes.contains(&b'/')
            || name_bytes.contains(&0)
            || !name_bytes.is_ascii()
        {
            return Err(Error("unsafe module tree name".into()));
        }
        let child_relative = relative.join(&name);
        let child = root.join(&child_relative);
        let child_metadata = fs::symlink_metadata(&child)
            .map_err(|error| Error(format!("stat module entry {}: {error}", child.display())))?;
        if child_metadata.is_dir() && !child_metadata.file_type().is_symlink() {
            collect_module_tree(root, &child_relative, depth + 1, files, directories)?;
            continue;
        }
        if !child_metadata.is_file()
            || child_metadata.file_type().is_symlink()
            || child_metadata.uid() != 0
            || child_metadata.gid() != 0
            || child_metadata.mode() & 0o7777 != 0o644
            || child_metadata.nlink() != 1
        {
            return Err(Error(format!("unsafe module file: {}", child.display())));
        }
        let relative_text = child_relative
            .to_str()
            .ok_or_else(|| Error("non-UTF-8 module path".into()))?
            .to_owned();
        let digest = hash_regular_path(&child, child_metadata.len())?;
        if files.insert(relative_text, digest).is_some() {
            return Err(Error("duplicate module file path".into()));
        }
    }
    Ok(())
}

fn verify_module_tree_at(
    tree: &Path,
    logical_release: &str,
    expected_tree: &str,
    expected_modules: usize,
    expected_files: usize,
) -> Result<()> {
    let mut files = BTreeMap::new();
    let mut directories = 0_usize;
    collect_module_tree(tree, Path::new(""), 0, &mut files, &mut directories)?;
    let module_count = files.keys().filter(|name| name.ends_with(".ko")).count();
    if module_count != expected_modules || files.len() != expected_files {
        return Err(Error(format!(
            "module tree count mismatch: modules={module_count}/{expected_modules} files={}/{expected_files}",
            files.len()
        )));
    }
    let mut tree_digest = Sha256::new();
    for (relative, digest) in files {
        tree_digest.update(
            format!("{digest}  rootfs/lib/modules/{logical_release}/{relative}\n").as_bytes(),
        );
    }
    if format!("{:x}", tree_digest.finalize()) != expected_tree {
        return Err(Error(format!(
            "module tree SHA-256 mismatch: {}",
            tree.display()
        )));
    }
    Ok(())
}

fn verify_fallback_modules() -> Result<()> {
    verify_module_tree_at(
        &Path::new(MODULES_PARENT).join(EXPECTED_RUNNING_RELEASE),
        EXPECTED_RUNNING_RELEASE,
        FALLBACK_MODULE_TREE_SHA256,
        FALLBACK_MODULE_COUNT,
        FALLBACK_MODULE_FILE_COUNT,
    )
}

fn verify_v10_modules(path: &Path) -> Result<()> {
    verify_module_tree_at(
        path,
        TARGET_RELEASE,
        MODULE_TREE_SHA256,
        MODULE_COUNT,
        MODULE_FILE_COUNT,
    )
}

fn verify_receipt_bytes(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| Error(format!("stat module receipt {}: {error}", path.display())))?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.uid() != 0
        || metadata.gid() != 0
        || metadata.mode() & 0o7777 != 0o600
        || metadata.nlink() != 1
        || metadata.len() != MODULE_RECEIPT_BYTES.len() as u64
    {
        return Err(Error(format!("unsafe module receipt: {}", path.display())));
    }
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut file = options
        .open(path)
        .map_err(|error| Error(format!("open module receipt: {error}")))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| Error(format!("read module receipt: {error}")))?;
    if bytes != MODULE_RECEIPT_BYTES {
        return Err(Error("module receipt content mismatch".into()));
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ModuleState {
    Ready,
    Partial,
    ReceiptRecovery,
    Installed,
}

fn module_state() -> Result<ModuleState> {
    let stage = Path::new(MODULES_PARENT).join(MODULE_STAGE_NAME);
    let final_tree = Path::new(MODULES_PARENT).join(TARGET_RELEASE);
    let receipt = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_NAME);
    let receipt_stage = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_STAGE_NAME);
    let stage_present = path_present(&stage)?;
    let final_present = path_present(&final_tree)?;
    let receipt_present = path_present(&receipt)?;
    let receipt_stage_present = path_present(&receipt_stage)?;
    if final_present {
        verify_v10_modules(&final_tree)?;
    }
    if receipt_present {
        verify_receipt_bytes(&receipt)?;
    }
    if receipt_present && !final_present {
        return Err(Error(
            "module receipt exists without v0.10 module tree".into(),
        ));
    }
    if stage_present || receipt_stage_present {
        return Ok(ModuleState::Partial);
    }
    match (final_present, receipt_present) {
        (false, false) => Ok(ModuleState::Ready),
        (true, false) => Ok(ModuleState::ReceiptRecovery),
        (true, true) => Ok(ModuleState::Installed),
        (false, true) => unreachable!(),
    }
}

fn module_state_name(state: ModuleState) -> &'static str {
    match state {
        ModuleState::Ready => "ready",
        ModuleState::Partial => "partial",
        ModuleState::ReceiptRecovery => "receipt-recovery",
        ModuleState::Installed => "installed",
    }
}

fn verify_module_capacity() -> Result<()> {
    let path = CString::new(MODULES_PARENT).unwrap();
    let mut status: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statvfs(path.as_ptr(), &mut status) } != 0 {
        return Err(Error(format!(
            "statvfs modules parent: {}",
            std::io::Error::last_os_error()
        )));
    }
    let available_bytes = u64::from(status.f_bavail)
        .checked_mul(u64::from(status.f_frsize))
        .ok_or_else(|| Error("available byte count overflow".into()))?;
    let required_bytes = MODULE_EXTRACTION_BYTES
        .checked_add(64 * 1024 * 1024)
        .ok_or_else(|| Error("required byte count overflow".into()))?;
    if available_bytes < required_bytes || u64::from(status.f_favail) < 2_048 {
        return Err(Error(
            "insufficient rootfs space or inodes for modules".into(),
        ));
    }
    Ok(())
}

fn validate_removable_module_stage(path: &Path, root_device: u64) -> Result<usize> {
    fn walk(path: &Path, root_device: u64, count: &mut usize, depth: usize) -> Result<()> {
        if depth > 32 || *count > 4_096 {
            return Err(Error(
                "partial module stage exceeds traversal limits".into(),
            ));
        }
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| Error(format!("stat partial module stage: {error}")))?;
        if metadata.dev() != root_device || metadata.uid() != 0 || metadata.gid() != 0 {
            return Err(Error(
                "partial module stage ownership or device mismatch".into(),
            ));
        }
        *count += 1;
        if metadata.is_file() && !metadata.file_type().is_symlink() && metadata.nlink() == 1 {
            return Ok(());
        }
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(Error("partial module stage contains unsafe entry".into()));
        }
        for entry in fs::read_dir(path)
            .map_err(|error| Error(format!("read partial module stage: {error}")))?
        {
            walk(
                &entry
                    .map_err(|error| Error(format!("enumerate partial module stage: {error}")))?
                    .path(),
                root_device,
                count,
                depth + 1,
            )?;
        }
        Ok(())
    }
    let mut count = 0;
    walk(path, root_device, &mut count, 0)?;
    Ok(count)
}

fn recover_module_partial() -> Result<()> {
    let modules_parent = open_trusted_directory(Path::new(MODULES_PARENT), 0o755)?;
    let root_device = modules_parent
        .metadata()
        .map_err(|error| Error(format!("fstat modules parent: {error}")))?
        .dev();
    let stage = Path::new(MODULES_PARENT).join(MODULE_STAGE_NAME);
    if path_present(&stage)? {
        validate_removable_module_stage(&stage, root_device)?;
        fs::remove_dir_all(&stage)
            .map_err(|error| Error(format!("remove partial module stage: {error}")))?;
    }
    let receipt_parent = open_trusted_directory(Path::new(MODULE_RECEIPT_PARENT), 0o755)?;
    let receipt_stage = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_STAGE_NAME);
    if path_present(&receipt_stage)? {
        let metadata = fs::symlink_metadata(&receipt_stage)
            .map_err(|error| Error(format!("stat partial module receipt stage: {error}")))?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.uid() != 0
            || metadata.gid() != 0
            || metadata.mode() & 0o7777 != 0o600
            || metadata.nlink() != 1
            || metadata.len() > 4_096
        {
            return Err(Error("unsafe partial module receipt stage".into()));
        }
        fs::remove_file(&receipt_stage)
            .map_err(|error| Error(format!("remove partial module receipt stage: {error}")))?;
    }
    LinuxDurability.sync_filesystem(&modules_parent)?;
    LinuxDurability.sync_filesystem(&receipt_parent)?;
    Ok(())
}

fn extract_module_tree(package: &Path, stage: &Path) -> Result<()> {
    fs::DirBuilder::new()
        .mode(0o700)
        .create(stage)
        .map_err(|error| Error(format!("create module stage: {error}")))?;
    let archive_member = format!("{MODULE_PACKAGE_NAME}/rootfs/lib/modules/{TARGET_RELEASE}/");
    let status = Command::new("/usr/bin/tar")
        .args([
            "--extract",
            "--gzip",
            "--no-same-owner",
            "--no-overwrite-dir",
            "--restrict",
            "--strip-components=5",
            "--file",
        ])
        .arg(package)
        .arg("--directory")
        .arg(stage)
        .arg(&archive_member)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .status()
        .map_err(|error| Error(format!("run module package extractor: {error}")))?;
    if !status.success() {
        return Err(Error(format!(
            "module package extractor exited {}",
            status.code().unwrap_or(255)
        )));
    }
    fs::set_permissions(stage, fs::Permissions::from_mode(0o755))
        .map_err(|error| Error(format!("set module stage mode: {error}")))?;
    Ok(())
}

fn publish_module_receipt() -> Result<()> {
    let parent = open_trusted_directory(Path::new(MODULE_RECEIPT_PARENT), 0o755)?;
    let receipt = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_NAME);
    let stage = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_STAGE_NAME);
    if path_present(&receipt)? || path_present(&stage)? {
        return Err(Error("module receipt or stage already exists".into()));
    }
    let mut options = OpenOptions::new();
    options
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    let mut file = options
        .open(&stage)
        .map_err(|error| Error(format!("create module receipt stage: {error}")))?;
    file.write_all(MODULE_RECEIPT_BYTES)
        .map_err(|error| Error(format!("write module receipt stage: {error}")))?;
    file.sync_all()
        .map_err(|error| Error(format!("fsync module receipt stage: {error}")))?;
    drop(file);
    verify_receipt_bytes(&stage)?;
    LinuxDurability.rename_noreplace(&parent, MODULE_RECEIPT_STAGE_NAME, MODULE_RECEIPT_NAME)?;
    LinuxDurability.sync_filesystem(&parent)?;
    verify_receipt_bytes(&receipt)?;
    Ok(())
}

struct ModuleStageGuard {
    path: PathBuf,
    published: bool,
}

impl Drop for ModuleStageGuard {
    fn drop(&mut self) {
        if self.published || fs::symlink_metadata(&self.path).is_err() {
            return;
        }
        let parent = match fs::metadata(MODULES_PARENT) {
            Ok(metadata) => metadata,
            Err(error) => {
                eprintln!("WARNING: cannot inspect module stage parent: {error}");
                return;
            }
        };
        if let Err(error) = validate_removable_module_stage(&self.path, parent.dev()) {
            eprintln!("WARNING: preserving unsafe module stage: {error}");
            return;
        }
        if let Err(error) = fs::remove_dir_all(&self.path) {
            eprintln!("WARNING: cannot remove module stage: {error}");
        }
    }
}

struct CompletedReceipt {
    json: String,
    mode: &'static str,
    boot_state: &'static str,
    write_started: bool,
}

fn mode_name(mode: Mode) -> &'static str {
    match mode {
        Mode::Preflight => "preflight",
        Mode::Install => "install",
        Mode::Recover => "recover",
        Mode::ModulesPreflight => "modules-preflight",
        Mode::InstallModules => "install-modules",
        Mode::RecoverModules => "recover-modules",
    }
}

fn perform(
    mode: Mode,
    contract: &Contract,
    signals: &SignalGuard,
    work: &WorkGuard,
) -> Result<CompletedReceipt> {
    verify_geometry()?;
    ensure_unmounted(&[BOOT_DEVICE, ROMS_DEVICE])?;
    let prefix = hash_block(Path::new(WHOLE_DEVICE), PREFIX_SIZE, "prefix")?;
    if prefix != EXPECTED_PREFIX_SHA256 {
        return Err(Error("g92 prefix and MBR SHA-256 mismatch".into()));
    }
    let raw_before = hash_block(Path::new(BOOT_DEVICE), BOOT_SIZE, "boot-before")?;
    check_signal()?;
    {
        let mut roms = MountedFilesystem::mount(ROMS_DEVICE, work.path("roms"), "exfat", false)?;
        freeze_sources(contract, &work.path("roms"), &work.path("source"))?;
        roms.unmount()?;
    }
    ensure_unmounted(&[ROMS_DEVICE])?;
    let state = {
        let mut boot = MountedFilesystem::mount(BOOT_DEVICE, work.path("boot"), "vfat", false)?;
        let state = verify_boot_state(contract, &work.path("boot"))?;
        boot.unmount()?;
        state
    };
    ensure_unmounted(&[BOOT_DEVICE])?;
    match state {
        BootState::Base => {
            if raw_before != EXPECTED_P1_BASE_SHA256 {
                return Err(Error("base BOOT raw SHA-256 mismatch".into()));
            }
            if mode == Mode::Recover {
                return Err(Error("recovery was requested but no journal exists".into()));
            }
        }
        BootState::Installed => {}
        BootState::Partial if mode == Mode::Recover => {}
        BootState::Partial => {
            return Err(Error(
                "partial BOOT state requires --recover-partial".into(),
            ))
        }
    }
    if mode == Mode::Preflight || state == BootState::Installed {
        let boot_state = if state == BootState::Installed {
            "installed"
        } else {
            "base"
        };
        return Ok(CompletedReceipt {
            json: format!(
                "{{\"boot_state\":\"{}\",\"format_version\":1,\"mode\":\"{}\",\"p1_sha256\":\"{}\",\"prefix_sha256\":\"{}\",\"result\":\"pass\",\"tool_id\":\"{}\",\"write_started\":false}}",
                boot_state,
                mode_name(mode),
                raw_before,
                prefix,
                TOOL_ID,
            ),
            mode: mode_name(mode),
            boot_state,
            write_started: false,
        });
    }
    signals.begin_write()?;
    println!("R46H_V10_TARGET stage=write-started active_v08_unchanged=yes");
    {
        let mut boot = MountedFilesystem::mount(BOOT_DEVICE, work.path("boot"), "vfat", true)?;
        install_candidate_files(
            contract,
            &LinuxDurability,
            &work.path("boot"),
            &work.path("source"),
            mode == Mode::Recover,
            None,
        )?;
        boot.unmount()?;
    }
    ensure_unmounted(&[BOOT_DEVICE, ROMS_DEVICE])?;
    flush_boot_block()?;
    let raw_after = hash_block(Path::new(BOOT_DEVICE), BOOT_SIZE, "boot-after")?;
    {
        let mut boot = MountedFilesystem::mount(BOOT_DEVICE, work.path("boot"), "vfat", false)?;
        if verify_boot_state(contract, &work.path("boot"))? != BootState::Installed {
            return Err(Error(
                "post-write read-only BOOT verification failed".into(),
            ));
        }
        boot.unmount()?;
    }
    ensure_unmounted(&[BOOT_DEVICE])?;
    let raw_repeat = hash_block(Path::new(BOOT_DEVICE), BOOT_SIZE, "boot-repeat")?;
    if raw_repeat != raw_after {
        return Err(Error("post-write BOOT raw hash is unstable".into()));
    }
    Ok(CompletedReceipt {
        json: format!(
            "{{\"active_release\":\"{}\",\"active_v08_anchors_unchanged\":true,\"boot_state\":\"installed\",\"candidate_release\":\"{}\",\"format_version\":1,\"mode\":\"{}\",\"old_v09_candidate_removed\":true,\"ordinary_boot_changed\":false,\"p1_sha256_after\":\"{}\",\"p1_sha256_before\":\"{}\",\"prefix_sha256\":\"{}\",\"result\":\"pass\",\"saveenv_used\":false,\"tool_id\":\"{}\",\"write_started\":true}}",
            EXPECTED_RUNNING_RELEASE,
            TARGET_RELEASE,
            mode_name(mode),
            raw_after,
            raw_before,
            prefix,
            TOOL_ID,
        ),
        mode: mode_name(mode),
        boot_state: "installed",
        write_started: true,
    })
}

fn perform_modules(
    mode: Mode,
    contract: &Contract,
    signals: &SignalGuard,
    work: &WorkGuard,
) -> Result<CompletedReceipt> {
    verify_geometry()?;
    ensure_unmounted(&[BOOT_DEVICE, ROMS_DEVICE])?;
    let prefix = hash_block(Path::new(WHOLE_DEVICE), PREFIX_SIZE, "prefix")?;
    if prefix != EXPECTED_PREFIX_SHA256 {
        return Err(Error("g92 prefix and MBR SHA-256 mismatch".into()));
    }
    let p1_before = hash_block(Path::new(BOOT_DEVICE), BOOT_SIZE, "boot-before-modules")?;
    if p1_before != EXPECTED_P1_INSTALLED_SHA256 {
        return Err(Error(
            "installed v0.10-candidate BOOT raw SHA-256 mismatch".into(),
        ));
    }
    {
        let mut boot = MountedFilesystem::mount(BOOT_DEVICE, work.path("boot"), "vfat", false)?;
        if verify_boot_state(contract, &work.path("boot"))? != BootState::Installed {
            return Err(Error(
                "BOOT is not in the exact installed candidate state".into(),
            ));
        }
        boot.unmount()?;
    }
    ensure_unmounted(&[BOOT_DEVICE])?;
    let frozen_package = work.path("source").join(MODULE_TAR_NAME);
    {
        let mut roms = MountedFilesystem::mount(ROMS_DEVICE, work.path("roms"), "exfat", false)?;
        freeze_module_package(&work.path("roms"), &frozen_package)?;
        roms.unmount()?;
    }
    ensure_unmounted(&[ROMS_DEVICE])?;
    open_trusted_directory(Path::new(MODULES_PARENT), 0o755)?;
    open_trusted_directory(Path::new(MODULE_RECEIPT_PARENT), 0o755)?;
    ensure_no_nested_mounts(Path::new(MODULES_PARENT))?;
    ensure_no_nested_mounts(Path::new(MODULE_RECEIPT_PARENT))?;
    verify_fallback_modules()?;
    let initial_state = module_state()?;
    if mode == Mode::ModulesPreflight {
        return Ok(CompletedReceipt {
            json: format!(
                "{{\"active_release\":\"{}\",\"fallback_module_tree_sha256\":\"{}\",\"format_version\":1,\"mode\":\"{}\",\"module_state\":\"{}\",\"p1_sha256\":\"{}\",\"payload_tar_sha256\":\"{}\",\"prefix_sha256\":\"{}\",\"result\":\"pass\",\"tool_id\":\"r46h-v10-module-installer-v0.1\",\"write_started\":false}}",
                EXPECTED_RUNNING_RELEASE,
                FALLBACK_MODULE_TREE_SHA256,
                mode_name(mode),
                module_state_name(initial_state),
                p1_before,
                MODULE_TAR_SHA256,
                prefix,
            ),
            mode: mode_name(mode),
            boot_state: module_state_name(initial_state),
            write_started: false,
        });
    }
    if initial_state == ModuleState::Partial && mode != Mode::RecoverModules {
        return Err(Error(
            "partial module state requires --recover-modules".into(),
        ));
    }
    if initial_state != ModuleState::Partial && mode == Mode::RecoverModules {
        return Err(Error(
            "module recovery was requested without partial state".into(),
        ));
    }
    if initial_state == ModuleState::Installed {
        return Ok(CompletedReceipt {
            json: format!(
                "{{\"active_release\":\"{}\",\"format_version\":1,\"mode\":\"{}\",\"module_state\":\"installed\",\"module_tree_sha256\":\"{}\",\"p1_sha256\":\"{}\",\"payload_tar_sha256\":\"{}\",\"prefix_sha256\":\"{}\",\"result\":\"pass\",\"tool_id\":\"r46h-v10-module-installer-v0.1\",\"write_started\":false}}",
                EXPECTED_RUNNING_RELEASE,
                mode_name(mode),
                MODULE_TREE_SHA256,
                p1_before,
                MODULE_TAR_SHA256,
                prefix,
            ),
            mode: mode_name(mode),
            boot_state: "installed",
            write_started: false,
        });
    }
    verify_module_capacity()?;
    signals.begin_write()?;
    println!("R46H_V10_TARGET stage=module-write-started active_v08_unchanged=yes p3_write=no");
    if initial_state == ModuleState::Partial {
        recover_module_partial()?;
    }
    let state_after_recovery = module_state()?;
    if state_after_recovery == ModuleState::Ready {
        let modules_parent = open_trusted_directory(Path::new(MODULES_PARENT), 0o755)?;
        let stage_path = Path::new(MODULES_PARENT).join(MODULE_STAGE_NAME);
        let mut stage = ModuleStageGuard {
            path: stage_path.clone(),
            published: false,
        };
        extract_module_tree(&frozen_package, &stage_path)?;
        LinuxDurability.sync_filesystem(&modules_parent)?;
        verify_v10_modules(&stage_path)?;
        verify_fallback_modules()?;
        LinuxDurability.rename_noreplace(&modules_parent, MODULE_STAGE_NAME, TARGET_RELEASE)?;
        stage.published = true;
        LinuxDurability.sync_filesystem(&modules_parent)?;
        verify_v10_modules(&Path::new(MODULES_PARENT).join(TARGET_RELEASE))?;
    } else if state_after_recovery != ModuleState::ReceiptRecovery {
        return Err(Error(format!(
            "unexpected module state after recovery: {}",
            module_state_name(state_after_recovery)
        )));
    }
    verify_v10_modules(&Path::new(MODULES_PARENT).join(TARGET_RELEASE))?;
    verify_fallback_modules()?;
    verify_production_identity()?;
    let p1_after = hash_block(Path::new(BOOT_DEVICE), BOOT_SIZE, "boot-after-modules")?;
    if p1_after != p1_before {
        return Err(Error("BOOT changed during module-only transaction".into()));
    }
    let receipt = Path::new(MODULE_RECEIPT_PARENT).join(MODULE_RECEIPT_NAME);
    if !path_present(&receipt)? {
        publish_module_receipt()?;
    }
    verify_receipt_bytes(&receipt)?;
    let receipt_sha256 = format!("{:x}", Sha256::digest(MODULE_RECEIPT_BYTES));
    Ok(CompletedReceipt {
        json: format!(
            "{{\"active_release\":\"{}\",\"fallback_module_tree_sha256\":\"{}\",\"format_version\":1,\"mode\":\"{}\",\"module_receipt_sha256\":\"{}\",\"module_state\":\"installed\",\"module_tree_sha256\":\"{}\",\"p1_sha256_after\":\"{}\",\"p1_sha256_before\":\"{}\",\"payload_tar_sha256\":\"{}\",\"prefix_sha256\":\"{}\",\"result\":\"pass\",\"target_release\":\"{}\",\"tool_id\":\"r46h-v10-module-installer-v0.1\",\"write_started\":true}}",
            EXPECTED_RUNNING_RELEASE,
            FALLBACK_MODULE_TREE_SHA256,
            mode_name(mode),
            receipt_sha256,
            MODULE_TREE_SHA256,
            p1_after,
            p1_before,
            MODULE_TAR_SHA256,
            prefix,
            TARGET_RELEASE,
        ),
        mode: mode_name(mode),
        boot_state: "installed",
        write_started: true,
    })
}

pub fn run() -> Result<()> {
    let mode = parse_arguments()?;
    verify_production_identity()?;
    let mut lock = LockGuard::acquire()?;
    let signals = SignalGuard::install()?;
    let contract = production_contract();
    if format!("{:x}", Sha256::digest(JOURNAL_BYTES)) != contract.journal.sha256
        || JOURNAL_BYTES.len() as u64 != contract.journal.size
    {
        return Err(Error("compiled journal identity mismatch".into()));
    }
    let mut work = WorkGuard::create()?;
    let operation = match mode {
        Mode::ModulesPreflight | Mode::InstallModules | Mode::RecoverModules => {
            perform_modules(mode, &contract, &signals, &work)
        }
        Mode::Preflight | Mode::Install | Mode::Recover => {
            perform(mode, &contract, &signals, &work)
        }
    };
    let cleanup = work.cleanup(&contract);
    let lock_cleanup = lock.finish();
    let receipt = match (operation, cleanup, lock_cleanup) {
        (Ok(receipt), Ok(()), Ok(())) => receipt,
        (Ok(_), Err(cleanup), Ok(())) => return Err(cleanup),
        (Ok(_), Ok(()), Err(lock_cleanup)) => return Err(lock_cleanup),
        (Ok(_), Err(cleanup), Err(lock_cleanup)) => {
            return Err(Error(format!(
                "{cleanup}; lock cleanup also failed: {lock_cleanup}"
            )))
        }
        (Err(operation), Ok(()), Ok(())) => return Err(operation),
        (Err(operation), Err(cleanup), Ok(())) => {
            return Err(Error(format!(
                "{operation}; private cleanup also failed: {cleanup}"
            )))
        }
        (Err(operation), Ok(()), Err(lock_cleanup)) => {
            return Err(Error(format!(
                "{operation}; lock cleanup also failed: {lock_cleanup}"
            )))
        }
        (Err(operation), Err(cleanup), Err(lock_cleanup)) => {
            return Err(Error(format!(
            "{operation}; private cleanup failed: {cleanup}; lock cleanup failed: {lock_cleanup}"
        )))
        }
    };
    let receipt_digest = format!("{:x}", Sha256::digest(format!("{}\n", receipt.json)));
    println!("R46H_V10_TARGET_RECEIPT {}", receipt.json);
    println!("R46H_V10_TARGET_RECEIPT_SHA256={receipt_digest}");
    println!(
        "R46H_V10_TARGET result=pass mode={} boot_state={} write_started={} active_v08_unchanged=yes",
        receipt.mode, receipt.boot_state, receipt.write_started,
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering as TestOrdering};

    const SIGNAL_TEST_ENV: &str = "R46H_V10_SIGNAL_TEST_MODE";
    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn create(label: &str) -> Self {
            let parent = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../out/.cache/r46h-v10-target-installer/tests");
            fs::create_dir_all(&parent).unwrap();
            let counter = TEST_COUNTER.fetch_add(1, TestOrdering::SeqCst);
            let path = parent.join(format!("linux-{label}-{}-{counter}", std::process::id()));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    fn write_test_file(path: &Path, bytes: &[u8], mode: u32) {
        fs::write(path, bytes).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
    }

    #[test]
    fn signal_contract_cancels_before_commit_and_completes_after_commit() {
        if let Ok(mode) = std::env::var(SIGNAL_TEST_ENV) {
            STOP_SIGNAL.store(0, Ordering::SeqCst);
            let guard = SignalGuard::install().unwrap();
            match mode.as_str() {
                "before" => {
                    assert_eq!(unsafe { libc::raise(libc::SIGTERM) }, 0);
                    assert!(check_signal().unwrap_err().0.contains("signal 15"));
                    assert!(guard.begin_write().unwrap_err().0.contains("signal 15"));
                }
                "after" => {
                    guard.begin_write().unwrap();
                    assert_eq!(unsafe { libc::raise(libc::SIGTERM) }, 0);
                    assert_eq!(STOP_SIGNAL.load(Ordering::SeqCst), 0);
                }
                _ => panic!("unknown signal test mode"),
            }
            return;
        }
        let executable = std::env::current_exe().unwrap();
        for mode in ["before", "after"] {
            let result = Command::new(&executable)
                .args([
                    "--exact",
                    "linux::tests::signal_contract_cancels_before_commit_and_completes_after_commit",
                    "--nocapture",
                ])
                .env(SIGNAL_TEST_ENV, mode)
                .status()
                .unwrap();
            assert!(result.success(), "signal child failed in {mode} mode");
        }
    }

    #[test]
    fn production_contract_has_exact_journal_and_boot_last() {
        let contract = production_contract();
        assert_eq!(contract.journal.size, JOURNAL_BYTES.len() as u64);
        assert_eq!(
            contract.journal.sha256,
            format!("{:x}", Sha256::digest(JOURNAL_BYTES))
        );
        assert_eq!(
            contract.final_files().map(|spec| spec.name),
            [
                "Image.mainline-v0.10-adc-full-range.gz",
                "rk3326-r46h-mainline-v0.10-adc-full-range.dtb",
                "boot.ini.v0.10-adc-full-range",
            ]
        );
        assert!(contract
            .stable_top_level
            .contains("boot.ini.v0.8-bootloader-handoff"));
        assert!(!contract
            .stable_top_level
            .contains("boot.ini.v0.9-adc-joystick-fix"));
        assert!(!contract.stable_top_level.contains(".fseventsd"));
        assert_eq!(
            contract.stable_directories,
            ["consoles", "System Volume Information", ".Spotlight-V100"]
                .into_iter()
                .collect()
        );
        assert!(contract
            .stable_directories
            .is_subset(&contract.stable_top_level));
        assert_eq!(
            contract.anchors[0].sha256,
            "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb"
        );
        assert_eq!(contract.anchors[0].sha256, contract.anchors[1].sha256);
    }

    #[test]
    fn storage_fault_gate_is_specific_and_case_normalized_by_caller() {
        assert_eq!(storage_fault_marker("mmc0: error -84"), Some("mmc0: error"));
        assert_eq!(
            storage_fault_marker("buffer i/o error on dev mmcblk0p2"),
            Some("buffer i/o error")
        );
        assert_eq!(
            storage_fault_marker("mmc0: new ultra high speed sdr104"),
            None
        );
    }

    #[test]
    fn procfs_text_ignores_zero_metadata_length_but_remains_bounded() {
        let path = Path::new("/proc/sys/kernel/osrelease");
        assert_eq!(fs::metadata(path).unwrap().len(), 0);
        let observed = read_pseudo_regular(path, 256).unwrap();
        assert!(!observed.is_empty());
        assert!(read_pseudo_regular(path, 1).is_err());
    }

    #[test]
    fn root_mount_identity_does_not_depend_on_dev_root_source_text() {
        let record = MountRecord {
            major: 179,
            minor: 2,
            mount_point: "/".into(),
            options: ["rw".into(), "noatime".into()].into_iter().collect(),
            filesystem: "ext4".into(),
        };
        assert!(mount_matches_block(&record, (179, 2), "ext4"));
        assert!(!mount_matches_block(&record, (179, 3), "ext4"));
    }

    #[test]
    fn module_tree_hash_binds_paths_bytes_counts_and_modes() {
        let fixture = TestDirectory::create("module-tree");
        let tree = fixture.0.join("tree");
        fs::create_dir(&tree).unwrap();
        fs::set_permissions(&tree, fs::Permissions::from_mode(0o755)).unwrap();
        fs::create_dir(tree.join("kernel")).unwrap();
        fs::set_permissions(tree.join("kernel"), fs::Permissions::from_mode(0o755)).unwrap();
        write_test_file(&tree.join("kernel/test.ko"), b"module\n", 0o644);
        write_test_file(&tree.join("modules.dep"), b"kernel/test.ko:\n", 0o644);
        let module = format!("{:x}", Sha256::digest(b"module\n"));
        let metadata = format!("{:x}", Sha256::digest(b"kernel/test.ko:\n"));
        let expected = format!(
            "{:x}",
            Sha256::digest(format!(
                "{module}  rootfs/lib/modules/test-release/kernel/test.ko\n\
                 {metadata}  rootfs/lib/modules/test-release/modules.dep\n"
            ))
        );
        verify_module_tree_at(&tree, "test-release", &expected, 1, 2).unwrap();
        write_test_file(&tree.join("modules.dep"), b"tampered\n", 0o644);
        assert!(verify_module_tree_at(&tree, "test-release", &expected, 1, 2).is_err());
        write_test_file(&tree.join("modules.dep"), b"kernel/test.ko:\n", 0o600);
        assert!(verify_module_tree_at(&tree, "test-release", &expected, 1, 2).is_err());
    }

    #[test]
    fn gnu_tar_extracts_only_the_exact_module_subtree() {
        let fixture = TestDirectory::create("tar-extract");
        let source = fixture
            .0
            .join(MODULE_PACKAGE_NAME)
            .join("rootfs/lib/modules")
            .join(TARGET_RELEASE);
        fs::create_dir_all(source.join("kernel")).unwrap();
        write_test_file(&source.join("kernel/test.ko"), b"module\n", 0o644);
        let archive = fixture.0.join("package.tar.gz");
        let status = Command::new("/usr/bin/tar")
            .args(["--create", "--gzip", "--file"])
            .arg(&archive)
            .arg("--directory")
            .arg(&fixture.0)
            .arg(MODULE_PACKAGE_NAME)
            .status()
            .unwrap();
        assert!(status.success());
        let stage = fixture.0.join("stage");
        extract_module_tree(&archive, &stage).unwrap();
        assert_eq!(fs::read(stage.join("kernel/test.ko")).unwrap(), b"module\n");
        assert!(!stage.join(MODULE_PACKAGE_NAME).exists());
        assert_eq!(fs::metadata(stage).unwrap().mode() & 0o7777, 0o755);
    }

    #[test]
    fn canonical_runtime_package_extracts_to_the_pinned_tree() {
        let Ok(package) = std::env::var("R46H_V10_MODULE_PACKAGE") else {
            return;
        };
        let package = PathBuf::from(package);
        assert_eq!(
            hash_regular_path(&package, MODULE_TAR_SIZE).unwrap(),
            MODULE_TAR_SHA256
        );
        let fixture = TestDirectory::create("canonical-package");
        let stage = fixture.0.join("stage");
        extract_module_tree(&package, &stage).unwrap();
        verify_v10_modules(&stage).unwrap();
    }

    #[test]
    fn module_receipt_is_fixed_and_self_consistent() {
        let text = std::str::from_utf8(MODULE_RECEIPT_BYTES).unwrap();
        assert_eq!(text.lines().count(), 11);
        assert!(text.contains(&format!("installed_release={TARGET_RELEASE}\n")));
        assert!(text.contains(&format!("payload_tar_sha256={MODULE_TAR_SHA256}\n")));
        assert!(text.contains(&format!("module_tree_sha256={MODULE_TREE_SHA256}\n")));
        assert!(text.contains(&format!("p1_sha256={EXPECTED_P1_INSTALLED_SHA256}\n")));
    }

    #[test]
    fn work_cleanup_rejects_unknown_children_without_recursive_delete() {
        let contract = production_contract();
        let mut work = WorkGuard::create().unwrap();
        let unexpected = work.path("source").join("unexpected");
        fs::write(&unexpected, b"do-not-delete-through-recursion\n").unwrap();
        let error = work.cleanup(&contract).unwrap_err();
        assert!(error.0.contains("remove private source directory"));
        assert!(unexpected.exists());
        fs::remove_file(unexpected).unwrap();
        work.cleanup(&contract).unwrap();
    }
}
