use std::io::{Read, Seek};
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::Result;
use crate::model::{CardProfile, Partition};

/// The exact destructive range shown to, or validated by, a trusted backend.
///
/// This is deliberately not deserializable. A write plan can request a
/// destructive operation, but it cannot manufacture backend approval for it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DestructiveRangeRequest {
    operation_id: String,
    offset: u64,
    length: u64,
    rationale: String,
}

impl DestructiveRangeRequest {
    pub(crate) fn new(operation_id: String, offset: u64, length: u64, rationale: String) -> Self {
        Self {
            operation_id,
            offset,
            length,
            rationale,
        }
    }

    pub fn operation_id(&self) -> &str {
        &self.operation_id
    }

    pub fn offset(&self) -> u64 {
        self.offset
    }

    pub fn length(&self) -> u64 {
        self.length
    }

    pub fn rationale(&self) -> &str {
        &self.rationale
    }
}

/// A transaction binding that a claimed-media backend must independently
/// authorize before the core can execute any disposable write.
///
/// All fields are private and the type has no serde implementation. Native
/// backends receive this value only from the transaction core after device,
/// profile, source, and baseline preflight have succeeded.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DestructiveAuthorizationRequest {
    target_stable_id: String,
    physical_store_id: String,
    profile_sha256: String,
    plan_sha256: String,
    transaction_nonce: String,
    ranges: Vec<DestructiveRangeRequest>,
}

impl DestructiveAuthorizationRequest {
    pub(crate) fn new(
        target_stable_id: String,
        physical_store_id: String,
        profile_sha256: String,
        plan_sha256: String,
        transaction_nonce: String,
        ranges: Vec<DestructiveRangeRequest>,
    ) -> Self {
        Self {
            target_stable_id,
            physical_store_id,
            profile_sha256,
            plan_sha256,
            transaction_nonce,
            ranges,
        }
    }

    pub fn target_stable_id(&self) -> &str {
        &self.target_stable_id
    }

    pub fn physical_store_id(&self) -> &str {
        &self.physical_store_id
    }

    pub fn profile_sha256(&self) -> &str {
        &self.profile_sha256
    }

    pub fn plan_sha256(&self) -> &str {
        &self.plan_sha256
    }

    pub fn transaction_nonce(&self) -> &str {
        &self.transaction_nonce
    }

    pub fn ranges(&self) -> &[DestructiveRangeRequest] {
        &self.ranges
    }
}

/// An in-process capability that cannot be constructed, cloned, or
/// deserialized by callers. It is minted only by the issuer passed to the
/// trusted backend's authorization callback.
#[derive(Debug)]
pub struct DestructiveAuthorization {
    request: DestructiveAuthorizationRequest,
}

impl DestructiveAuthorization {
    pub(crate) fn authorizes(&self, request: &DestructiveAuthorizationRequest) -> bool {
        self.request == *request
    }
}

/// A one-shot capability issuer. The core constructs it for one exact request;
/// a backend can consume it only while servicing `authorize_destructive`.
pub struct DestructiveAuthorizationIssuer<'a> {
    request: &'a DestructiveAuthorizationRequest,
}

impl<'a> DestructiveAuthorizationIssuer<'a> {
    pub(crate) fn new(request: &'a DestructiveAuthorizationRequest) -> Self {
        Self { request }
    }

    pub fn issue(self) -> DestructiveAuthorization {
        DestructiveAuthorization {
            request: self.request.clone(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DeviceIdentity {
    pub platform: String,
    pub stable_id: String,
    pub hardware_target: String,
    pub physical_store_id: String,
    pub display_path: String,
    pub size: u64,
    pub sector_size: u32,
    pub removable: bool,
    pub system_disk: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WriteOutcome {
    pub bytes_written: u64,
    pub source_stream_sha256: String,
}

pub trait ReadSeek: Read + Seek {}
impl<T: Read + Seek> ReadSeek for T {}

pub trait MediaSession {
    fn identity(&self) -> &DeviceIdentity;
    fn profile(&self) -> &CardProfile;
    fn reader(&mut self) -> Result<&mut dyn ReadSeek>;
    fn write_partition(
        &mut self,
        partition: &Partition,
        source: &mut dyn ReadSeek,
        progress: &mut dyn FnMut(u64) -> Result<()>,
    ) -> Result<WriteOutcome>;
    fn flush_and_prepare_readback(&mut self) -> Result<()>;
    fn validate_external_path(&self, path: &Path) -> Result<()>;
    /// Independently authorize one exact destructive request against the
    /// already-claimed device. Implementations must obtain consent or validate
    /// trusted policy outside the serialized write plan before consuming the
    /// issuer. Returning a capability for any other request is impossible.
    fn authorize_destructive(
        &mut self,
        request: &DestructiveAuthorizationRequest,
        issuer: DestructiveAuthorizationIssuer<'_>,
    ) -> Result<DestructiveAuthorization>;
    /// Release/eject the claimed medium. This must be attempted independently
    /// of flushing: callers may invoke it after a failed flush, and an
    /// implementation must not silently skip release for that reason.
    fn eject(&mut self) -> Result<()>;
}

pub trait PlatformBackend {
    type Session: MediaSession;

    fn platform_name(&self) -> &'static str;
    fn discover(&self) -> Result<Vec<DeviceIdentity>>;
    fn claim(&self, stable_id: &str, profile: CardProfile, writable: bool)
    -> Result<Self::Session>;
}
