use crate::backend::{DeviceIdentity, PlatformBackend};
use crate::error::{Error, Result};
use crate::model::CardProfile;
use crate::readonly::{DiscoveryCandidate, ReadOnlyMediaSession, ReadOnlyPlatformBackend};

#[cfg(target_os = "macos")]
mod macos;

pub struct NativeBackend;

impl PlatformBackend for NativeBackend {
    type Session = DisabledNativeSession;

    fn platform_name(&self) -> &'static str {
        std::env::consts::OS
    }

    fn discover(&self) -> Result<Vec<DeviceIdentity>> {
        Err(Error::Unsupported(format!(
            "{} write-capable physical-media discovery is not enabled in toolchain v0.2",
            PlatformBackend::platform_name(self)
        )))
    }

    fn claim(
        &self,
        _stable_id: &str,
        _profile: CardProfile,
        _writable: bool,
    ) -> Result<Self::Session> {
        Err(Error::Unsupported(format!(
            "{} physical-media writes are not enabled in toolchain v0.2",
            PlatformBackend::platform_name(self)
        )))
    }
}

impl ReadOnlyPlatformBackend for NativeBackend {
    #[cfg(target_os = "macos")]
    type Session = macos::MacosReadOnlySession;
    #[cfg(not(target_os = "macos"))]
    type Session = DisabledNativeReadOnlySession;

    fn platform_name(&self) -> &'static str {
        std::env::consts::OS
    }

    fn discover_readonly(&self) -> Result<Vec<DiscoveryCandidate>> {
        #[cfg(target_os = "macos")]
        {
            macos::discover()
        }
        #[cfg(not(target_os = "macos"))]
        {
            Err(Error::Unsupported(format!(
                "{} read-only physical-media discovery is not enabled",
                ReadOnlyPlatformBackend::platform_name(self)
            )))
        }
    }

    fn validate_external_path(&self, attachment_id: &str, path: &std::path::Path) -> Result<()> {
        #[cfg(target_os = "macos")]
        {
            macos::validate_external_path(attachment_id, path)
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = (attachment_id, path);
            Err(Error::Unsupported(format!(
                "{} external-path validation is not enabled",
                ReadOnlyPlatformBackend::platform_name(self)
            )))
        }
    }

    fn claim_readonly(&self, attachment_id: &str) -> Result<Self::Session> {
        #[cfg(target_os = "macos")]
        {
            macos::claim(attachment_id)
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = attachment_id;
            Err(Error::Unsupported(format!(
                "{} read-only physical-media claim is not enabled",
                ReadOnlyPlatformBackend::platform_name(self)
            )))
        }
    }
}

pub struct DisabledNativeSession;

pub struct DisabledNativeReadOnlySession;

impl ReadOnlyMediaSession for DisabledNativeReadOnlySession {
    fn candidate(&self) -> &DiscoveryCandidate {
        unreachable!("disabled native read-only sessions cannot be constructed")
    }

    fn partitions(&self) -> &[crate::readonly::PartitionObservation] {
        unreachable!("disabled native read-only sessions cannot be constructed")
    }

    fn read_exact_at(&mut self, _offset: u64, _buffer: &mut [u8]) -> Result<()> {
        Err(Error::Unsupported(
            "native read-only session is disabled".into(),
        ))
    }

    fn eject(&mut self) -> Result<()> {
        Err(Error::Unsupported(
            "native read-only session is disabled".into(),
        ))
    }
}

impl crate::backend::MediaSession for DisabledNativeSession {
    fn identity(&self) -> &DeviceIdentity {
        unreachable!("disabled native sessions cannot be constructed")
    }

    fn profile(&self) -> &CardProfile {
        unreachable!("disabled native sessions cannot be constructed")
    }

    fn reader(&mut self) -> Result<&mut dyn crate::backend::ReadSeek> {
        Err(Error::Unsupported("native session is disabled".into()))
    }

    fn write_partition(
        &mut self,
        _partition: &crate::model::Partition,
        _source: &mut dyn crate::backend::ReadSeek,
        _progress: &mut dyn FnMut(u64) -> Result<()>,
    ) -> Result<crate::backend::WriteOutcome> {
        Err(Error::Unsupported("native session is disabled".into()))
    }

    fn flush_and_prepare_readback(&mut self) -> Result<()> {
        Err(Error::Unsupported("native session is disabled".into()))
    }

    fn validate_external_path(&self, _path: &std::path::Path) -> Result<()> {
        Err(Error::Unsupported("native session is disabled".into()))
    }

    fn authorize_destructive(
        &mut self,
        _request: &crate::backend::DestructiveAuthorizationRequest,
        _issuer: crate::backend::DestructiveAuthorizationIssuer<'_>,
    ) -> Result<crate::backend::DestructiveAuthorization> {
        Err(Error::Unsupported("native session is disabled".into()))
    }

    fn eject(&mut self) -> Result<()> {
        Err(Error::Unsupported("native session is disabled".into()))
    }
}
