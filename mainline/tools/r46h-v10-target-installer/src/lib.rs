//! Directory transaction used by the R46H v0.10 target installer.
//!
//! The production binary supplies a Linux durability implementation and exact
//! board/card constants. Tests use only private directories on the host.

use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::ffi::CString;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

const COPY_BUFFER_SIZE: usize = 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

fn io_error(context: &str, error: std::io::Error) -> Error {
    Error(format!("{context}: {error}"))
}

#[derive(Clone, Debug)]
pub struct FileSpec {
    pub name: &'static str,
    pub size: u64,
    pub sha256: &'static str,
}

#[derive(Clone, Debug)]
pub struct Contract {
    pub payload_name: &'static str,
    pub payload_manifest: FileSpec,
    pub payload_complete: FileSpec,
    pub source_image: FileSpec,
    pub source_dtb: FileSpec,
    pub source_boot: FileSpec,
    pub final_boot: FileSpec,
    pub boot_fallback_old: &'static [u8],
    pub boot_fallback_new: &'static [u8],
    pub old_files: Vec<FileSpec>,
    pub anchors: Vec<FileSpec>,
    pub stable_top_level: BTreeSet<&'static str>,
    pub stable_directories: BTreeSet<&'static str>,
    pub stage_suffix: &'static str,
    pub journal: FileSpec,
    pub journal_bytes: &'static [u8],
    pub minimum_free_bytes: u64,
    pub source_date_epoch: i64,
}

impl Contract {
    pub fn final_files(&self) -> [&FileSpec; 3] {
        [&self.source_image, &self.source_dtb, &self.final_boot]
    }

    pub fn stage_name(&self, spec: &FileSpec) -> String {
        format!(".{}{}", spec.name, self.stage_suffix)
    }

    pub fn base_names(&self) -> BTreeSet<&str> {
        self.stable_top_level
            .iter()
            .copied()
            .chain(self.old_files.iter().map(|spec| spec.name))
            .collect()
    }

    pub fn installed_names(&self) -> BTreeSet<&str> {
        self.stable_top_level
            .iter()
            .copied()
            .chain(self.final_files().into_iter().map(|spec| spec.name))
            .collect()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootState {
    Base,
    Installed,
    Partial,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FaultPoint {
    AfterOldRemoved,
    AfterImage,
    AfterDtb,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct InstallOutcome {
    pub changed: bool,
    pub recovered: bool,
}

pub trait DurableFilesystem {
    fn sync_filesystem(&self, directory: &File) -> Result<()>;
    fn set_timestamp(&self, directory: &File, name: &str, epoch: i64) -> Result<()>;
    fn rename_noreplace(&self, directory: &File, source: &str, destination: &str) -> Result<()>;
}

pub struct LinuxDurability;

impl DurableFilesystem for LinuxDurability {
    fn sync_filesystem(&self, directory: &File) -> Result<()> {
        #[cfg(target_os = "linux")]
        {
            unsafe extern "C" {
                fn syncfs(descriptor: libc::c_int) -> libc::c_int;
            }
            let result = unsafe { syncfs(directory.as_raw_fd()) };
            if result != 0 {
                return Err(io_error("syncfs", std::io::Error::last_os_error()));
            }
            Ok(())
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = directory;
            Err(Error(
                "syncfs is available only in the Linux production build".into(),
            ))
        }
    }

    fn set_timestamp(&self, directory: &File, name: &str, epoch: i64) -> Result<()> {
        let name = CString::new(name.as_bytes()).map_err(|_| Error("NUL in file name".into()))?;
        let times = [
            libc::timespec {
                tv_sec: epoch,
                tv_nsec: 0,
            },
            libc::timespec {
                tv_sec: epoch,
                tv_nsec: 0,
            },
        ];
        let result = unsafe {
            libc::utimensat(
                directory.as_raw_fd(),
                name.as_ptr(),
                times.as_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if result != 0 {
            return Err(io_error("utimensat", std::io::Error::last_os_error()));
        }
        Ok(())
    }

    fn rename_noreplace(&self, directory: &File, source: &str, destination: &str) -> Result<()> {
        #[cfg(target_os = "linux")]
        {
            let source = CString::new(source.as_bytes())
                .map_err(|_| Error("NUL in source file name".into()))?;
            let destination = CString::new(destination.as_bytes())
                .map_err(|_| Error("NUL in destination file name".into()))?;
            let result = unsafe {
                libc::syscall(
                    libc::SYS_renameat2,
                    directory.as_raw_fd(),
                    source.as_ptr(),
                    directory.as_raw_fd(),
                    destination.as_ptr(),
                    libc::RENAME_NOREPLACE,
                )
            };
            if result != 0 {
                return Err(io_error(
                    "renameat2(RENAME_NOREPLACE)",
                    std::io::Error::last_os_error(),
                ));
            }
            Ok(())
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = (directory, source, destination);
            Err(Error(
                "renameat2 is available only in the Linux production build".into(),
            ))
        }
    }
}

fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 128
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.as_bytes().contains(&0)
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b' ' | b'.' | b'_' | b'-'))
}

fn open_directory(path: &Path) -> Result<File> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_DIRECTORY);
    let directory = options
        .open(path)
        .map_err(|error| io_error(&format!("open directory {}", path.display()), error))?;
    if !directory
        .metadata()
        .map_err(|error| io_error("fstat directory", error))?
        .is_dir()
    {
        return Err(Error(format!("not a directory: {}", path.display())));
    }
    Ok(directory)
}

fn try_open_file_at(directory: &File, name: &str, flags: i32, mode: u32) -> Result<Option<File>> {
    if !valid_name(name) {
        return Err(Error(format!("unsafe file name: {name:?}")));
    }
    let name = CString::new(name.as_bytes()).map_err(|_| Error("NUL in file name".into()))?;
    let descriptor = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            mode,
        )
    };
    if descriptor < 0 {
        let error = std::io::Error::last_os_error();
        if error.kind() == std::io::ErrorKind::NotFound {
            return Ok(None);
        }
        return Err(io_error(
            &format!("openat {}", name.to_string_lossy()),
            error,
        ));
    }
    Ok(Some(unsafe { File::from_raw_fd(descriptor) }))
}

fn open_file_at(directory: &File, name: &str, flags: i32, mode: u32) -> Result<File> {
    try_open_file_at(directory, name, flags, mode)?
        .ok_or_else(|| Error(format!("required file is absent: {name}")))
}

fn hash_reader(reader: &mut File, expected_size: u64) -> Result<String> {
    reader
        .seek(SeekFrom::Start(0))
        .map_err(|error| io_error("seek before SHA-256", error))?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; COPY_BUFFER_SIZE];
    let mut total = 0_u64;
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| io_error("read for SHA-256", error))?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| Error("SHA-256 byte count overflow".into()))?;
        if total > expected_size {
            return Err(Error("file grew while hashing".into()));
        }
        digest.update(&buffer[..count]);
    }
    if total != expected_size {
        return Err(Error(format!(
            "SHA-256 size mismatch: expected {expected_size}, read {total}"
        )));
    }
    reader
        .seek(SeekFrom::Start(0))
        .map_err(|error| io_error("seek after SHA-256", error))?;
    Ok(format!("{:x}", digest.finalize()))
}

fn verify_named_file_at(directory: &File, name: &str, size: u64, sha256: &str) -> Result<()> {
    let mut file = open_file_at(directory, name, libc::O_RDONLY, 0)?;
    let metadata = file
        .metadata()
        .map_err(|error| io_error("fstat verified file", error))?;
    if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() != size {
        return Err(Error(format!("unsafe or mismatched file identity: {name}")));
    }
    let digest = hash_reader(&mut file, size)?;
    if digest != sha256 {
        return Err(Error(format!("SHA-256 mismatch: {name}")));
    }
    Ok(())
}

pub fn verify_file_at(directory: &File, spec: &FileSpec) -> Result<()> {
    verify_named_file_at(directory, spec.name, spec.size, spec.sha256)
}

fn read_exact_at(directory: &File, spec: &FileSpec) -> Result<Vec<u8>> {
    verify_file_at(directory, spec)?;
    let mut file = open_file_at(directory, spec.name, libc::O_RDONLY, 0)?;
    let size = usize::try_from(spec.size).map_err(|_| Error("file is too large".into()))?;
    let mut bytes = vec![0_u8; size];
    file.read_exact(&mut bytes)
        .map_err(|error| io_error(&format!("read {}", spec.name), error))?;
    let mut trailing = [0_u8; 1];
    if file
        .read(&mut trailing)
        .map_err(|error| io_error("read trailing byte", error))?
        != 0
    {
        return Err(Error(format!("file grew while reading: {}", spec.name)));
    }
    Ok(bytes)
}

fn write_exclusive_at(directory: &File, name: &str, bytes: &[u8]) -> Result<()> {
    let mut file = open_file_at(
        directory,
        name,
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
        0o600,
    )?;
    file.write_all(bytes)
        .map_err(|error| io_error(&format!("write {name}"), error))?;
    file.sync_all()
        .map_err(|error| io_error(&format!("fsync {name}"), error))?;
    Ok(())
}

fn copy_exclusive_at(
    source_directory: &File,
    source: &FileSpec,
    destination_directory: &File,
    destination_name: &str,
) -> Result<()> {
    verify_file_at(source_directory, source)?;
    let mut input = open_file_at(source_directory, source.name, libc::O_RDONLY, 0)?;
    let mut output = open_file_at(
        destination_directory,
        destination_name,
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
        0o600,
    )?;
    let mut remaining = source.size;
    let mut buffer = vec![0_u8; COPY_BUFFER_SIZE];
    while remaining != 0 {
        let desired = usize::try_from(remaining.min(COPY_BUFFER_SIZE as u64))
            .map_err(|_| Error("copy length overflow".into()))?;
        let count = input
            .read(&mut buffer[..desired])
            .map_err(|error| io_error(&format!("read {}", source.name), error))?;
        if count == 0 {
            return Err(Error(format!("source became short: {}", source.name)));
        }
        output
            .write_all(&buffer[..count])
            .map_err(|error| io_error(&format!("write {destination_name}"), error))?;
        remaining -= count as u64;
    }
    let mut trailing = [0_u8; 1];
    if input
        .read(&mut trailing)
        .map_err(|error| io_error("read trailing source byte", error))?
        != 0
    {
        return Err(Error(format!("source grew while copying: {}", source.name)));
    }
    output
        .sync_all()
        .map_err(|error| io_error(&format!("fsync {destination_name}"), error))?;
    Ok(())
}

fn child_exists_regular(directory: &File, name: &str) -> Result<bool> {
    match try_open_file_at(directory, name, libc::O_RDONLY | libc::O_NONBLOCK, 0)? {
        Some(file) => {
            let metadata = file
                .metadata()
                .map_err(|error| io_error("fstat transient", error))?;
            if !metadata.is_file() || metadata.nlink() != 1 {
                return Err(Error(format!("unsafe known transient path: {name}")));
            }
            Ok(true)
        }
        None => Ok(false),
    }
}

fn child_exists_directory(directory: &File, name: &str) -> Result<bool> {
    match try_open_file_at(directory, name, libc::O_RDONLY | libc::O_DIRECTORY, 0)? {
        Some(child) => {
            if !child
                .metadata()
                .map_err(|error| io_error("fstat stable directory", error))?
                .is_dir()
            {
                return Err(Error(format!("unsafe stable directory path: {name}")));
            }
            Ok(true)
        }
        None => Ok(false),
    }
}

fn unlink_at(directory: &File, name: &str) -> Result<()> {
    let name = CString::new(name.as_bytes()).map_err(|_| Error("NUL in unlink name".into()))?;
    if unsafe { libc::unlinkat(directory.as_raw_fd(), name.as_ptr(), 0) } != 0 {
        return Err(io_error("unlinkat", std::io::Error::last_os_error()));
    }
    Ok(())
}

fn list_names(path: &Path) -> Result<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    for entry in fs::read_dir(path)
        .map_err(|error| io_error(&format!("read directory {}", path.display()), error))?
    {
        let entry = entry.map_err(|error| io_error("read directory entry", error))?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| Error("non-UTF-8 directory entry".into()))?;
        if !valid_name(&name) || !names.insert(name.clone()) {
            return Err(Error(format!(
                "unsafe or duplicate directory entry: {name:?}"
            )));
        }
    }
    Ok(names)
}

fn contains_name(names: &BTreeSet<String>, name: &str) -> bool {
    names.get(name).is_some()
}

pub fn freeze_sources(contract: &Contract, roms_mount: &Path, stage: &Path) -> Result<()> {
    let payload_path = roms_mount.join(contract.payload_name);
    let payload = open_directory(&payload_path)?;
    let stage_directory = open_directory(stage)?;
    verify_file_at(&payload, &contract.payload_manifest)?;
    verify_file_at(&payload, &contract.payload_complete)?;
    copy_exclusive_at(
        &payload,
        &contract.source_image,
        &stage_directory,
        contract.source_image.name,
    )?;
    copy_exclusive_at(
        &payload,
        &contract.source_dtb,
        &stage_directory,
        contract.source_dtb.name,
    )?;
    let source_boot = read_exact_at(&payload, &contract.source_boot)?;
    if source_boot
        .windows(contract.boot_fallback_old.len())
        .filter(|window| *window == contract.boot_fallback_old)
        .count()
        != 1
        || source_boot
            .windows(contract.boot_fallback_new.len())
            .any(|window| window == contract.boot_fallback_new)
    {
        return Err(Error("v0.10 source boot fallback marker mismatch".into()));
    }
    let marker = source_boot
        .windows(contract.boot_fallback_old.len())
        .position(|window| window == contract.boot_fallback_old)
        .ok_or_else(|| Error("missing source boot fallback marker".into()))?;
    let mut rendered = Vec::with_capacity(
        source_boot.len() + contract.boot_fallback_new.len() - contract.boot_fallback_old.len(),
    );
    rendered.extend_from_slice(&source_boot[..marker]);
    rendered.extend_from_slice(contract.boot_fallback_new);
    rendered.extend_from_slice(&source_boot[marker + contract.boot_fallback_old.len()..]);
    if rendered.len() as u64 != contract.final_boot.size
        || format!("{:x}", Sha256::digest(&rendered)) != contract.final_boot.sha256
    {
        return Err(Error(
            "rendered one-shot boot script identity mismatch".into(),
        ));
    }
    write_exclusive_at(&stage_directory, contract.final_boot.name, &rendered)?;
    for spec in contract.final_files() {
        verify_file_at(&stage_directory, spec)?;
    }
    Ok(())
}

pub fn verify_boot_state(contract: &Contract, boot: &Path) -> Result<BootState> {
    let directory = open_directory(boot)?;
    let names = list_names(boot)?;
    if !contract
        .stable_directories
        .is_subset(&contract.stable_top_level)
    {
        return Err(Error(
            "stable BOOT directory contract is not a top-level subset".into(),
        ));
    }
    let mut allowed: BTreeSet<&str> = contract
        .stable_top_level
        .iter()
        .copied()
        .chain(contract.old_files.iter().map(|spec| spec.name))
        .chain(contract.final_files().into_iter().map(|spec| spec.name))
        .chain(std::iter::once(contract.journal.name))
        .collect();
    let stage_names: Vec<String> = contract
        .final_files()
        .into_iter()
        .map(|spec| contract.stage_name(spec))
        .collect();
    for name in &stage_names {
        allowed.insert(name);
    }
    let missing: Vec<&str> = contract
        .stable_top_level
        .iter()
        .copied()
        .filter(|name| !contains_name(&names, name))
        .collect();
    let extra: Vec<&str> = names
        .iter()
        .map(String::as_str)
        .filter(|name| !allowed.contains(name))
        .collect();
    if !missing.is_empty() || !extra.is_empty() {
        return Err(Error(format!(
            "BOOT top-level identity mismatch: missing={missing:?} extra={extra:?}"
        )));
    }
    for name in &contract.stable_top_level {
        if contract.stable_directories.contains(name) {
            if !child_exists_directory(&directory, name)? {
                return Err(Error(format!(
                    "required stable directory is absent: {name}"
                )));
            }
        } else if !child_exists_regular(&directory, name)? {
            return Err(Error(format!("required stable file is absent: {name}")));
        }
    }
    for spec in &contract.anchors {
        verify_file_at(&directory, spec)?;
    }
    let mut old_count = 0;
    for spec in &contract.old_files {
        if contains_name(&names, spec.name) {
            verify_file_at(&directory, spec)?;
            old_count += 1;
        }
    }
    let mut new_count = 0;
    for spec in contract.final_files() {
        if contains_name(&names, spec.name) {
            verify_file_at(&directory, spec)?;
            new_count += 1;
        }
    }
    let journal_present = contains_name(&names, contract.journal.name);
    let mut transient_count = usize::from(journal_present);
    if journal_present {
        verify_file_at(&directory, &contract.journal)?;
    }
    for name in &stage_names {
        if contains_name(&names, name) {
            child_exists_regular(&directory, name)?;
            transient_count += 1;
        }
    }
    let borrowed_names: BTreeSet<&str> = names.iter().map(String::as_str).collect();
    if borrowed_names == contract.base_names()
        && old_count == contract.old_files.len()
        && new_count == 0
        && transient_count == 0
    {
        return Ok(BootState::Base);
    }
    if borrowed_names == contract.installed_names()
        && old_count == 0
        && new_count == 3
        && transient_count == 0
    {
        return Ok(BootState::Installed);
    }
    if journal_present {
        return Ok(BootState::Partial);
    }
    Err(Error(
        "BOOT candidate state is neither base, installed, nor recoverable partial".into(),
    ))
}

fn available_bytes(directory: &File) -> Result<u64> {
    let mut value = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::fstatvfs(directory.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(io_error("fstatvfs", std::io::Error::last_os_error()));
    }
    let value = unsafe { value.assume_init() };
    #[cfg(target_os = "macos")]
    let available_blocks = u64::from(value.f_bavail);
    #[cfg(target_os = "linux")]
    let available_blocks = value.f_bavail;
    available_blocks
        .checked_mul(value.f_frsize)
        .ok_or_else(|| Error("available-byte count overflow".into()))
}

fn required_publication_bytes(contract: &Contract, names: &BTreeSet<String>) -> Result<u64> {
    contract
        .final_files()
        .into_iter()
        .filter(|spec| !contains_name(names, spec.name))
        .try_fold(contract.minimum_free_bytes, |total, spec| {
            total.checked_add(spec.size)
        })
        .ok_or_else(|| Error("required free-space count overflow".into()))
}

pub fn install_candidate_files(
    contract: &Contract,
    durable: &dyn DurableFilesystem,
    boot: &Path,
    stage: &Path,
    recovery: bool,
    fault: Option<FaultPoint>,
) -> Result<InstallOutcome> {
    let state = verify_boot_state(contract, boot)?;
    if state == BootState::Installed {
        return Ok(InstallOutcome {
            changed: false,
            recovered: false,
        });
    }
    if recovery && state != BootState::Partial {
        return Err(Error(
            "recovery requires the exact in-progress journal state".into(),
        ));
    }
    if !recovery && state != BootState::Base {
        return Err(Error(
            "normal install requires the exact base BOOT state".into(),
        ));
    }
    let boot_directory = open_directory(boot)?;
    let stage_directory = open_directory(stage)?;
    for spec in contract.final_files() {
        verify_file_at(&stage_directory, spec)?;
    }
    if state == BootState::Base {
        write_exclusive_at(
            &boot_directory,
            contract.journal.name,
            contract.journal_bytes,
        )?;
        durable.sync_filesystem(&boot_directory)?;
    } else {
        verify_file_at(&boot_directory, &contract.journal)?;
    }
    for spec in contract.final_files() {
        let stage_name = contract.stage_name(spec);
        if child_exists_regular(&boot_directory, &stage_name)? {
            unlink_at(&boot_directory, &stage_name)?;
        }
    }
    durable.sync_filesystem(&boot_directory)?;
    let names = list_names(boot)?;
    for spec in &contract.old_files {
        if contains_name(&names, spec.name) {
            verify_file_at(&boot_directory, spec)?;
            unlink_at(&boot_directory, spec.name)?;
            durable.sync_filesystem(&boot_directory)?;
        }
    }
    if fault == Some(FaultPoint::AfterOldRemoved) {
        return Err(Error("injected failure after old candidate removal".into()));
    }
    let names = list_names(boot)?;
    let required = required_publication_bytes(contract, &names)?;
    let available = available_bytes(&boot_directory)?;
    if available < required {
        return Err(Error(format!(
            "BOOT free space is too small: required={required} available={available}"
        )));
    }
    for (index, spec) in contract.final_files().into_iter().enumerate() {
        if contains_name(&list_names(boot)?, spec.name) {
            verify_file_at(&boot_directory, spec)?;
            continue;
        }
        let temporary = contract.stage_name(spec);
        copy_exclusive_at(&stage_directory, spec, &boot_directory, &temporary)?;
        verify_named_file_at(&boot_directory, &temporary, spec.size, spec.sha256)?;
        durable.set_timestamp(&boot_directory, &temporary, contract.source_date_epoch)?;
        durable.sync_filesystem(&boot_directory)?;
        durable.rename_noreplace(&boot_directory, &temporary, spec.name)?;
        durable.sync_filesystem(&boot_directory)?;
        verify_file_at(&boot_directory, spec)?;
        if fault == Some(FaultPoint::AfterImage) && index == 0 {
            return Err(Error("injected failure after image publication".into()));
        }
        if fault == Some(FaultPoint::AfterDtb) && index == 1 {
            return Err(Error("injected failure after DTB publication".into()));
        }
    }
    for spec in &contract.anchors {
        verify_file_at(&boot_directory, spec)?;
    }
    let names = list_names(boot)?;
    for spec in &contract.old_files {
        if contains_name(&names, spec.name) {
            return Err(Error(format!(
                "old candidate remains after publication: {}",
                spec.name
            )));
        }
    }
    for spec in contract.final_files() {
        verify_file_at(&boot_directory, spec)?;
    }
    unlink_at(&boot_directory, contract.journal.name)?;
    durable.sync_filesystem(&boot_directory)?;
    if verify_boot_state(contract, boot)? != BootState::Installed {
        return Err(Error("final BOOT state verification failed".into()));
    }
    Ok(InstallOutcome {
        changed: true,
        recovered: recovery,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TestDurability;

    impl DurableFilesystem for TestDurability {
        fn sync_filesystem(&self, directory: &File) -> Result<()> {
            directory
                .sync_all()
                .map_err(|error| io_error("test directory fsync", error))
        }

        fn set_timestamp(&self, _directory: &File, _name: &str, _epoch: i64) -> Result<()> {
            Ok(())
        }

        fn rename_noreplace(
            &self,
            directory: &File,
            source: &str,
            destination: &str,
        ) -> Result<()> {
            if child_exists_regular(directory, destination)? {
                return Err(Error(format!("destination exists: {destination}")));
            }
            let source = CString::new(source).unwrap();
            let destination = CString::new(destination).unwrap();
            if unsafe {
                libc::renameat(
                    directory.as_raw_fd(),
                    source.as_ptr(),
                    directory.as_raw_fd(),
                    destination.as_ptr(),
                )
            } != 0
            {
                return Err(io_error("test renameat", std::io::Error::last_os_error()));
            }
            Ok(())
        }
    }

    struct Fixture {
        root: std::path::PathBuf,
        boot: std::path::PathBuf,
        stage: std::path::PathBuf,
        roms: std::path::PathBuf,
        contract: Contract,
    }

    fn leak(value: String) -> &'static str {
        Box::leak(value.into_boxed_str())
    }

    fn spec(name: &'static str, bytes: &'static [u8]) -> FileSpec {
        FileSpec {
            name,
            size: bytes.len() as u64,
            sha256: leak(format!("{:x}", Sha256::digest(bytes))),
        }
    }

    impl Fixture {
        fn new() -> Self {
            static ACTIVE: &[u8] = b"active-v08\n";
            static ACTIVE_VERSIONED: &[u8] = b"active-v08-versioned\n";
            static OLD_IMAGE: &[u8] = b"old-v09-image\n";
            static OLD_BOOT: &[u8] = b"old-v09-boot\n";
            static SOURCE_IMAGE: &[u8] = b"v10-image\n";
            static SOURCE_DTB: &[u8] = b"v10-dtb\n";
            static SOURCE_BOOT: &[u8] = b"fallback=boot.ini.v0.2-known-good\n";
            static FINAL_BOOT: &[u8] = b"fallback=boot.ini.v0.8-bootloader-handoff\n";
            static MANIFEST: &[u8] = b"manifest\n";
            static COMPLETE: &[u8] = b"complete\n";
            static JOURNAL: &[u8] = b"format=fixture\nstate=in-progress\n";
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let counter = TEST_COUNTER.fetch_add(1, Ordering::SeqCst);
            let cache = Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../out/.cache/r46h-v10-target-installer/tests");
            fs::create_dir_all(&cache).unwrap();
            let root = cache.join(format!(
                "r46h-v10-target-rust-test-{}-{nonce}-{counter}",
                std::process::id(),
            ));
            let boot = root.join("boot");
            let stage = root.join("stage");
            let roms = root.join("roms");
            fs::create_dir_all(roms.join("payload")).unwrap();
            fs::create_dir(&boot).unwrap();
            fs::create_dir(&stage).unwrap();
            let contract = Contract {
                payload_name: "payload",
                payload_manifest: spec("DEPLOY-MANIFEST", MANIFEST),
                payload_complete: spec("STAGE-COMPLETE", COMPLETE),
                source_image: spec("Image.v10.gz", SOURCE_IMAGE),
                source_dtb: spec("v10.dtb", SOURCE_DTB),
                source_boot: spec("boot.v10", SOURCE_BOOT),
                final_boot: spec("boot.v10", FINAL_BOOT),
                boot_fallback_old: b"boot.ini.v0.2-known-good",
                boot_fallback_new: b"boot.ini.v0.8-bootloader-handoff",
                old_files: vec![spec("Image.v09.gz", OLD_IMAGE), spec("boot.v09", OLD_BOOT)],
                anchors: vec![
                    spec("boot.ini", ACTIVE),
                    spec("boot.ini.v08", ACTIVE_VERSIONED),
                ],
                stable_top_level: ["boot.ini", "boot.ini.v08", "vendor.bin"]
                    .into_iter()
                    .collect(),
                stable_directories: BTreeSet::new(),
                stage_suffix: ".stage",
                journal: spec(".install.stage", JOURNAL),
                journal_bytes: JOURNAL,
                minimum_free_bytes: 0,
                source_date_epoch: 1_785_369_600,
            };
            for (name, bytes) in [
                ("boot.ini", ACTIVE),
                ("boot.ini.v08", ACTIVE_VERSIONED),
                ("vendor.bin", b"vendor\n"),
                ("Image.v09.gz", OLD_IMAGE),
                ("boot.v09", OLD_BOOT),
            ] {
                fs::write(boot.join(name), bytes).unwrap();
            }
            for (name, bytes) in [
                ("Image.v10.gz", SOURCE_IMAGE),
                ("v10.dtb", SOURCE_DTB),
                ("boot.v10", FINAL_BOOT),
            ] {
                fs::write(stage.join(name), bytes).unwrap();
            }
            let payload = roms.join("payload");
            for (name, bytes) in [
                ("DEPLOY-MANIFEST", MANIFEST),
                ("STAGE-COMPLETE", COMPLETE),
                ("Image.v10.gz", SOURCE_IMAGE),
                ("v10.dtb", SOURCE_DTB),
                ("boot.v10", SOURCE_BOOT),
            ] {
                fs::write(payload.join(name), bytes).unwrap();
            }
            Self {
                root,
                boot,
                stage,
                roms,
                contract,
            }
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    #[test]
    fn freezes_sources_and_rewrites_only_fallback_comment() {
        let fixture = Fixture::new();
        let frozen = fixture.root.join("frozen");
        fs::create_dir(&frozen).unwrap();
        freeze_sources(&fixture.contract, &fixture.roms, &frozen).unwrap();
        assert_eq!(
            fs::read(frozen.join("boot.v10")).unwrap(),
            b"fallback=boot.ini.v0.8-bootloader-handoff\n"
        );
        for spec in fixture.contract.final_files() {
            verify_file_at(&open_directory(&frozen).unwrap(), spec).unwrap();
        }
    }

    #[test]
    fn happy_install_is_idempotent_and_preserves_active_boot() {
        let fixture = Fixture::new();
        let active_before = fs::read(fixture.boot.join("boot.ini")).unwrap();
        let first = install_candidate_files(
            &fixture.contract,
            &TestDurability,
            &fixture.boot,
            &fixture.stage,
            false,
            None,
        )
        .unwrap();
        let second = install_candidate_files(
            &fixture.contract,
            &TestDurability,
            &fixture.boot,
            &fixture.stage,
            false,
            None,
        )
        .unwrap();
        assert!(first.changed);
        assert!(!second.changed);
        assert_eq!(
            fs::read(fixture.boot.join("boot.ini")).unwrap(),
            active_before
        );
        assert_eq!(
            verify_boot_state(&fixture.contract, &fixture.boot).unwrap(),
            BootState::Installed
        );
    }

    #[test]
    fn recovery_space_counts_only_files_that_are_still_absent() {
        let fixture = Fixture::new();
        let mut names = fixture.contract.base_names();
        let required_base = required_publication_bytes(
            &fixture.contract,
            &names.into_iter().map(str::to_owned).collect(),
        )
        .unwrap();
        names = fixture.contract.base_names();
        names.insert(fixture.contract.source_image.name);
        let required_after_image = required_publication_bytes(
            &fixture.contract,
            &names.into_iter().map(str::to_owned).collect(),
        )
        .unwrap();
        assert_eq!(
            required_base - required_after_image,
            fixture.contract.source_image.size
        );
        assert!(required_after_image < required_base);
    }

    #[test]
    fn failures_are_journaled_and_recover_without_early_boot_script() {
        for fault in [
            FaultPoint::AfterOldRemoved,
            FaultPoint::AfterImage,
            FaultPoint::AfterDtb,
        ] {
            let fixture = Fixture::new();
            let error = install_candidate_files(
                &fixture.contract,
                &TestDurability,
                &fixture.boot,
                &fixture.stage,
                false,
                Some(fault),
            )
            .unwrap_err();
            assert!(error.0.contains("injected failure"));
            assert_eq!(
                verify_boot_state(&fixture.contract, &fixture.boot).unwrap(),
                BootState::Partial
            );
            if fault != FaultPoint::AfterDtb {
                assert!(!fixture.boot.join("boot.v10").exists());
            }
            install_candidate_files(
                &fixture.contract,
                &TestDurability,
                &fixture.boot,
                &fixture.stage,
                true,
                None,
            )
            .unwrap();
            assert_eq!(
                verify_boot_state(&fixture.contract, &fixture.boot).unwrap(),
                BootState::Installed
            );
        }
    }

    #[test]
    fn tampered_anchor_extra_name_and_source_symlink_fail_before_journal() {
        for mutation in 0..3 {
            let fixture = Fixture::new();
            match mutation {
                0 => fs::write(fixture.boot.join("boot.ini"), b"tampered\n").unwrap(),
                1 => fs::write(fixture.boot.join("unexpected.bin"), b"unexpected\n").unwrap(),
                2 => {
                    fs::remove_file(fixture.stage.join("Image.v10.gz")).unwrap();
                    symlink("v10.dtb", fixture.stage.join("Image.v10.gz")).unwrap();
                }
                _ => unreachable!(),
            }
            assert!(install_candidate_files(
                &fixture.contract,
                &TestDurability,
                &fixture.boot,
                &fixture.stage,
                false,
                None,
            )
            .is_err());
            assert!(!fixture.boot.join(fixture.contract.journal.name).exists());
        }
    }

    #[test]
    fn exact_space_name_and_stable_entry_types_are_enforced() {
        let mut fixture = Fixture::new();
        fixture
            .contract
            .stable_top_level
            .insert("System Volume Information");
        fixture
            .contract
            .stable_directories
            .insert("System Volume Information");
        fs::create_dir(fixture.boot.join("System Volume Information")).unwrap();
        assert_eq!(
            verify_boot_state(&fixture.contract, &fixture.boot).unwrap(),
            BootState::Base
        );

        fs::remove_dir(fixture.boot.join("System Volume Information")).unwrap();
        fs::write(
            fixture.boot.join("System Volume Information"),
            b"not a directory\n",
        )
        .unwrap();
        assert!(verify_boot_state(&fixture.contract, &fixture.boot).is_err());

        fs::remove_file(fixture.boot.join("System Volume Information")).unwrap();
        fs::remove_file(fixture.boot.join("vendor.bin")).unwrap();
        fs::create_dir(fixture.boot.join("vendor.bin")).unwrap();
        assert!(verify_boot_state(&fixture.contract, &fixture.boot).is_err());
    }

    #[test]
    fn tampered_journal_is_not_recoverable() {
        let fixture = Fixture::new();
        for spec in &fixture.contract.old_files {
            fs::remove_file(fixture.boot.join(spec.name)).unwrap();
        }
        fs::write(
            fixture.boot.join(fixture.contract.journal.name),
            b"tampered\n",
        )
        .unwrap();
        assert!(verify_boot_state(&fixture.contract, &fixture.boot).is_err());
    }
}
