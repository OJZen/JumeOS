use std::fs::File;
use std::io::{Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};

use crate::digest::hash_reader;
use crate::error::{Error, Result};
use crate::file_identity;
use crate::model::SourceImage;

pub struct SourceRoot {
    canonical: PathBuf,
}

pub struct PinnedSource {
    pub path: PathBuf,
    pub file: File,
    pub size: u64,
    pub sha256: String,
}

impl SourceRoot {
    pub fn open(path: &Path) -> Result<Self> {
        let metadata = std::fs::symlink_metadata(path)
            .map_err(|source| Error::io("inspect input root", source))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(Error::UnsafePath(path.to_path_buf()));
        }
        let canonical = path
            .canonicalize()
            .map_err(|source| Error::io("canonicalize input root", source))?;
        Ok(Self { canonical })
    }

    pub fn path(&self) -> &Path {
        &self.canonical
    }

    pub fn open_verified(&self, source: &SourceImage) -> Result<PinnedSource> {
        let relative = Path::new(&source.relative_path);
        if relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
        {
            return Err(Error::UnsafePath(relative.to_path_buf()));
        }
        let candidate = self.canonical.join(relative);
        let metadata = std::fs::symlink_metadata(&candidate)
            .map_err(|error| Error::io("inspect source image", error))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() != source.size
        {
            return Err(Error::UnsafePath(candidate));
        }
        let canonical = candidate
            .canonicalize()
            .map_err(|error| Error::io("canonicalize source image", error))?;
        if !canonical.starts_with(&self.canonical) {
            return Err(Error::UnsafePath(canonical));
        }
        let mut file = file_identity::open_existing(&canonical, false)?;
        let opened = file_identity::identity(&file)?;
        if opened.size() != metadata.len() || opened.links() != 1 || opened.is_reparse_point() {
            return Err(Error::UnsafePath(canonical));
        }
        let (digest, bytes) = hash_reader(&mut file)?;
        let after = file_identity::identity(&file)?;
        if opened != after {
            return Err(Error::InvalidData(format!(
                "source image {} changed while it was pinned",
                source.relative_path
            )));
        }
        if bytes != source.size || digest != source.sha256 {
            return Err(Error::InvalidData(format!(
                "source image {} digest mismatch",
                source.relative_path
            )));
        }
        file.seek(SeekFrom::Start(0))
            .map_err(|error| Error::io("rewind verified source image", error))?;
        Ok(PinnedSource {
            path: canonical,
            file,
            size: bytes,
            sha256: digest,
        })
    }
}
