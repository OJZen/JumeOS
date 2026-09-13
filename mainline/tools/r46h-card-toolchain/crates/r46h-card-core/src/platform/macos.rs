use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CStr;
use std::os::raw::{c_char, c_int, c_void};
use std::ptr::NonNull;

use crate::error::{Error, Result};
use crate::readonly::{DiscoveryCandidate, PartitionObservation, ReadOnlyMediaSession};

const MAX_CANDIDATES: usize = 64;
const PATH_CAPACITY: usize = 128;
const TEXT_CAPACITY: usize = 128;

#[repr(C)]
#[derive(Clone, Copy)]
struct NativeCandidate {
    attachment_id: [c_char; TEXT_CAPACITY],
    physical_store_id: [c_char; TEXT_CAPACITY],
    display_path: [c_char; PATH_CAPACITY],
    raw_path: [c_char; PATH_CAPACITY],
    transport: [c_char; TEXT_CAPACITY],
    registry_entry_id: u64,
    physical_registry_entry_id: u64,
    device_number: u64,
    size: u64,
    sector_size: u32,
    whole: u8,
    internal: u8,
    removable: u8,
    ejectable: u8,
    writable: u8,
    system_disk: u8,
}

impl Default for NativeCandidate {
    fn default() -> Self {
        // The C ABI contract treats all-zero bytes as an empty output slot.
        unsafe { std::mem::zeroed() }
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
struct NativePartition {
    number: u32,
    offset: u64,
    size: u64,
    filesystem: [c_char; TEXT_CAPACITY],
    volume_uuid: [c_char; TEXT_CAPACITY],
}

impl Default for NativePartition {
    fn default() -> Self {
        unsafe { std::mem::zeroed() }
    }
}

#[repr(C)]
struct NativeSession {
    _private: [u8; 0],
}

unsafe extern "C" {
    fn r46h_macos_discover(
        candidates: *mut NativeCandidate,
        capacity: usize,
        count: *mut usize,
    ) -> c_int;
    fn r46h_macos_claim_readonly(expected: *const NativeCandidate) -> *mut NativeSession;
    fn r46h_macos_path_whole_registry_id(path: *const c_char, registry_entry_id: *mut u64)
    -> c_int;
    fn r46h_macos_path_whole_bsd_name(
        path: *const c_char,
        bsd_name: *mut c_char,
        capacity: usize,
    ) -> c_int;
    fn r46h_macos_partition_observation(
        session: *mut NativeSession,
        candidate: *const NativeCandidate,
        partition_number: u32,
        observation: *mut NativePartition,
    ) -> c_int;
    fn r46h_macos_read_at(
        session: *mut NativeSession,
        offset: u64,
        buffer: *mut c_void,
        length: usize,
    ) -> c_int;
    fn r46h_macos_eject(session: *mut NativeSession) -> c_int;
    fn r46h_macos_revalidate(session: *mut NativeSession) -> c_int;
    fn r46h_macos_session_free(session: *mut NativeSession);
}

pub struct MacosReadOnlySession {
    native: NonNull<NativeSession>,
    candidate: DiscoveryCandidate,
    partitions: Vec<PartitionObservation>,
    ejected: bool,
}

pub fn discover() -> Result<Vec<DiscoveryCandidate>> {
    Ok(discover_native()?
        .into_iter()
        .map(|(_, candidate)| candidate)
        .collect())
}

pub fn claim(attachment_id: &str) -> Result<MacosReadOnlySession> {
    let matches: Vec<_> = discover_native()?
        .into_iter()
        .filter(|(_, candidate)| candidate.attachment_id == attachment_id)
        .collect();
    if matches.len() != 1 {
        return Err(Error::InvalidData(format!(
            "read-only attachment selector matched {} candidates",
            matches.len()
        )));
    }
    let (native_candidate, candidate) = matches.into_iter().next().expect("one match");
    if candidate.system_disk
        || candidate.internal
        || !candidate.whole
        || !candidate.removable
        || !candidate.ejectable
        || !candidate.transport.eq_ignore_ascii_case("usb")
    {
        return Err(Error::InvalidData(
            "selected attachment is not an eligible external removable whole medium".into(),
        ));
    }

    let native = NonNull::new(unsafe { r46h_macos_claim_readonly(&native_candidate) })
        .ok_or_else(|| last_os_error("claim external medium for read-only audit"))?;
    let partitions = match read_partitions(native, &native_candidate) {
        Ok(partitions) => partitions,
        Err(error) => {
            let eject_error = if unsafe { r46h_macos_eject(native.as_ptr()) } == 0 {
                None
            } else {
                Some(last_os_error("eject after partition inspection failure"))
            };
            unsafe { r46h_macos_session_free(native.as_ptr()) };
            return match eject_error {
                Some(eject_error) => Err(Error::InvalidData(format!(
                    "partition inspection failed: {error}; eject also failed: {eject_error}"
                ))),
                None => Err(error),
            };
        }
    };
    Ok(MacosReadOnlySession {
        native,
        candidate,
        partitions,
        ejected: false,
    })
}

pub fn validate_external_path(attachment_id: &str, path: &std::path::Path) -> Result<()> {
    use std::os::unix::ffi::OsStrExt;

    let matches: Vec<_> = discover_native()?
        .into_iter()
        .filter(|(_, candidate)| candidate.attachment_id == attachment_id)
        .collect();
    if matches.len() != 1 {
        return Err(Error::InvalidData(format!(
            "external-path attachment selector matched {} candidates",
            matches.len()
        )));
    }
    let (native, _) = &matches[0];
    let canonical = path
        .canonicalize()
        .map_err(|source| Error::io("canonicalize external evidence parent", source))?;
    let bytes = canonical.as_os_str().as_bytes();
    if bytes.contains(&0) {
        return Err(Error::UnsafePath(canonical));
    }
    let c_path = std::ffi::CString::new(bytes).map_err(|_| Error::UnsafePath(canonical.clone()))?;
    let mut registry_entry_id = 0_u64;
    if unsafe { r46h_macos_path_whole_registry_id(c_path.as_ptr(), &mut registry_entry_id) } != 0 {
        return Err(last_os_error("resolve external evidence physical store"));
    }
    let mut whole_bsd_name = [0 as c_char; TEXT_CAPACITY];
    if unsafe {
        r46h_macos_path_whole_bsd_name(
            c_path.as_ptr(),
            whole_bsd_name.as_mut_ptr(),
            whole_bsd_name.len(),
        )
    } != 0
    {
        return Err(last_os_error("resolve external evidence whole disk"));
    }
    let whole_bsd_name = c_string(&whole_bsd_name, "external whole BSD name")?;
    let target_display_path = c_string(&native.display_path, "target display path")?;
    if registry_entry_id == native.physical_registry_entry_id
        || target_display_path == format!("/dev/{whole_bsd_name}")
    {
        return Err(Error::UnsafePath(canonical));
    }
    Ok(())
}

impl ReadOnlyMediaSession for MacosReadOnlySession {
    fn candidate(&self) -> &DiscoveryCandidate {
        &self.candidate
    }

    fn partitions(&self) -> &[PartitionObservation] {
        &self.partitions
    }

    fn read_exact_at(&mut self, offset: u64, buffer: &mut [u8]) -> Result<()> {
        let end = offset
            .checked_add(buffer.len() as u64)
            .ok_or_else(|| Error::InvalidData("raw read range overflow".into()))?;
        if end > self.candidate.size {
            return Err(Error::InvalidData("raw read exceeds whole medium".into()));
        }
        if unsafe {
            r46h_macos_read_at(
                self.native.as_ptr(),
                offset,
                buffer.as_mut_ptr().cast(),
                buffer.len(),
            )
        } != 0
        {
            return Err(last_os_error("read claimed medium"));
        }
        if unsafe { r46h_macos_revalidate(self.native.as_ptr()) } != 0 {
            return Err(last_os_error("revalidate claimed medium after read"));
        }
        Ok(())
    }

    fn eject(&mut self) -> Result<()> {
        if self.ejected {
            return Err(Error::InvalidData("medium was already ejected".into()));
        }
        if unsafe { r46h_macos_eject(self.native.as_ptr()) } != 0 {
            return Err(last_os_error("eject claimed medium"));
        }
        self.ejected = true;
        Ok(())
    }
}

impl Drop for MacosReadOnlySession {
    fn drop(&mut self) {
        unsafe { r46h_macos_session_free(self.native.as_ptr()) };
    }
}

fn discover_native() -> Result<Vec<(NativeCandidate, DiscoveryCandidate)>> {
    let mut native = vec![NativeCandidate::default(); MAX_CANDIDATES];
    let mut count = 0_usize;
    if unsafe { r46h_macos_discover(native.as_mut_ptr(), native.len(), &mut count) } != 0 {
        return Err(last_os_error("discover IOMedia whole disks"));
    }
    if count > native.len() {
        return Err(Error::InvalidData(
            "native discovery returned an invalid candidate count".into(),
        ));
    }
    let mut attachment_ids = BTreeSet::new();
    let mut candidates = Vec::with_capacity(count);
    for item in native.into_iter().take(count) {
        let candidate = candidate_from_native(&item)?;
        if !attachment_ids.insert(candidate.attachment_id.clone()) {
            return Err(Error::InvalidData(
                "native discovery returned duplicate attachment identities".into(),
            ));
        }
        candidates.push((item, candidate));
    }
    candidates.sort_by(|left, right| left.1.attachment_id.cmp(&right.1.attachment_id));
    Ok(candidates)
}

fn candidate_from_native(native: &NativeCandidate) -> Result<DiscoveryCandidate> {
    let internal = native.internal != 0;
    Ok(DiscoveryCandidate {
        platform: "macos".into(),
        attachment_id: c_string(&native.attachment_id, "attachment_id")?,
        physical_store_id: c_string(&native.physical_store_id, "physical_store_id")?,
        display_path: c_string(&native.display_path, "display_path")?,
        transport: c_string(&native.transport, "transport")?,
        size: native.size,
        sector_size: native.sector_size,
        whole: native.whole != 0,
        internal,
        removable: native.removable != 0,
        ejectable: native.ejectable != 0,
        writable: native.writable != 0,
        // Discovery accepts only external media. This conservative bit remains
        // true for every internal candidate and therefore rejects the system
        // store even if higher-level root-volume resolution is unavailable.
        system_disk: native.system_disk != 0,
    })
}

fn read_partitions(
    session: NonNull<NativeSession>,
    native: &NativeCandidate,
) -> Result<Vec<PartitionObservation>> {
    let mut partitions = Vec::new();
    for number in 1..=4_u32 {
        let mut observation = NativePartition::default();
        let status = unsafe {
            r46h_macos_partition_observation(session.as_ptr(), native, number, &mut observation)
        };
        if status == 1 {
            break;
        }
        if status != 0 {
            return Err(last_os_error("inspect partition"));
        }
        let filesystem = optional_c_string(&observation.filesystem, "filesystem")?
            .map(|value| canonical_filesystem(&value));
        let mut identifiers = BTreeMap::new();
        if let Some(uuid) = optional_c_string(&observation.volume_uuid, "volume UUID")? {
            identifiers.insert("volume_uuid".into(), uuid.to_ascii_uppercase());
        }
        partitions.push(PartitionObservation {
            number: observation.number,
            offset: observation.offset,
            size: observation.size,
            filesystem,
            identifiers,
        });
    }
    if partitions.is_empty() {
        return Err(Error::InvalidData("whole medium has no partitions".into()));
    }
    Ok(partitions)
}

fn canonical_filesystem(value: &str) -> String {
    match value.to_ascii_lowercase().as_str() {
        "msdos" | "fat" | "fat32" => "fat32".into(),
        "exfat" => "exfat".into(),
        "ext4" | "linux" => "ext4".into(),
        other => other.into(),
    }
}

fn c_string<const N: usize>(bytes: &[c_char; N], field: &str) -> Result<String> {
    optional_c_string(bytes, field)?
        .ok_or_else(|| Error::InvalidData(format!("native candidate field {field} is empty")))
}

fn optional_c_string<const N: usize>(bytes: &[c_char; N], field: &str) -> Result<Option<String>> {
    let terminator = bytes.iter().position(|byte| *byte == 0).ok_or_else(|| {
        Error::InvalidData(format!("native candidate field {field} is unterminated"))
    })?;
    if terminator == 0 {
        return Ok(None);
    }
    let value = unsafe { CStr::from_ptr(bytes.as_ptr()) }
        .to_str()
        .map_err(|_| Error::InvalidData(format!("native candidate field {field} is not UTF-8")))?;
    Ok(Some(value.to_owned()))
}

fn last_os_error(context: &'static str) -> Error {
    Error::io(context, std::io::Error::last_os_error())
}
