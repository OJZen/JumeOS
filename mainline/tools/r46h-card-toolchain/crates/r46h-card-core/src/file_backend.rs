use std::fs::File;
use std::io::{Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::backend::{
    DestructiveAuthorization, DestructiveAuthorizationIssuer, DestructiveAuthorizationRequest,
    DeviceIdentity, MediaSession, PlatformBackend, ReadSeek, WriteOutcome,
};
use crate::digest::StreamHasher;
use crate::error::{Error, Result};
use crate::file_identity;
use crate::model::{CardProfile, Partition};

#[derive(Debug, Clone)]
pub struct FileBackend {
    media_path: PathBuf,
    fail_after_bytes: Option<u64>,
    fail_flush: bool,
    fail_eject: bool,
    allow_destructive: bool,
    hardware_target: String,
    probe: Arc<FileBackendProbe>,
}

#[derive(Debug, Default)]
struct FileBackendProbe {
    authorization_attempts: AtomicU64,
    flush_attempts: AtomicU64,
    eject_attempts: AtomicU64,
}

impl FileBackend {
    pub fn new(media_path: impl Into<PathBuf>) -> Self {
        Self {
            media_path: media_path.into(),
            fail_after_bytes: None,
            fail_flush: false,
            fail_eject: false,
            allow_destructive: false,
            hardware_target: "R46H-TEST".into(),
            probe: Arc::new(FileBackendProbe::default()),
        }
    }

    pub fn with_hardware_target(mut self, target: impl Into<String>) -> Self {
        self.hardware_target = target.into();
        self
    }

    pub fn with_write_failure(mut self, fail_after_bytes: u64) -> Self {
        self.fail_after_bytes = Some(fail_after_bytes);
        self
    }

    pub fn with_flush_failure(mut self) -> Self {
        self.fail_flush = true;
        self
    }

    pub fn with_eject_failure(mut self) -> Self {
        self.fail_eject = true;
        self
    }

    /// Simulator-only opt-in. Native backends must replace this with explicit
    /// operator consent or a separately authenticated policy decision.
    pub fn with_destructive_authorization(mut self) -> Self {
        self.allow_destructive = true;
        self
    }

    pub fn authorization_attempts(&self) -> u64 {
        self.probe.authorization_attempts.load(Ordering::SeqCst)
    }

    pub fn flush_attempts(&self) -> u64 {
        self.probe.flush_attempts.load(Ordering::SeqCst)
    }

    pub fn eject_attempts(&self) -> u64 {
        self.probe.eject_attempts.load(Ordering::SeqCst)
    }

    fn inspect(&self) -> Result<DeviceIdentity> {
        let metadata = std::fs::symlink_metadata(&self.media_path)
            .map_err(|source| Error::io("inspect simulated media", source))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(Error::UnsafePath(self.media_path.clone()));
        }
        let canonical = self
            .media_path
            .canonicalize()
            .map_err(|source| Error::io("canonicalize simulated media", source))?;
        let file = file_identity::open_existing(&canonical, false)?;
        let opened = file_identity::identity(&file)?;
        if opened.size() != metadata.len() || opened.is_reparse_point() || opened.links() != 1 {
            return Err(Error::UnsafePath(canonical));
        }
        let token = opened.stable_token();
        Ok(DeviceIdentity {
            platform: "file-simulator".into(),
            stable_id: format!("file:{token}:{}", canonical.display()),
            hardware_target: self.hardware_target.clone(),
            physical_store_id: format!("simulated-file:{}", canonical.display()),
            display_path: canonical.display().to_string(),
            size: metadata.len(),
            sector_size: 512,
            removable: true,
            system_disk: false,
        })
    }
}

impl PlatformBackend for FileBackend {
    type Session = FileSession;

    fn platform_name(&self) -> &'static str {
        "file-simulator"
    }

    fn discover(&self) -> Result<Vec<DeviceIdentity>> {
        Ok(vec![self.inspect()?])
    }

    fn claim(
        &self,
        stable_id: &str,
        profile: CardProfile,
        writable: bool,
    ) -> Result<Self::Session> {
        let file = file_identity::open_existing(&self.media_path, writable)?;
        let opened_identity = file_identity::identity(&file)?;
        let identity = self.inspect()?;
        let opened_token = opened_identity.stable_token();
        let discovered_token = identity
            .stable_id
            .strip_prefix("file:")
            .and_then(|value| value.split_once(':'))
            .map(|(token, _)| token);
        if discovered_token != Some(opened_token.as_str()) {
            return Err(Error::InvalidData(
                "simulated media changed while it was claimed".into(),
            ));
        }
        if stable_id != identity.stable_id {
            return Err(Error::InvalidArgument(
                "simulated media stable ID mismatch".into(),
            ));
        }
        if identity.size != profile.whole_size {
            return Err(Error::InvalidData(
                "simulated media size does not match profile".into(),
            ));
        }
        Ok(FileSession {
            identity,
            profile,
            file,
            writable,
            fail_after_bytes: self.fail_after_bytes,
            fail_flush: self.fail_flush,
            fail_eject: self.fail_eject,
            allow_destructive: self.allow_destructive,
            probe: Arc::clone(&self.probe),
            ejected: false,
        })
    }
}

pub struct FileSession {
    identity: DeviceIdentity,
    profile: CardProfile,
    file: File,
    writable: bool,
    fail_after_bytes: Option<u64>,
    fail_flush: bool,
    fail_eject: bool,
    allow_destructive: bool,
    probe: Arc<FileBackendProbe>,
    ejected: bool,
}

impl MediaSession for FileSession {
    fn identity(&self) -> &DeviceIdentity {
        &self.identity
    }

    fn profile(&self) -> &CardProfile {
        &self.profile
    }

    fn reader(&mut self) -> Result<&mut dyn ReadSeek> {
        if self.ejected {
            return Err(Error::InvalidData(
                "simulated media has been ejected".into(),
            ));
        }
        Ok(&mut self.file)
    }

    fn write_partition(
        &mut self,
        partition: &Partition,
        source: &mut dyn ReadSeek,
        progress: &mut dyn FnMut(u64) -> Result<()>,
    ) -> Result<WriteOutcome> {
        if !self.writable || self.ejected {
            return Err(Error::Unsupported(
                "simulated session is read-only or ejected".into(),
            ));
        }
        source
            .seek(SeekFrom::Start(0))
            .map_err(|error| Error::io("seek pinned source for simulated write", error))?;
        self.file
            .seek(SeekFrom::Start(partition.offset))
            .map_err(|error| Error::io("seek simulated media for write", error))?;
        let mut buffer = vec![0_u8; 1024 * 1024];
        let mut written = 0_u64;
        let mut stream_hasher = StreamHasher::new();
        while written < partition.size {
            if self.fail_after_bytes.is_some_and(|limit| written >= limit) {
                return Err(Error::PartialWrite {
                    target_offset: partition.offset,
                    target_length: partition.size,
                    bytes_written: written,
                    message: "injected simulated write failure".into(),
                });
            }
            let remaining = partition.size - written;
            let chunk_size = remaining.min(buffer.len() as u64) as usize;
            let count =
                source
                    .read(&mut buffer[..chunk_size])
                    .map_err(|error| Error::PartialWrite {
                        target_offset: partition.offset,
                        target_length: partition.size,
                        bytes_written: written,
                        message: format!("read pinned source: {error}"),
                    })?;
            if count == 0 {
                return Err(Error::PartialWrite {
                    target_offset: partition.offset,
                    target_length: partition.size,
                    bytes_written: written,
                    message: "source image ended during write".into(),
                });
            }
            let write_count = if let Some(limit) = self.fail_after_bytes {
                count.min(limit.saturating_sub(written) as usize)
            } else {
                count
            };
            if write_count == 0 {
                return Err(Error::PartialWrite {
                    target_offset: partition.offset,
                    target_length: partition.size,
                    bytes_written: written,
                    message: "injected simulated write failure".into(),
                });
            }
            let mut chunk_written = 0_usize;
            while chunk_written < write_count {
                match self.file.write(&buffer[chunk_written..write_count]) {
                    Ok(0) => {
                        return Err(Error::PartialWrite {
                            target_offset: partition.offset,
                            target_length: partition.size,
                            bytes_written: written + chunk_written as u64,
                            message: "write simulated media returned zero bytes".into(),
                        });
                    }
                    Ok(bytes) => chunk_written += bytes,
                    Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                    Err(error) => {
                        return Err(Error::PartialWrite {
                            target_offset: partition.offset,
                            target_length: partition.size,
                            bytes_written: written + chunk_written as u64,
                            message: format!("write simulated media: {error}"),
                        });
                    }
                }
            }
            stream_hasher.update(&buffer[..write_count]);
            written += write_count as u64;
            if let Err(error) = progress(written) {
                return Err(Error::PartialWrite {
                    target_offset: partition.offset,
                    target_length: partition.size,
                    bytes_written: written,
                    message: format!("persist write progress: {error}"),
                });
            }
        }
        let mut trailing = [0_u8; 1];
        if source
            .read(&mut trailing)
            .map_err(|error| Error::PartialWrite {
                target_offset: partition.offset,
                target_length: partition.size,
                bytes_written: written,
                message: format!("check source image length: {error}"),
            })?
            != 0
        {
            return Err(Error::PartialWrite {
                target_offset: partition.offset,
                target_length: partition.size,
                bytes_written: written,
                message: "source image exceeds partition size".into(),
            });
        }
        Ok(WriteOutcome {
            bytes_written: written,
            source_stream_sha256: stream_hasher.finalize_hex(),
        })
    }

    fn flush_and_prepare_readback(&mut self) -> Result<()> {
        self.probe.flush_attempts.fetch_add(1, Ordering::SeqCst);
        if self.fail_flush {
            return Err(Error::Io {
                context: "injected simulated flush failure",
                source: std::io::Error::other("fault injection"),
            });
        }
        self.file
            .sync_all()
            .map_err(|error| Error::io("flush simulated media", error))
    }

    fn validate_external_path(&self, path: &std::path::Path) -> Result<()> {
        if !path.is_absolute() || path.file_name().is_none() {
            return Err(Error::UnsafePath(path.to_path_buf()));
        }
        let canonical = if path.exists() || path.is_symlink() {
            let metadata = std::fs::symlink_metadata(path)
                .map_err(|error| Error::io("inspect simulated external path", error))?;
            if metadata.file_type().is_symlink() {
                return Err(Error::UnsafePath(path.to_path_buf()));
            }
            path.canonicalize()
                .map_err(|error| Error::io("canonicalize simulated external path", error))?
        } else {
            let parent = path
                .parent()
                .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?;
            let metadata = std::fs::symlink_metadata(parent)
                .map_err(|error| Error::io("inspect simulated external parent", error))?;
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                return Err(Error::UnsafePath(path.to_path_buf()));
            }
            let canonical_parent = parent
                .canonicalize()
                .map_err(|error| Error::io("canonicalize simulated external parent", error))?;
            #[cfg(not(windows))]
            if canonical_parent != parent {
                return Err(Error::UnsafePath(path.to_path_buf()));
            }
            canonical_parent.join(path.file_name().expect("checked external file name"))
        };
        if canonical == std::path::Path::new(&self.identity.display_path) {
            return Err(Error::UnsafePath(canonical));
        }
        Ok(())
    }

    fn authorize_destructive(
        &mut self,
        request: &DestructiveAuthorizationRequest,
        issuer: DestructiveAuthorizationIssuer<'_>,
    ) -> Result<DestructiveAuthorization> {
        self.probe
            .authorization_attempts
            .fetch_add(1, Ordering::SeqCst);
        if !self.writable
            || self.ejected
            || request.target_stable_id() != self.identity.stable_id
            || request.physical_store_id() != self.identity.physical_store_id
            || request.ranges().is_empty()
        {
            return Err(Error::InvalidData(
                "simulated destructive authorization request is not bound to the claimed media"
                    .into(),
            ));
        }
        if !self.allow_destructive {
            return Err(Error::Unsupported(
                "simulator destructive authorization was not explicitly enabled".into(),
            ));
        }
        Ok(issuer.issue())
    }

    fn eject(&mut self) -> Result<()> {
        self.probe.eject_attempts.fetch_add(1, Ordering::SeqCst);
        if self.fail_eject {
            return Err(Error::Io {
                context: "injected simulated eject failure",
                source: std::io::Error::other("fault injection"),
            });
        }
        self.ejected = true;
        Ok(())
    }
}
