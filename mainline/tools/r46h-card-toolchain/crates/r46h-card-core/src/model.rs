use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

use crate::{
    digest::is_sha256,
    error::{Error, Result},
};

pub const FORMAT_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CardProfile {
    pub format_version: u32,
    pub profile_id: String,
    pub target: String,
    pub whole_size: u64,
    pub sector_size: u32,
    pub partition_scheme: PartitionScheme,
    pub prefix: Prefix,
    pub partitions: Vec<Partition>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PartitionScheme {
    Mbr,
    Gpt,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Prefix {
    pub size: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Partition {
    pub role: PartitionRole,
    pub number: u32,
    pub offset: u64,
    pub size: u64,
    #[serde(default)]
    pub mbr: Option<MbrPartitionIdentity>,
    #[serde(default)]
    pub filesystem: Option<String>,
    #[serde(default)]
    pub identifiers: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MbrPartitionIdentity {
    pub bootable: bool,
    pub type_code: u8,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum PartitionRole {
    Boot,
    Root,
    Easyroms,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WritePlan {
    pub format_version: u32,
    pub plan_id: String,
    pub profile_id: String,
    pub target_stable_id: String,
    pub verification: VerificationMode,
    pub operations: Vec<WriteOperation>,
    pub unchanged_ranges: Vec<RangeAttestation>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum VerificationMode {
    Quick,
    Balanced,
    Full,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WriteOperation {
    pub id: String,
    pub partition: PartitionRole,
    pub source: SourceImage,
    pub target_before: TargetPrecondition,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum TargetPrecondition {
    ExactSha256 {
        sha256: String,
    },
    Disposable {
        destructive: bool,
        rationale: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SourceImage {
    pub relative_path: String,
    pub size: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RangeAttestation {
    pub id: String,
    pub offset: u64,
    pub length: u64,
    pub sha256_before: String,
}

impl CardProfile {
    pub fn validate(&self) -> Result<()> {
        if self.format_version != FORMAT_VERSION {
            return Err(Error::InvalidData(
                "profile format_version must be 2".into(),
            ));
        }
        validate_id(&self.profile_id, "profile_id")?;
        if self.target.is_empty() || self.target.len() > 128 {
            return Err(Error::InvalidData("profile target is invalid".into()));
        }
        if self.whole_size == 0 || self.sector_size < 512 || !self.sector_size.is_power_of_two() {
            return Err(Error::InvalidData(
                "profile media geometry is invalid".into(),
            ));
        }
        if self.whole_size % u64::from(self.sector_size) != 0
            || self.prefix.size == 0
            || self.prefix.size > self.whole_size
            || !is_sha256(&self.prefix.sha256)
        {
            return Err(Error::InvalidData("profile prefix is invalid".into()));
        }
        if self.partitions.is_empty() {
            return Err(Error::InvalidData("profile has no partitions".into()));
        }
        let mut roles = BTreeSet::new();
        let mut numbers = BTreeSet::new();
        let mut previous_end = 0_u64;
        let mut ordered: Vec<&Partition> = self.partitions.iter().collect();
        ordered.sort_by_key(|partition| partition.offset);
        if ordered
            .first()
            .is_some_and(|partition| self.prefix.size > partition.offset)
        {
            return Err(Error::InvalidData(
                "profile prefix overlaps a partition".into(),
            ));
        }
        for partition in ordered {
            if !roles.insert(partition.role)
                || !numbers.insert(partition.number)
                || partition.number == 0
                || partition.size == 0
                || partition.mbr.as_ref().is_some_and(|mbr| mbr.type_code == 0)
                || self.partition_scheme == PartitionScheme::Gpt && partition.mbr.is_some()
                || partition.offset % u64::from(self.sector_size) != 0
                || partition.size % u64::from(self.sector_size) != 0
                || partition.offset < previous_end
                || partition.offset > self.whole_size
                || partition.size > self.whole_size - partition.offset
            {
                return Err(Error::InvalidData("profile partitions are invalid".into()));
            }
            previous_end = partition.offset + partition.size;
        }
        Ok(())
    }

    pub fn partition(&self, role: PartitionRole) -> Result<&Partition> {
        self.partitions
            .iter()
            .find(|partition| partition.role == role)
            .ok_or_else(|| Error::InvalidData(format!("profile is missing {role:?}")))
    }
}

impl WritePlan {
    pub fn validate(&self, profile: &CardProfile) -> Result<()> {
        if self.format_version != FORMAT_VERSION {
            return Err(Error::InvalidData(
                "write plan format_version must be 2".into(),
            ));
        }
        validate_id(&self.plan_id, "plan_id")?;
        if self.profile_id != profile.profile_id
            || self.target_stable_id.trim().is_empty()
            || self.target_stable_id.len() > 512
            || self.operations.is_empty()
        {
            return Err(Error::InvalidData(
                "write plan header does not match profile".into(),
            ));
        }
        let mut operation_ids = BTreeSet::new();
        let mut partitions = BTreeSet::new();
        for operation in &self.operations {
            validate_id(&operation.id, "operation id")?;
            validate_relative_path(&operation.source.relative_path)?;
            let partition = profile.partition(operation.partition)?;
            if !operation_ids.insert(&operation.id)
                || !partitions.insert(operation.partition)
                || operation.source.size != partition.size
                || !is_sha256(&operation.source.sha256)
            {
                return Err(Error::InvalidData(format!(
                    "write operation {} is invalid",
                    operation.id
                )));
            }
            match &operation.target_before {
                TargetPrecondition::ExactSha256 { sha256 } if is_sha256(sha256) => {}
                TargetPrecondition::Disposable {
                    destructive: true,
                    rationale,
                } if !rationale.trim().is_empty() && rationale.len() <= 256 => {}
                _ => {
                    return Err(Error::InvalidData(format!(
                        "write operation {} has an invalid target precondition",
                        operation.id
                    )));
                }
            }
        }
        let mut attestations = BTreeSet::new();
        let mut protected_ranges = Vec::new();
        for attestation in &self.unchanged_ranges {
            validate_id(&attestation.id, "attestation id")?;
            if !attestations.insert(&attestation.id)
                || attestation.length == 0
                || attestation.offset > profile.whole_size
                || attestation.length > profile.whole_size - attestation.offset
                || attestation.offset % u64::from(profile.sector_size) != 0
                || attestation.length % u64::from(profile.sector_size) != 0
                || !is_sha256(&attestation.sha256_before)
            {
                return Err(Error::InvalidData(format!(
                    "range attestation {} is invalid",
                    attestation.id
                )));
            }
            protected_ranges.push((attestation.offset, attestation.offset + attestation.length));
        }
        protected_ranges.sort_unstable();
        for ranges in protected_ranges.windows(2) {
            if ranges[0].1 > ranges[1].0 {
                return Err(Error::InvalidData(
                    "unchanged range attestations overlap".into(),
                ));
            }
        }
        for operation in &self.operations {
            let partition = profile.partition(operation.partition)?;
            let write_start = partition.offset;
            let write_end = partition.offset + partition.size;
            if protected_ranges
                .iter()
                .any(|(start, end)| write_start < *end && *start < write_end)
            {
                return Err(Error::InvalidData(format!(
                    "unchanged range overlaps write operation {}",
                    operation.id
                )));
            }
        }
        if self.verification == VerificationMode::Full {
            self.validate_full_coverage(profile)?;
        }
        Ok(())
    }

    fn validate_full_coverage(&self, profile: &CardProfile) -> Result<()> {
        let mut ranges = Vec::new();
        for operation in &self.operations {
            let partition = profile.partition(operation.partition)?;
            ranges.push((partition.offset, partition.offset + partition.size, "write"));
        }
        for attestation in &self.unchanged_ranges {
            ranges.push((
                attestation.offset,
                attestation.offset + attestation.length,
                "unchanged",
            ));
        }
        ranges.sort_by_key(|range| range.0);
        let mut expected_offset = 0_u64;
        for (start, end, _) in ranges {
            if start != expected_offset || end <= start {
                return Err(Error::InvalidData(
                    "full verification ranges must cover the whole medium exactly once".into(),
                ));
            }
            expected_offset = end;
        }
        if expected_offset != profile.whole_size {
            return Err(Error::InvalidData(
                "full verification ranges do not reach the end of the medium".into(),
            ));
        }
        Ok(())
    }
}

pub fn validate_id(value: &str, field: &str) -> Result<()> {
    let valid = !value.is_empty()
        && value.len() <= 64
        && value.bytes().enumerate().all(|(index, byte)| {
            byte.is_ascii_lowercase()
                || byte.is_ascii_digit()
                || (index > 0 && matches!(byte, b'.' | b'_' | b'-'))
        });
    if valid {
        Ok(())
    } else {
        Err(Error::InvalidData(format!("{field} is invalid")))
    }
}

pub fn validate_relative_path(value: &str) -> Result<()> {
    if value.is_empty()
        || value.starts_with('/')
        || value.starts_with('\\')
        || value.contains('\\')
        || value.contains(':')
        || value.contains('\0')
        || value
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(Error::InvalidData(
            "source path must be a portable relative path".into(),
        ));
    }
    Ok(())
}
