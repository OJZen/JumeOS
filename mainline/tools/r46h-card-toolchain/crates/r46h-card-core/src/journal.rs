use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::error::{Error, Result};
use crate::receipt::TransactionReceipt;
use crate::transaction::Journal;

pub struct AppendOnlyJournal {
    path: PathBuf,
    sink: Box<dyn JournalSink>,
    sequence: u64,
    poisoned: bool,
}

impl AppendOnlyJournal {
    pub fn create(path: &Path) -> Result<Self> {
        let parent = safe_parent(path)?;
        let resolved = parent.join(
            path.file_name()
                .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?,
        );
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&resolved)
            .map_err(|error| Error::io("create transaction journal", error))?;
        file.sync_all()
            .map_err(|error| Error::io("initialize transaction journal", error))?;
        sync_directory(&parent)?;
        Ok(Self {
            path: resolved,
            sink: Box::new(file),
            sequence: 0,
            poisoned: false,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl Journal for AppendOnlyJournal {
    fn persist(&mut self, receipt: &TransactionReceipt) -> Result<()> {
        if self.poisoned {
            return Err(Error::InvalidData(
                "transaction journal is poisoned after an earlier persistence failure".into(),
            ));
        }
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or_else(|| Error::InvalidData("journal sequence overflow".into()))?;
        let event = JournalEvent {
            sequence: self.sequence,
            receipt,
        };
        let mut bytes = serde_json::to_vec(&event)?;
        bytes.push(b'\n');
        if let Err(error) = self
            .sink
            .write_all(&bytes)
            .and_then(|()| self.sink.sync_data())
        {
            self.poisoned = true;
            return Err(Error::io("append and flush transaction journal", error));
        }
        Ok(())
    }
}

pub struct EvidenceStore {
    root: PathBuf,
}

impl EvidenceStore {
    pub fn create(path: &Path) -> Result<Self> {
        let parent = safe_parent(path)?;
        let resolved = parent.join(
            path.file_name()
                .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?,
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            let mut builder = std::fs::DirBuilder::new();
            builder.mode(0o700);
            builder.create(&resolved).map_err(|error| {
                Error::io("reserve evidence directory without replacement", error)
            })?;
        }
        #[cfg(windows)]
        {
            std::fs::create_dir(&resolved).map_err(|error| {
                Error::io("reserve evidence directory without replacement", error)
            })?;
        }
        sync_directory(&parent)?;
        Ok(Self { root: resolved })
    }

    pub fn journal_path(&self) -> PathBuf {
        self.root.join("journal.jsonl")
    }

    pub fn finalize(&self, data: &[u8]) -> Result<String> {
        let receipt_path = self.root.join("receipt.json");
        let digest = publish_no_replace(&receipt_path, data)?;
        let complete = format!("receipt_sha256={digest}\n");
        publish_no_replace(&self.root.join("RECEIPT-COMPLETE"), complete.as_bytes())?;
        sync_directory(&self.root)?;
        Ok(digest)
    }

    pub fn path(&self) -> &Path {
        &self.root
    }
}

#[derive(serde::Serialize)]
struct JournalEvent<'a> {
    sequence: u64,
    receipt: &'a TransactionReceipt,
}

trait JournalSink: Write {
    fn sync_data(&mut self) -> std::io::Result<()>;
}

impl JournalSink for File {
    fn sync_data(&mut self) -> std::io::Result<()> {
        File::sync_data(self)
    }
}

pub fn publish_no_replace(path: &Path, data: &[u8]) -> Result<String> {
    let parent = safe_parent(path)?;
    let destination = parent.join(
        path.file_name()
            .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?,
    );
    let temporary = create_temporary_path(&parent, &destination)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|error| Error::io("create temporary final receipt", error))?;
    file.write_all(data)
        .map_err(|error| Error::io("write final receipt", error))?;
    file.sync_all()
        .map_err(|error| Error::io("flush final receipt", error))?;
    if let Err(error) = std::fs::hard_link(&temporary, &destination) {
        let _ = std::fs::remove_file(&temporary);
        return Err(Error::io(
            "publish final receipt without replacement",
            error,
        ));
    }
    sync_directory(&parent)?;
    std::fs::remove_file(&temporary)
        .map_err(|error| Error::io("remove temporary final receipt", error))?;
    sync_directory(&parent)?;
    let (digest, bytes) = crate::digest::hash_reader(&mut &*data)?;
    if bytes != data.len() as u64 {
        return Err(Error::InvalidData("receipt byte count changed".into()));
    }
    Ok(digest)
}

fn create_temporary_path(parent: &Path, destination: &Path) -> Result<PathBuf> {
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    let name = destination
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| Error::UnsafePath(destination.to_path_buf()))?;
    let time = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| Error::InvalidData("system clock is before Unix epoch".into()))?
        .as_nanos();
    let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
    Ok(parent.join(format!(
        ".{name}.tmp-{}-{time}-{sequence}",
        std::process::id()
    )))
}

fn safe_parent(path: &Path) -> Result<PathBuf> {
    if !path.is_absolute() {
        return Err(Error::UnsafePath(path.to_path_buf()));
    }
    let parent = path
        .parent()
        .ok_or_else(|| Error::UnsafePath(path.to_path_buf()))?;
    let metadata = std::fs::symlink_metadata(parent)
        .map_err(|error| Error::io("inspect evidence parent", error))?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata_is_reparse_point(&metadata)
        || path.file_name().is_none()
    {
        return Err(Error::UnsafePath(path.to_path_buf()));
    }
    let canonical = parent
        .canonicalize()
        .map_err(|error| Error::io("canonicalize evidence parent", error))?;
    #[cfg(not(windows))]
    if canonical != parent {
        return Err(Error::UnsafePath(parent.to_path_buf()));
    }
    Ok(canonical)
}

#[cfg(not(windows))]
fn metadata_is_reparse_point(_metadata: &std::fs::Metadata) -> bool {
    false
}

#[cfg(windows)]
fn metadata_is_reparse_point(metadata: &std::fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0000_0400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(unix)]
fn sync_directory(path: &Path) -> Result<()> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| Error::io("flush evidence directory", error))
}

#[cfg(windows)]
fn sync_directory(_path: &Path) -> Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;
    use std::io::{self, Write};
    use std::rc::Rc;

    use super::{AppendOnlyJournal, JournalSink};
    use crate::backend::DeviceIdentity;
    use crate::receipt::{EvidenceBindings, TransactionReceipt};
    use crate::transaction::Journal;

    struct PartialFailureSink {
        bytes: Vec<u8>,
        fail_after: usize,
        calls: Rc<Cell<usize>>,
    }

    struct SyncFailureSink {
        writes: Rc<Cell<usize>>,
        syncs: Rc<Cell<usize>>,
    }

    impl Write for PartialFailureSink {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.calls.set(self.calls.get() + 1);
            if self.bytes.len() >= self.fail_after {
                return Err(io::Error::other("injected journal failure"));
            }
            let count = bytes.len().min(self.fail_after - self.bytes.len());
            self.bytes.extend_from_slice(&bytes[..count]);
            Ok(count)
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl JournalSink for PartialFailureSink {
        fn sync_data(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Write for SyncFailureSink {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.writes.set(self.writes.get() + 1);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl JournalSink for SyncFailureSink {
        fn sync_data(&mut self) -> io::Result<()> {
            self.syncs.set(self.syncs.get() + 1);
            Err(io::Error::other("injected journal sync failure"))
        }
    }

    #[test]
    fn partial_append_poisons_journal_and_forbids_a_second_write() {
        let calls = Rc::new(Cell::new(0));
        let sink = PartialFailureSink {
            bytes: Vec::new(),
            fail_after: 13,
            calls: Rc::clone(&calls),
        };
        let mut journal = AppendOnlyJournal {
            path: "unused".into(),
            sink: Box::new(sink),
            sequence: 0,
            poisoned: false,
        };
        let receipt = test_receipt();

        let first = journal.persist(&receipt).unwrap_err().to_string();
        assert!(first.contains("append and flush transaction journal"));
        assert!(journal.poisoned);
        let calls_after_failure = calls.get();

        let second = journal.persist(&receipt).unwrap_err().to_string();
        assert!(second.contains("journal is poisoned"));
        assert_eq!(calls.get(), calls_after_failure);
    }

    #[test]
    fn failed_sync_poisons_journal_and_forbids_a_second_write() {
        let writes = Rc::new(Cell::new(0));
        let syncs = Rc::new(Cell::new(0));
        let sink = SyncFailureSink {
            writes: Rc::clone(&writes),
            syncs: Rc::clone(&syncs),
        };
        let mut journal = AppendOnlyJournal {
            path: "unused".into(),
            sink: Box::new(sink),
            sequence: 0,
            poisoned: false,
        };
        let receipt = test_receipt();

        assert!(journal.persist(&receipt).is_err());
        assert!(journal.poisoned);
        let calls_after_failure = (writes.get(), syncs.get());

        assert!(journal.persist(&receipt).is_err());
        assert_eq!((writes.get(), syncs.get()), calls_after_failure);
    }

    fn test_receipt() -> TransactionReceipt {
        TransactionReceipt::new(
            "journal-test".into(),
            "plan-test".into(),
            "profile-test".into(),
            EvidenceBindings {
                profile_sha256: "1".repeat(64),
                plan_sha256: "2".repeat(64),
                tool_version: "test".into(),
                tool_sha256: "3".repeat(64),
            },
            DeviceIdentity {
                platform: "test".into(),
                stable_id: "stable".into(),
                hardware_target: "R46H-TEST".into(),
                physical_store_id: "store".into(),
                display_path: "test".into(),
                size: 4096,
                sector_size: 512,
                removable: true,
                system_disk: false,
            },
            crate::model::VerificationMode::Quick,
        )
    }
}
