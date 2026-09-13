//! Read-only media discovery and profile certification.
//!
//! This module intentionally defines capabilities that are separate from
//! [`crate::backend::MediaSession`]. A native implementation can expose a raw
//! read operation and eject a claimed medium, but it cannot acquire a write
//! capability through this API.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::digest::is_sha256;
use crate::error::{Error, Result};
use crate::model::{CardProfile, PartitionRole, PartitionScheme};

pub const READ_ONLY_AUDIT_FORMAT_VERSION: u32 = 1;
const MBR_SIZE: usize = 512;
const MBR_DISK_SIGNATURE_OFFSET: usize = 440;
const MBR_PARTITION_TABLE_OFFSET: usize = 446;
const MBR_PARTITION_ENTRY_SIZE: usize = 16;
const MBR_PARTITION_COUNT: usize = 4;
const READ_BUFFER_SIZE: usize = 1024 * 1024;
const LAYOUT_ID_DOMAIN: &[u8] = b"r46h-profile-bound-layout-v1\0";

/// A currently attached whole-media candidate.
///
/// `attachment_id` identifies this attachment, not its content. A stable
/// layout identity is minted only after a complete profile-bound audit.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DiscoveryCandidate {
    pub platform: String,
    pub attachment_id: String,
    pub physical_store_id: String,
    pub display_path: String,
    pub transport: String,
    pub size: u64,
    pub sector_size: u32,
    pub whole: bool,
    pub internal: bool,
    pub removable: bool,
    pub ejectable: bool,
    pub writable: bool,
    pub system_disk: bool,
}

/// Platform observations for one partition. The role is deliberately absent:
/// the trusted profile assigns roles only after matching the partition number.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PartitionObservation {
    pub number: u32,
    pub offset: u64,
    pub size: u64,
    #[serde(default)]
    pub filesystem: Option<String>,
    #[serde(default)]
    pub identifiers: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct VerifiedPartition {
    pub role: PartitionRole,
    pub number: u32,
    pub offset: u64,
    pub size: u64,
    pub mbr_bootable: bool,
    pub mbr_type_code: u8,
    #[serde(default)]
    pub filesystem: Option<String>,
    #[serde(default)]
    pub identifiers: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MediaAccess {
    ReadOnly,
}

/// Receipt emitted only after a profile-bound read audit and successful eject.
///
/// There is intentionally no `safe_to_boot`, write-plan, or destructive
/// authorization field. It records a layout fingerprint and successful reads
/// of the bounded regions used by that fingerprint. It is neither a whole-card
/// digest nor authenticated provenance, and never authorizes execution/writes.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ReadOnlyAuditReceipt {
    pub format_version: u32,
    pub audit_id: String,
    pub profile_id: String,
    pub profile_sha256: String,
    pub tool_version: String,
    pub tool_sha256: String,
    pub hardware_target: String,
    pub layout_id: String,
    pub candidate: DiscoveryCandidate,
    pub partition_scheme: PartitionScheme,
    pub prefix_size: u64,
    pub prefix_sha256: String,
    pub mbr_disk_signature: u32,
    pub partitions: Vec<VerifiedPartition>,
    pub media_access: MediaAccess,
    pub ejected: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MbrPartition {
    pub number: u32,
    pub bootable: bool,
    pub type_code: u8,
    pub offset: u64,
    pub size: u64,
    pub partuuid: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MbrObservation {
    pub disk_signature: u32,
    pub partitions: Vec<MbrPartition>,
}

/// A claimed medium with no write-capable method or handle.
pub trait ReadOnlyMediaSession {
    fn candidate(&self) -> &DiscoveryCandidate;
    fn partitions(&self) -> &[PartitionObservation];

    /// Fill `buffer` from an exact raw-media offset. Implementations must use a
    /// descriptor opened without write access and fail on a short read.
    fn read_exact_at(&mut self, offset: u64, buffer: &mut [u8]) -> Result<()>;

    /// Release and eject the claimed whole medium.
    fn eject(&mut self) -> Result<()>;
}

/// Discovery and claim surface for read-only native implementations.
pub trait ReadOnlyPlatformBackend {
    type Session: ReadOnlyMediaSession;

    fn platform_name(&self) -> &'static str;
    fn discover_readonly(&self) -> Result<Vec<DiscoveryCandidate>>;
    fn validate_external_path(&self, attachment_id: &str, path: &Path) -> Result<()>;
    fn claim_readonly(&self, attachment_id: &str) -> Result<Self::Session>;
}

/// Audit an already-claimed medium, always attempt eject, and mint a receipt
/// only if both the audit and eject succeed.
pub fn audit_and_eject<S: ReadOnlyMediaSession>(
    session: &mut S,
    profile: &CardProfile,
    audit_id: &str,
    profile_file_sha256: &str,
    tool_version: &str,
    tool_sha256: &str,
) -> Result<ReadOnlyAuditReceipt> {
    let audit = inspect_claimed_media(
        session,
        profile,
        audit_id,
        profile_file_sha256,
        tool_version,
        tool_sha256,
    );
    let eject = session.eject();

    match (audit, eject) {
        (Ok(mut receipt), Ok(())) => {
            receipt.ejected = true;
            Ok(receipt)
        }
        (Err(audit_error), Ok(())) => Err(audit_error),
        (Err(audit_error), Err(eject_error)) => Err(Error::InvalidData(format!(
            "read-only audit failed: {audit_error}; eject also failed: {eject_error}"
        ))),
        (Ok(_), Err(eject_error)) => Err(eject_error),
    }
}

/// Validate the stricter profile subset that the macOS read-only backend can
/// certify before discovery or claim begins.
pub fn validate_macos_readonly_profile(profile: &CardProfile) -> Result<()> {
    profile.validate()?;
    validate_bounded_text(&profile.target, "profile target", 128)?;
    if profile.partition_scheme != PartitionScheme::Mbr
        || profile.sector_size != MBR_SIZE as u32
        || profile.partitions.is_empty()
        || profile.partitions.len() > MBR_PARTITION_COUNT
    {
        return Err(Error::InvalidData(
            "macOS read-only audit requires a 512-byte MBR profile with 1-4 partitions".into(),
        ));
    }
    for (index, partition) in profile.partitions.iter().enumerate() {
        if partition.number != (index + 1) as u32 {
            return Err(Error::InvalidData(
                "macOS read-only profile partition numbers must be consecutive and ordered".into(),
            ));
        }
        let mbr = partition.mbr.as_ref().ok_or_else(|| {
            Error::InvalidData(format!(
                "macOS read-only profile partition {} has no MBR identity",
                partition.number
            ))
        })?;
        if mbr.type_code == 0 {
            return Err(Error::InvalidData(
                "macOS read-only profile has an invalid MBR type".into(),
            ));
        }
        let filesystem = partition.filesystem.as_deref().ok_or_else(|| {
            Error::InvalidData(format!(
                "macOS read-only profile partition {} has no filesystem",
                partition.number
            ))
        })?;
        let canonical = canonical_filesystem(filesystem)?;
        if canonical != filesystem || !matches!(canonical.as_str(), "fat32" | "ext4" | "exfat") {
            return Err(Error::InvalidData(format!(
                "macOS read-only profile partition {} has an unsupported filesystem",
                partition.number
            )));
        }
        for (key, value) in &partition.identifiers {
            if !matches!(key.as_str(), "partuuid" | "volume_uuid")
                || canonical_identifier(key, value)? != *value
            {
                return Err(Error::InvalidData(format!(
                    "macOS read-only profile partition {} has a non-canonical identifier",
                    partition.number
                )));
            }
        }
        let required_identifier = match partition.role {
            PartitionRole::Boot | PartitionRole::Easyroms => "volume_uuid",
            PartitionRole::Root => "partuuid",
        };
        if partition.identifiers.len() != 1
            || !partition.identifiers.contains_key(required_identifier)
        {
            return Err(Error::InvalidData(format!(
                "macOS read-only profile partition {} must contain only its required {} identity",
                partition.number, required_identifier
            )));
        }
        if let Some(partuuid) = partition.identifiers.get("partuuid") {
            let expected_suffix = format!("-{:02}", partition.number);
            if !partuuid.ends_with(&expected_suffix) {
                return Err(Error::InvalidData(format!(
                    "macOS read-only profile partition {} PARTUUID has the wrong partition suffix",
                    partition.number
                )));
            }
        }
    }
    Ok(())
}

/// Reject a set containing the same profile-bound layout identity more than
/// once. This is a layout-fingerprint check, not a whole-card content digest.
pub fn ensure_unique_layout_ids<'a, I>(receipts: I) -> Result<()>
where
    I: IntoIterator<Item = &'a ReadOnlyAuditReceipt>,
{
    let mut layout_ids = BTreeSet::new();
    for receipt in receipts {
        receipt.validate()?;
        if !layout_ids.insert(receipt.layout_id.as_str()) {
            return Err(Error::InvalidData(format!(
                "duplicate audited layout identity: {}",
                receipt.layout_id
            )));
        }
    }
    Ok(())
}

pub fn parse_mbr_sector0(sector0: &[u8], sector_size: u32) -> Result<MbrObservation> {
    if sector_size != MBR_SIZE as u32 {
        return Err(Error::Unsupported(
            "MBR audit currently requires 512-byte logical sectors".into(),
        ));
    }
    if sector0.len() < MBR_SIZE || sector0[510..512] != [0x55, 0xaa] {
        return Err(Error::InvalidData("invalid MBR sector signature".into()));
    }

    let disk_signature = u32::from_le_bytes(
        sector0[MBR_DISK_SIGNATURE_OFFSET..MBR_DISK_SIGNATURE_OFFSET + 4]
            .try_into()
            .expect("fixed MBR signature slice"),
    );
    if disk_signature == 0 {
        return Err(Error::InvalidData(
            "zero MBR disk signature cannot identify content".into(),
        ));
    }

    let mut partitions = Vec::new();
    for index in 0..MBR_PARTITION_COUNT {
        let base = MBR_PARTITION_TABLE_OFFSET + index * MBR_PARTITION_ENTRY_SIZE;
        let status = sector0[base];
        let type_code = sector0[base + 4];
        let first_lba = u32::from_le_bytes(
            sector0[base + 8..base + 12]
                .try_into()
                .expect("fixed MBR LBA slice"),
        );
        let sector_count = u32::from_le_bytes(
            sector0[base + 12..base + 16]
                .try_into()
                .expect("fixed MBR size slice"),
        );

        if status != 0 && status != 0x80 {
            return Err(Error::InvalidData(format!(
                "MBR partition {} has an invalid status byte",
                index + 1
            )));
        }
        let empty = type_code == 0 && first_lba == 0 && sector_count == 0;
        if empty {
            continue;
        }
        if type_code == 0 || first_lba == 0 || sector_count == 0 {
            return Err(Error::InvalidData(format!(
                "MBR partition {} is only partially populated",
                index + 1
            )));
        }

        let offset = u64::from(first_lba)
            .checked_mul(u64::from(sector_size))
            .ok_or_else(|| Error::InvalidData("MBR partition offset overflow".into()))?;
        let size = u64::from(sector_count)
            .checked_mul(u64::from(sector_size))
            .ok_or_else(|| Error::InvalidData("MBR partition size overflow".into()))?;
        partitions.push(MbrPartition {
            number: (index + 1) as u32,
            bootable: status == 0x80,
            type_code,
            offset,
            size,
            partuuid: format!("{disk_signature:08x}-{:02}", index + 1),
        });
    }
    if partitions.is_empty() {
        return Err(Error::InvalidData("MBR has no partitions".into()));
    }
    Ok(MbrObservation {
        disk_signature,
        partitions,
    })
}

impl DiscoveryCandidate {
    pub fn validate_for_profile(&self, profile: &CardProfile) -> Result<()> {
        self.validate_intrinsic()?;
        if self.size != profile.whole_size || self.sector_size != profile.sector_size {
            return Err(Error::InvalidData(
                "candidate geometry does not match profile".into(),
            ));
        }
        Ok(())
    }

    fn validate_intrinsic(&self) -> Result<()> {
        validate_bounded_text(&self.platform, "candidate platform", 64)?;
        validate_bounded_text(&self.attachment_id, "candidate attachment_id", 512)?;
        validate_bounded_text(&self.physical_store_id, "candidate physical_store_id", 512)?;
        validate_bounded_text(&self.display_path, "candidate display_path", 1024)?;
        validate_bounded_text(&self.transport, "candidate transport", 64)?;
        if !self.whole || self.internal || !self.removable || !self.ejectable || self.system_disk {
            return Err(Error::InvalidData(
                "candidate is not an eligible external whole medium".into(),
            ));
        }
        if !self.transport.eq_ignore_ascii_case("usb") {
            return Err(Error::InvalidData(
                "candidate is not attached through the required USB transport".into(),
            ));
        }
        if self.size == 0
            || self.sector_size < MBR_SIZE as u32
            || !self.sector_size.is_power_of_two()
            || self.size % u64::from(self.sector_size) != 0
        {
            return Err(Error::InvalidData(
                "candidate media geometry is invalid".into(),
            ));
        }
        Ok(())
    }
}

impl ReadOnlyAuditReceipt {
    pub fn validate(&self) -> Result<()> {
        if self.format_version != READ_ONLY_AUDIT_FORMAT_VERSION {
            return Err(Error::InvalidData(
                "read-only receipt format_version must be 1".into(),
            ));
        }
        crate::model::validate_id(&self.audit_id, "audit_id")?;
        crate::model::validate_id(&self.profile_id, "profile_id")?;
        validate_bounded_text(&self.hardware_target, "hardware_target", 128)?;
        self.candidate.validate_intrinsic()?;
        if !is_sha256(&self.profile_sha256)
            || !is_sha256(&self.tool_sha256)
            || !is_sha256(&self.prefix_sha256)
            || !valid_layout_id(&self.layout_id)
            || self.partition_scheme != PartitionScheme::Mbr
            || self.prefix_size == 0
            || self.prefix_size > self.candidate.size
            || self.mbr_disk_signature == 0
            || !self.ejected
            || self.partitions.is_empty()
        {
            return Err(Error::InvalidData(
                "read-only receipt is incomplete or invalid".into(),
            ));
        }
        validate_bounded_text(&self.tool_version, "tool_version", 128)?;
        let mut numbers = BTreeSet::new();
        let mut roles = BTreeSet::new();
        let mut ranges = Vec::new();
        let mut previous_number = 0_u32;
        for partition in &self.partitions {
            if partition.number == 0
                || partition.number <= previous_number
                || partition.size == 0
                || !numbers.insert(partition.number)
                || !roles.insert(partition.role)
                || partition.mbr_type_code == 0
            {
                return Err(Error::InvalidData(
                    "read-only receipt partitions are invalid".into(),
                ));
            }
            previous_number = partition.number;
            if partition.offset % u64::from(self.candidate.sector_size) != 0
                || partition.size % u64::from(self.candidate.sector_size) != 0
                || partition.offset > self.candidate.size
                || partition.size > self.candidate.size - partition.offset
            {
                return Err(Error::InvalidData(
                    "read-only receipt partition geometry is invalid".into(),
                ));
            }
            if let Some(filesystem) = &partition.filesystem {
                if canonical_filesystem(filesystem)? != *filesystem {
                    return Err(Error::InvalidData(
                        "read-only receipt filesystem is not canonical".into(),
                    ));
                }
            }
            for (key, value) in &partition.identifiers {
                validate_identifier_key(key)?;
                if canonical_identifier(key, value)? != *value {
                    return Err(Error::InvalidData(
                        "read-only receipt identifier is not canonical".into(),
                    ));
                }
            }
            if let Some(partuuid) = partition.identifiers.get("partuuid") {
                let derived = format!("{:08x}-{:02}", self.mbr_disk_signature, partition.number);
                if *partuuid != derived {
                    return Err(Error::InvalidData(format!(
                        "read-only receipt partition {} PARTUUID is not derived from its MBR",
                        partition.number
                    )));
                }
            }
            ranges.push((partition.offset, partition.offset + partition.size));
        }
        ranges.sort_unstable();
        if ranges.windows(2).any(|ranges| ranges[0].1 > ranges[1].0) {
            return Err(Error::InvalidData(
                "read-only receipt partitions overlap".into(),
            ));
        }
        let expected_layout_id = self.recompute_layout_id()?;
        if self.layout_id != expected_layout_id {
            return Err(Error::InvalidData(
                "read-only receipt layout identity does not match its observations".into(),
            ));
        }
        Ok(())
    }

    pub fn recompute_layout_id(&self) -> Result<String> {
        compute_layout_id(LayoutIdentityInput {
            profile_id: &self.profile_id,
            profile_sha256: &self.profile_sha256,
            hardware_target: &self.hardware_target,
            candidate: &self.candidate,
            partition_scheme: self.partition_scheme,
            prefix_size: self.prefix_size,
            prefix_sha256: &self.prefix_sha256,
            mbr_disk_signature: self.mbr_disk_signature,
            partitions: &self.partitions,
        })
    }

    pub fn validate_against(
        &self,
        profile: &CardProfile,
        profile_file_sha256: &str,
        tool_version: &str,
        tool_sha256: &str,
    ) -> Result<()> {
        self.validate()?;
        validate_macos_readonly_profile(profile)?;
        if !is_sha256(profile_file_sha256)
            || !is_sha256(tool_sha256)
            || self.profile_id != profile.profile_id
            || self.profile_sha256 != profile_file_sha256
            || self.hardware_target != profile.target
            || self.tool_version != tool_version
            || self.tool_sha256 != tool_sha256
            || self.candidate.size != profile.whole_size
            || self.candidate.sector_size != profile.sector_size
            || self.partition_scheme != profile.partition_scheme
            || self.prefix_size != profile.prefix.size
            || self.prefix_sha256 != profile.prefix.sha256
            || self.partitions.len() != profile.partitions.len()
        {
            return Err(Error::InvalidData(
                "read-only receipt does not match its external profile/tool bindings".into(),
            ));
        }
        let by_number: BTreeMap<_, _> = self
            .partitions
            .iter()
            .map(|partition| (partition.number, partition))
            .collect();
        for expected in &profile.partitions {
            let actual = by_number.get(&expected.number).ok_or_else(|| {
                Error::InvalidData(format!(
                    "read-only receipt is missing profile partition {}",
                    expected.number
                ))
            })?;
            let mbr = expected.mbr.as_ref().ok_or_else(|| {
                Error::InvalidData(format!(
                    "MBR profile partition {} has no MBR identity",
                    expected.number
                ))
            })?;
            let expected_filesystem = expected
                .filesystem
                .as_deref()
                .map(canonical_filesystem)
                .transpose()?;
            let mut expected_identifiers = BTreeMap::new();
            for (key, value) in &expected.identifiers {
                expected_identifiers.insert(key.clone(), canonical_identifier(key, value)?);
            }
            if actual.role != expected.role
                || actual.offset != expected.offset
                || actual.size != expected.size
                || actual.mbr_bootable != mbr.bootable
                || actual.mbr_type_code != mbr.type_code
                || actual.filesystem != expected_filesystem
                || actual.identifiers != expected_identifiers
            {
                return Err(Error::InvalidData(format!(
                    "read-only receipt partition {} does not match profile",
                    expected.number
                )));
            }
            if let Some(partuuid) = actual.identifiers.get("partuuid") {
                let derived = format!("{:08x}-{:02}", self.mbr_disk_signature, actual.number);
                if *partuuid != derived {
                    return Err(Error::InvalidData(format!(
                        "read-only receipt partition {} PARTUUID is not derived from its MBR",
                        actual.number
                    )));
                }
            }
        }
        Ok(())
    }
}

fn inspect_claimed_media<S: ReadOnlyMediaSession>(
    session: &mut S,
    profile: &CardProfile,
    audit_id: &str,
    profile_file_sha256: &str,
    tool_version: &str,
    tool_sha256: &str,
) -> Result<ReadOnlyAuditReceipt> {
    validate_macos_readonly_profile(profile)?;
    crate::model::validate_id(audit_id, "audit_id")?;
    if !is_sha256(profile_file_sha256) || !is_sha256(tool_sha256) {
        return Err(Error::InvalidData(
            "read-only audit SHA-256 binding is invalid".into(),
        ));
    }
    validate_bounded_text(tool_version, "tool_version", 128)?;
    let candidate = session.candidate().clone();
    candidate.validate_for_profile(profile)?;
    if profile.partition_scheme != PartitionScheme::Mbr {
        return Err(Error::Unsupported(
            "read-only certification currently supports MBR profiles only".into(),
        ));
    }

    let observations = session.partitions().to_vec();
    let prefix_sha256 = hash_exact_range(session, 0, profile.prefix.size)?;
    if prefix_sha256 != profile.prefix.sha256 {
        return Err(Error::InvalidData("media prefix digest mismatch".into()));
    }

    let mut sector0 = [0_u8; MBR_SIZE];
    session.read_exact_at(0, &mut sector0)?;
    let mbr = parse_mbr_sector0(&sector0, candidate.sector_size)?;
    let partitions = verify_partitions(profile, &observations, &mbr)?;
    let layout_id = compute_layout_id(LayoutIdentityInput {
        profile_id: &profile.profile_id,
        profile_sha256: profile_file_sha256,
        hardware_target: &profile.target,
        candidate: &candidate,
        partition_scheme: profile.partition_scheme,
        prefix_size: profile.prefix.size,
        prefix_sha256: &prefix_sha256,
        mbr_disk_signature: mbr.disk_signature,
        partitions: &partitions,
    })?;

    Ok(ReadOnlyAuditReceipt {
        format_version: READ_ONLY_AUDIT_FORMAT_VERSION,
        audit_id: audit_id.to_owned(),
        profile_id: profile.profile_id.clone(),
        profile_sha256: profile_file_sha256.to_owned(),
        tool_version: tool_version.to_owned(),
        tool_sha256: tool_sha256.to_owned(),
        hardware_target: profile.target.clone(),
        layout_id,
        candidate,
        partition_scheme: profile.partition_scheme,
        prefix_size: profile.prefix.size,
        prefix_sha256,
        mbr_disk_signature: mbr.disk_signature,
        partitions,
        media_access: MediaAccess::ReadOnly,
        ejected: false,
    })
}

fn verify_partitions(
    profile: &CardProfile,
    observations: &[PartitionObservation],
    mbr: &MbrObservation,
) -> Result<Vec<VerifiedPartition>> {
    if observations.len() != profile.partitions.len()
        || mbr.partitions.len() != profile.partitions.len()
    {
        return Err(Error::InvalidData(
            "observed partition count does not match profile".into(),
        ));
    }

    let mut observed_by_number = BTreeMap::new();
    for observed in observations {
        if observed.number == 0
            || observed.size == 0
            || observed.offset % u64::from(profile.sector_size) != 0
            || observed.size % u64::from(profile.sector_size) != 0
            || observed.offset > profile.whole_size
            || observed.size > profile.whole_size - observed.offset
            || observed_by_number
                .insert(observed.number, observed)
                .is_some()
        {
            return Err(Error::InvalidData(
                "platform partition observations are invalid".into(),
            ));
        }
        validate_observed_identifiers(&observed.identifiers)?;
    }
    let mbr_by_number: BTreeMap<_, _> = mbr
        .partitions
        .iter()
        .map(|partition| (partition.number, partition))
        .collect();

    let mut verified = Vec::with_capacity(profile.partitions.len());
    let mut ordered: Vec<_> = profile.partitions.iter().collect();
    ordered.sort_by_key(|partition| partition.number);
    for expected in ordered {
        let observed = observed_by_number.get(&expected.number).ok_or_else(|| {
            Error::InvalidData(format!("partition {} was not observed", expected.number))
        })?;
        let mbr_partition = mbr_by_number.get(&expected.number).ok_or_else(|| {
            Error::InvalidData(format!(
                "partition {} is absent from the MBR",
                expected.number
            ))
        })?;
        if observed.offset != expected.offset
            || observed.size != expected.size
            || mbr_partition.offset != expected.offset
            || mbr_partition.size != expected.size
        {
            return Err(Error::InvalidData(format!(
                "partition {} geometry does not match profile",
                expected.number
            )));
        }
        let expected_mbr = expected.mbr.as_ref().ok_or_else(|| {
            Error::InvalidData(format!(
                "MBR profile partition {} has no MBR identity",
                expected.number
            ))
        })?;
        if mbr_partition.bootable != expected_mbr.bootable
            || mbr_partition.type_code != expected_mbr.type_code
        {
            return Err(Error::InvalidData(format!(
                "partition {} MBR identity does not match profile",
                expected.number
            )));
        }

        let filesystem = match (&expected.filesystem, &observed.filesystem) {
            (Some(expected), Some(actual))
                if canonical_filesystem(expected)? == canonical_filesystem(actual)? =>
            {
                Some(canonical_filesystem(expected)?)
            }
            (Some(_), _) => {
                return Err(Error::InvalidData(format!(
                    "partition {} filesystem does not match profile",
                    expected.number
                )));
            }
            (None, _) => None,
        };

        let mut identifiers = BTreeMap::new();
        for (key, expected_value) in &expected.identifiers {
            validate_identifier_key(key)?;
            let expected_value = canonical_identifier(key, expected_value)?;
            let actual_value = if key == "partuuid" {
                let derived = canonical_identifier(key, &mbr_partition.partuuid)?;
                if let Some(observed_value) = observed.identifiers.get(key) {
                    if canonical_identifier(key, observed_value)? != derived {
                        return Err(Error::InvalidData(format!(
                            "partition {} observed PARTUUID disagrees with MBR",
                            expected.number
                        )));
                    }
                }
                derived
            } else {
                let observed_value = observed.identifiers.get(key).ok_or_else(|| {
                    Error::InvalidData(format!(
                        "partition {} is missing identifier {key}",
                        expected.number
                    ))
                })?;
                canonical_identifier(key, observed_value)?
            };
            if actual_value != expected_value {
                return Err(Error::InvalidData(format!(
                    "partition {} identifier {key} does not match profile",
                    expected.number
                )));
            }
            identifiers.insert(key.clone(), actual_value);
        }
        verified.push(VerifiedPartition {
            role: expected.role,
            number: expected.number,
            offset: expected.offset,
            size: expected.size,
            mbr_bootable: mbr_partition.bootable,
            mbr_type_code: mbr_partition.type_code,
            filesystem,
            identifiers,
        });
    }
    Ok(verified)
}

fn hash_exact_range<S: ReadOnlyMediaSession>(
    session: &mut S,
    offset: u64,
    length: u64,
) -> Result<String> {
    let mut hasher = Sha256::new();
    let buffer_length = usize::try_from(length)
        .unwrap_or(READ_BUFFER_SIZE)
        .min(READ_BUFFER_SIZE);
    let mut buffer = vec![0_u8; buffer_length];
    let mut completed = 0_u64;
    while completed < length {
        let count = usize::try_from((length - completed).min(buffer.len() as u64))
            .expect("bounded read chunk fits usize");
        let read_offset = offset
            .checked_add(completed)
            .ok_or_else(|| Error::InvalidData("raw read offset overflow".into()))?;
        session.read_exact_at(read_offset, &mut buffer[..count])?;
        hasher.update(&buffer[..count]);
        completed += count as u64;
    }
    Ok(hex_digest(hasher.finalize()))
}

struct LayoutIdentityInput<'a> {
    profile_id: &'a str,
    profile_sha256: &'a str,
    hardware_target: &'a str,
    candidate: &'a DiscoveryCandidate,
    partition_scheme: PartitionScheme,
    prefix_size: u64,
    prefix_sha256: &'a str,
    mbr_disk_signature: u32,
    partitions: &'a [VerifiedPartition],
}

fn compute_layout_id(input: LayoutIdentityInput<'_>) -> Result<String> {
    crate::model::validate_id(input.profile_id, "profile_id")?;
    validate_bounded_text(input.hardware_target, "hardware_target", 128)?;
    if !is_sha256(input.profile_sha256) || !is_sha256(input.prefix_sha256) {
        return Err(Error::InvalidData(
            "cannot compute layout identity from invalid prefix digest".into(),
        ));
    }
    let mut hasher = Sha256::new();
    hasher.update(LAYOUT_ID_DOMAIN);
    hash_text(&mut hasher, input.profile_id)?;
    hash_text(&mut hasher, input.profile_sha256)?;
    hash_text(&mut hasher, input.hardware_target)?;
    hash_u64(&mut hasher, input.candidate.size);
    hash_u32(&mut hasher, input.candidate.sector_size);
    hasher.update(match input.partition_scheme {
        PartitionScheme::Mbr => b"mbr".as_slice(),
        PartitionScheme::Gpt => b"gpt".as_slice(),
    });
    hash_u64(&mut hasher, input.prefix_size);
    hash_text(&mut hasher, input.prefix_sha256)?;
    hash_u32(&mut hasher, input.mbr_disk_signature);
    hash_u32(
        &mut hasher,
        u32::try_from(input.partitions.len())
            .map_err(|_| Error::InvalidData("too many partitions for layout identity".into()))?,
    );
    for partition in input.partitions {
        hash_u32(&mut hasher, partition.number);
        hash_u64(&mut hasher, partition.offset);
        hash_u64(&mut hasher, partition.size);
        hasher.update([u8::from(partition.mbr_bootable)]);
        hasher.update([partition.mbr_type_code]);
        hash_text(&mut hasher, role_name(partition.role))?;
        hash_text(&mut hasher, partition.filesystem.as_deref().unwrap_or(""))?;
        hash_u32(
            &mut hasher,
            u32::try_from(partition.identifiers.len()).map_err(|_| {
                Error::InvalidData("too many identifiers for layout identity".into())
            })?,
        );
        for (key, value) in &partition.identifiers {
            hash_text(&mut hasher, key)?;
            hash_text(&mut hasher, value)?;
        }
    }
    Ok(format!(
        "r46h-profile-bound-layout-v1:{}",
        hex_digest(hasher.finalize())
    ))
}

fn hash_u32(hasher: &mut Sha256, value: u32) {
    hasher.update(value.to_be_bytes());
}

fn hash_u64(hasher: &mut Sha256, value: u64) {
    hasher.update(value.to_be_bytes());
}

fn hash_text(hasher: &mut Sha256, value: &str) -> Result<()> {
    let length = u32::try_from(value.len())
        .map_err(|_| Error::InvalidData("layout identity field is too long".into()))?;
    hash_u32(hasher, length);
    hasher.update(value.as_bytes());
    Ok(())
}

fn role_name(role: PartitionRole) -> &'static str {
    match role {
        PartitionRole::Boot => "boot",
        PartitionRole::Root => "root",
        PartitionRole::Easyroms => "easyroms",
    }
}

fn canonical_filesystem(value: &str) -> Result<String> {
    let canonical = value.to_ascii_lowercase();
    validate_bounded_text(&canonical, "filesystem", 64)?;
    if canonical != value.trim().to_ascii_lowercase()
        || !canonical.bytes().all(|byte| {
            byte.is_ascii_lowercase()
                || byte.is_ascii_digit()
                || matches!(byte, b'.' | b'_' | b'+' | b'-')
        })
    {
        return Err(Error::InvalidData(
            "filesystem contains surrounding whitespace".into(),
        ));
    }
    Ok(canonical)
}

fn validate_observed_identifiers(identifiers: &BTreeMap<String, String>) -> Result<()> {
    for (key, value) in identifiers {
        validate_identifier_key(key)?;
        canonical_identifier(key, value)?;
    }
    Ok(())
}

fn validate_identifier_key(key: &str) -> Result<()> {
    let valid = !key.is_empty()
        && key.len() <= 64
        && key.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        });
    if valid {
        Ok(())
    } else {
        Err(Error::InvalidData(
            "partition identifier key is invalid".into(),
        ))
    }
}

fn canonical_identifier(key: &str, value: &str) -> Result<String> {
    validate_bounded_text(value, "partition identifier", 128)?;
    if value != value.trim() {
        return Err(Error::InvalidData(
            "partition identifier contains surrounding whitespace".into(),
        ));
    }
    match key {
        "partuuid" => {
            let canonical = value.to_ascii_lowercase();
            let bytes = canonical.as_bytes();
            if bytes.len() != 11
                || bytes[8] != b'-'
                || !bytes[..8].iter().all(u8::is_ascii_hexdigit)
                || !bytes[9..].iter().all(u8::is_ascii_digit)
            {
                return Err(Error::InvalidData("PARTUUID is invalid".into()));
            }
            Ok(canonical)
        }
        "volume_uuid" => {
            if value.len() < 4
                || !value
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() || byte == b'-')
                || value.starts_with('-')
                || value.ends_with('-')
                || value.contains("--")
            {
                return Err(Error::InvalidData("volume UUID is invalid".into()));
            }
            Ok(value.to_ascii_uppercase())
        }
        _ => Ok(value.to_owned()),
    }
}

fn validate_bounded_text(value: &str, field: &str, maximum: usize) -> Result<()> {
    if value.is_empty()
        || value.len() > maximum
        || value.chars().any(char::is_control)
        || value != value.trim()
    {
        Err(Error::InvalidData(format!("{field} is invalid")))
    } else {
        Ok(())
    }
}

fn valid_layout_id(value: &str) -> bool {
    value
        .strip_prefix("r46h-profile-bound-layout-v1:")
        .is_some_and(is_sha256)
}

fn hex_digest(bytes: impl AsRef<[u8]>) -> String {
    use std::fmt::Write;

    let bytes = bytes.as_ref();
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{FORMAT_VERSION, Partition, Prefix};

    struct MemorySession {
        candidate: DiscoveryCandidate,
        partitions: Vec<PartitionObservation>,
        media: Vec<u8>,
        fail_read: bool,
        fail_eject: bool,
        eject_attempts: usize,
    }

    impl ReadOnlyMediaSession for MemorySession {
        fn candidate(&self) -> &DiscoveryCandidate {
            &self.candidate
        }

        fn partitions(&self) -> &[PartitionObservation] {
            &self.partitions
        }

        fn read_exact_at(&mut self, offset: u64, buffer: &mut [u8]) -> Result<()> {
            if self.fail_read {
                return Err(Error::InvalidData("injected read failure".into()));
            }
            let start = usize::try_from(offset)
                .map_err(|_| Error::InvalidData("test offset overflow".into()))?;
            let end = start
                .checked_add(buffer.len())
                .ok_or_else(|| Error::InvalidData("test read overflow".into()))?;
            let source = self
                .media
                .get(start..end)
                .ok_or_else(|| Error::InvalidData("test short read".into()))?;
            buffer.copy_from_slice(source);
            Ok(())
        }

        fn eject(&mut self) -> Result<()> {
            self.eject_attempts += 1;
            if self.fail_eject {
                Err(Error::InvalidData("injected eject failure".into()))
            } else {
                Ok(())
            }
        }
    }

    fn audit(
        session: &mut MemorySession,
        profile: &CardProfile,
        audit_id: &str,
    ) -> Result<ReadOnlyAuditReceipt> {
        let file_sha256 = profile_file_digest(profile);
        audit_and_eject(
            session,
            profile,
            audit_id,
            &file_sha256,
            env!("CARGO_PKG_VERSION"),
            &digest(b"test-tool"),
        )
    }

    fn profile_file_digest(profile: &CardProfile) -> String {
        digest(&serde_json::to_vec_pretty(profile).unwrap())
    }

    #[test]
    fn profile_bound_audit_normalizes_uuid_and_derives_partuuid() {
        let (profile, mut session) = fixture();
        session.partitions[0].identifiers.insert(
            "volume_uuid".into(),
            "abcdef01-2345-6789-abcd-ef0123456789".into(),
        );
        session.partitions[1]
            .identifiers
            .insert("partuuid".into(), "1234ABCD-02".into());

        let receipt = audit(&mut session, &profile, "audit-01").unwrap();

        assert!(receipt.ejected);
        assert_eq!(session.eject_attempts, 1);
        assert_eq!(receipt.media_access, MediaAccess::ReadOnly);
        assert_eq!(receipt.hardware_target, "R46H-TEST");
        assert_eq!(receipt.profile_sha256, profile_file_digest(&profile));
        assert_eq!(
            receipt.partitions[0].identifiers["volume_uuid"],
            "ABCDEF01-2345-6789-ABCD-EF0123456789"
        );
        assert_eq!(receipt.partitions[1].identifiers["partuuid"], "1234abcd-02");
        assert!(valid_layout_id(&receipt.layout_id));
        receipt.validate().unwrap();
        receipt
            .validate_against(
                &profile,
                &profile_file_digest(&profile),
                env!("CARGO_PKG_VERSION"),
                &digest(b"test-tool"),
            )
            .unwrap();

        let encoded = serde_json::to_value(&receipt).unwrap();
        assert!(encoded.get("safe_to_boot").is_none());
        assert!(encoded.get("write_plan").is_none());
    }

    #[test]
    fn layout_identity_matches_python_golden_vector() {
        let candidate = DiscoveryCandidate {
            platform: "macos".into(),
            attachment_id: "macos-iomedia-v1:abc".into(),
            physical_store_id: "ioreg:1".into(),
            display_path: "/dev/rdisk-test-placeholder".into(),
            transport: "USB".into(),
            size: 4096,
            sector_size: 512,
            whole: true,
            internal: false,
            removable: true,
            ejectable: true,
            writable: true,
            system_disk: false,
        };
        let partitions = vec![
            VerifiedPartition {
                role: PartitionRole::Boot,
                number: 1,
                offset: 512,
                size: 1024,
                mbr_bootable: false,
                mbr_type_code: 12,
                filesystem: Some("fat32".into()),
                identifiers: BTreeMap::from([("volume_uuid".into(), "A-B".into())]),
            },
            VerifiedPartition {
                role: PartitionRole::Root,
                number: 2,
                offset: 1536,
                size: 2560,
                mbr_bootable: false,
                mbr_type_code: 131,
                filesystem: Some("ext4".into()),
                identifiers: BTreeMap::from([("partuuid".into(), "00000001-02".into())]),
            },
        ];
        let actual = compute_layout_id(LayoutIdentityInput {
            profile_id: "hl-r46h-test-v2",
            profile_sha256: &"3".repeat(64),
            hardware_target: "HL-R46H-V22",
            candidate: &candidate,
            partition_scheme: PartitionScheme::Mbr,
            prefix_size: 512,
            prefix_sha256: &"1".repeat(64),
            mbr_disk_signature: 1,
            partitions: &partitions,
        })
        .unwrap();
        assert_eq!(
            actual,
            "r46h-profile-bound-layout-v1:\
             ed2f77b270ef0827f6ef69a32a227c76847cb23565ea95c8b7b3215a65687743"
        );
    }

    #[test]
    fn external_profile_and_tool_bindings_are_required() {
        let (profile, mut session) = fixture();
        let receipt = audit(&mut session, &profile, "binding-check").unwrap();
        let profile_sha = profile_file_digest(&profile);
        let tool_sha = digest(b"test-tool");

        receipt
            .validate_against(&profile, &profile_sha, env!("CARGO_PKG_VERSION"), &tool_sha)
            .unwrap();

        let mut tampered = receipt.clone();
        tampered.profile_id = "other-profile-v2".into();
        assert!(
            tampered
                .validate_against(&profile, &profile_sha, env!("CARGO_PKG_VERSION"), &tool_sha,)
                .is_err()
        );
        let mut tampered = receipt.clone();
        tampered.tool_sha256 = "f".repeat(64);
        assert!(
            tampered
                .validate_against(&profile, &profile_sha, env!("CARGO_PKG_VERSION"), &tool_sha,)
                .is_err()
        );
        let mut tampered = receipt;
        tampered.partitions[1]
            .identifiers
            .insert("partuuid".into(), "deadbeef-02".into());
        assert!(tampered.validate().is_err());
    }

    #[test]
    fn mbr_boot_flag_and_type_code_are_profile_bound() {
        let (mut profile, mut session) = fixture();
        profile.partitions[0].mbr.as_mut().unwrap().type_code = 0x0b;
        assert!(audit(&mut session, &profile, "wrong-type").is_err());

        let (mut profile, mut session) = fixture();
        profile.partitions[0].mbr.as_mut().unwrap().bootable = true;
        assert!(audit(&mut session, &profile, "wrong-boot-flag").is_err());
    }

    #[test]
    fn macos_readonly_profile_subset_is_fail_closed_before_media_access() {
        let (profile, _) = fixture();
        validate_macos_readonly_profile(&profile).unwrap();

        let mut missing_mbr = profile.clone();
        missing_mbr.partitions[0].mbr = None;
        assert!(validate_macos_readonly_profile(&missing_mbr).is_err());

        let mut out_of_order = profile.clone();
        out_of_order.partitions.swap(0, 1);
        assert!(validate_macos_readonly_profile(&out_of_order).is_err());

        let mut unsupported_filesystem = profile.clone();
        unsupported_filesystem.partitions[0].filesystem = Some("hfs".into());
        assert!(validate_macos_readonly_profile(&unsupported_filesystem).is_err());

        let mut noncanonical_identifier = profile;
        noncanonical_identifier.partitions[1]
            .identifiers
            .insert("partuuid".into(), "1234ABCD-02".into());
        assert!(validate_macos_readonly_profile(&noncanonical_identifier).is_err());

        let (mut missing_role_identity, _) = fixture();
        missing_role_identity.partitions[2].identifiers.clear();
        assert!(validate_macos_readonly_profile(&missing_role_identity).is_err());

        let (mut wrong_partuuid_suffix, _) = fixture();
        wrong_partuuid_suffix.partitions[1]
            .identifiers
            .insert("partuuid".into(), "1234abcd-03".into());
        assert!(validate_macos_readonly_profile(&wrong_partuuid_suffix).is_err());
    }

    #[test]
    fn exact_end_boundary_passes_and_out_of_bounds_observation_fails() {
        let (profile, mut session) = fixture();
        assert_eq!(
            profile.partitions.last().unwrap().offset + profile.partitions.last().unwrap().size,
            profile.whole_size
        );
        audit(&mut session, &profile, "boundary-ok").unwrap();

        let (profile, mut session) = fixture();
        session.partitions[2].size += 512;
        assert!(audit(&mut session, &profile, "boundary-bad").is_err());
        assert_eq!(session.eject_attempts, 1);
    }

    #[test]
    fn malformed_mbr_variants_are_rejected() {
        let (_, session) = fixture();
        let mut sector0 = session.media[..512].to_vec();
        sector0[510] = 0;
        assert!(parse_mbr_sector0(&sector0, 512).is_err());

        let (_, session) = fixture();
        let mut sector0 = session.media[..512].to_vec();
        sector0[440..444].fill(0);
        assert!(parse_mbr_sector0(&sector0, 512).is_err());

        let (_, session) = fixture();
        let mut sector0 = session.media[..512].to_vec();
        sector0[446] = 0x7f;
        assert!(parse_mbr_sector0(&sector0, 512).is_err());
        assert!(matches!(
            parse_mbr_sector0(&session.media[..512], 4096),
            Err(Error::Unsupported(_))
        ));
    }

    #[test]
    fn mbr_geometry_and_extra_partition_are_rejected() {
        let (profile, mut session) = fixture();
        put_u32_le(&mut session.media, 446 + 8, 2);
        let mut changed_profile = profile.clone();
        changed_profile.prefix.sha256 = digest(&session.media[..512]);
        assert!(audit(&mut session, &changed_profile, "bad-geometry").is_err());

        let (mut profile, mut session) = fixture();
        put_partition(&mut session.media, 4, 0x83, 7, 1);
        profile.prefix.sha256 = digest(&session.media[..512]);
        assert!(audit(&mut session, &profile, "extra-partition").is_err());
    }

    #[test]
    fn mismatched_prefix_uuid_and_partuuid_are_rejected_and_ejected() {
        let (profile, mut session) = fixture();
        session.media[1] ^= 1;
        assert!(audit(&mut session, &profile, "bad-prefix").is_err());
        assert_eq!(session.eject_attempts, 1);

        let (profile, mut session) = fixture();
        session.partitions[0].identifiers.insert(
            "volume_uuid".into(),
            "00000000-2345-6789-ABCD-EF0123456789".into(),
        );
        assert!(audit(&mut session, &profile, "bad-uuid").is_err());

        let (profile, mut session) = fixture();
        session.partitions[1]
            .identifiers
            .insert("partuuid".into(), "deadbeef-02".into());
        assert!(audit(&mut session, &profile, "bad-partuuid").is_err());
    }

    #[test]
    fn read_and_eject_failures_never_mint_a_receipt() {
        let (profile, mut session) = fixture();
        session.fail_read = true;
        assert!(audit(&mut session, &profile, "read-failure").is_err());
        assert_eq!(session.eject_attempts, 1);

        let (profile, mut session) = fixture();
        assert!(
            audit_and_eject(
                &mut session,
                &profile,
                "bad-binding",
                "not-a-digest",
                env!("CARGO_PKG_VERSION"),
                &digest(b"test-tool"),
            )
            .is_err()
        );
        assert_eq!(session.eject_attempts, 1);

        let (profile, mut session) = fixture();
        session.fail_read = true;
        session.fail_eject = true;
        let error = audit(&mut session, &profile, "double-failure")
            .unwrap_err()
            .to_string();
        assert!(error.contains("audit failed"));
        assert!(error.contains("eject also failed"));

        let (profile, mut session) = fixture();
        session.fail_eject = true;
        assert!(audit(&mut session, &profile, "eject-failure").is_err());
        assert_eq!(session.eject_attempts, 1);
    }

    #[test]
    fn duplicate_layout_ids_are_rejected() {
        let (profile, mut first) = fixture();
        let first_receipt = audit(&mut first, &profile, "first").unwrap();
        let (profile, mut second) = fixture();
        second.candidate.attachment_id = "macos-iomedia:2".into();
        second.candidate.display_path = "/dev/disk99".into();
        let second_receipt = audit(&mut second, &profile, "second").unwrap();
        assert_eq!(first_receipt.layout_id, second_receipt.layout_id);
        assert!(ensure_unique_layout_ids([&first_receipt, &second_receipt]).is_err());
        ensure_unique_layout_ids([&first_receipt]).unwrap();
    }

    #[test]
    fn strict_receipt_rejects_write_claims_and_unknown_nested_fields() {
        let (profile, mut session) = fixture();
        let receipt = audit(&mut session, &profile, "strict-json").unwrap();
        let mut value = serde_json::to_value(receipt).unwrap();
        value
            .as_object_mut()
            .unwrap()
            .insert("safe_to_boot".into(), serde_json::Value::Bool(true));
        assert!(serde_json::from_value::<ReadOnlyAuditReceipt>(value).is_err());

        let (profile, mut session) = fixture();
        let receipt = audit(&mut session, &profile, "nested-json").unwrap();
        let mut value = serde_json::to_value(receipt).unwrap();
        value["candidate"]["unknown"] = serde_json::Value::Bool(true);
        assert!(serde_json::from_value::<ReadOnlyAuditReceipt>(value).is_err());

        let (profile, mut session) = fixture();
        let mut receipt = audit(&mut session, &profile, "tampered-id").unwrap();
        receipt.layout_id = format!("r46h-profile-bound-layout-v1:{}", "0".repeat(64));
        assert!(receipt.validate().is_err());

        let (profile, mut session) = fixture();
        let mut receipt = audit(&mut session, &profile, "partition-order").unwrap();
        receipt.partitions.swap(0, 1);
        receipt.layout_id = compute_layout_id(LayoutIdentityInput {
            profile_id: &receipt.profile_id,
            profile_sha256: &receipt.profile_sha256,
            hardware_target: &receipt.hardware_target,
            candidate: &receipt.candidate,
            partition_scheme: receipt.partition_scheme,
            prefix_size: receipt.prefix_size,
            prefix_sha256: &receipt.prefix_sha256,
            mbr_disk_signature: receipt.mbr_disk_signature,
            partitions: &receipt.partitions,
        })
        .unwrap();
        assert!(receipt.validate().is_err());
    }

    #[test]
    fn attachment_safety_and_exact_geometry_are_required() {
        let (profile, mut session) = fixture();
        session.candidate.internal = true;
        assert!(audit(&mut session, &profile, "internal").is_err());

        let (profile, mut session) = fixture();
        session.candidate.size -= 512;
        assert!(audit(&mut session, &profile, "wrong-size").is_err());

        let (profile, mut session) = fixture();
        session.candidate.writable = false;
        audit(&mut session, &profile, "read-only-card").unwrap();
    }

    fn fixture() -> (CardProfile, MemorySession) {
        let mut media = vec![0_u8; 4096];
        media[440..444].copy_from_slice(&0x1234_abcd_u32.to_le_bytes());
        put_partition(&mut media, 1, 0x0c, 1, 2);
        put_partition(&mut media, 2, 0x83, 3, 2);
        put_partition(&mut media, 3, 0x07, 5, 3);
        media[510..512].copy_from_slice(&[0x55, 0xaa]);

        let profile = CardProfile {
            format_version: FORMAT_VERSION,
            profile_id: "readonly-fixture-v2".into(),
            target: "R46H-TEST".into(),
            whole_size: 4096,
            sector_size: 512,
            partition_scheme: PartitionScheme::Mbr,
            prefix: Prefix {
                size: 512,
                sha256: digest(&media[..512]),
            },
            partitions: vec![
                Partition {
                    role: PartitionRole::Boot,
                    number: 1,
                    offset: 512,
                    size: 1024,
                    mbr: Some(crate::model::MbrPartitionIdentity {
                        bootable: false,
                        type_code: 0x0c,
                    }),
                    filesystem: Some("fat32".into()),
                    identifiers: BTreeMap::from([(
                        "volume_uuid".into(),
                        "ABCDEF01-2345-6789-ABCD-EF0123456789".into(),
                    )]),
                },
                Partition {
                    role: PartitionRole::Root,
                    number: 2,
                    offset: 1536,
                    size: 1024,
                    mbr: Some(crate::model::MbrPartitionIdentity {
                        bootable: false,
                        type_code: 0x83,
                    }),
                    filesystem: Some("ext4".into()),
                    identifiers: BTreeMap::from([("partuuid".into(), "1234abcd-02".into())]),
                },
                Partition {
                    role: PartitionRole::Easyroms,
                    number: 3,
                    offset: 2560,
                    size: 1536,
                    mbr: Some(crate::model::MbrPartitionIdentity {
                        bootable: false,
                        type_code: 0x07,
                    }),
                    filesystem: Some("exfat".into()),
                    identifiers: BTreeMap::from([(
                        "volume_uuid".into(),
                        "87654321-4321-6789-ABCD-EF0123456789".into(),
                    )]),
                },
            ],
        };
        profile.validate().unwrap();

        let partitions = vec![
            PartitionObservation {
                number: 1,
                offset: 512,
                size: 1024,
                filesystem: Some("FAT32".into()),
                identifiers: BTreeMap::from([(
                    "volume_uuid".into(),
                    "ABCDEF01-2345-6789-ABCD-EF0123456789".into(),
                )]),
            },
            PartitionObservation {
                number: 2,
                offset: 1536,
                size: 1024,
                filesystem: Some("ext4".into()),
                identifiers: BTreeMap::new(),
            },
            PartitionObservation {
                number: 3,
                offset: 2560,
                size: 1536,
                filesystem: Some("exfat".into()),
                identifiers: BTreeMap::from([(
                    "volume_uuid".into(),
                    "87654321-4321-6789-ABCD-EF0123456789".into(),
                )]),
            },
        ];
        let candidate = DiscoveryCandidate {
            platform: "macos".into(),
            attachment_id: "macos-iomedia:1".into(),
            physical_store_id: "macos-store:1".into(),
            display_path: "/dev/disk42".into(),
            transport: "USB".into(),
            size: 4096,
            sector_size: 512,
            whole: true,
            internal: false,
            removable: true,
            ejectable: true,
            writable: true,
            system_disk: false,
        };
        (
            profile,
            MemorySession {
                candidate,
                partitions,
                media,
                fail_read: false,
                fail_eject: false,
                eject_attempts: 0,
            },
        )
    }

    fn put_partition(media: &mut [u8], number: usize, type_code: u8, lba: u32, sectors: u32) {
        let base = MBR_PARTITION_TABLE_OFFSET + (number - 1) * MBR_PARTITION_ENTRY_SIZE;
        media[base + 4] = type_code;
        put_u32_le(media, base + 8, lba);
        put_u32_le(media, base + 12, sectors);
    }

    fn put_u32_le(bytes: &mut [u8], offset: usize, value: u32) {
        bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }

    fn digest(bytes: &[u8]) -> String {
        hex_digest(Sha256::digest(bytes))
    }
}
