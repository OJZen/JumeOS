use std::collections::{BTreeMap, BTreeSet};
use std::io::SeekFrom;
use std::path::Path;

use crate::backend::{
    DestructiveAuthorizationIssuer, DestructiveAuthorizationRequest, DestructiveRangeRequest,
    MediaSession,
};
use crate::digest::{hash_range, is_sha256};
use crate::error::{Error, Result};
use crate::model::{TargetPrecondition, VerificationMode, WriteOperation, WritePlan, validate_id};
use crate::receipt::{
    EvidenceBindings, FailureDisposition, FailureDispositionStep, OperationReceipt, OperationState,
    RangeReceipt, ReceiptState, SampleReceipt, TransactionReceipt,
};
use crate::source::{PinnedSource, SourceRoot};

const QUICK_SAMPLE_BYTES: u64 = 4 * 1024 * 1024;
const BALANCED_SAMPLE_BYTES: u64 = 1024 * 1024;
const BALANCED_INTERIOR_SAMPLES: u64 = 8;
const JOURNAL_PROGRESS_BYTES: u64 = 64 * 1024 * 1024;

pub struct Transaction<'a, S: MediaSession> {
    session: S,
    plan: &'a WritePlan,
    sources: &'a SourceRoot,
    receipt: TransactionReceipt,
    session_disposed: bool,
}

pub trait Journal {
    fn persist(&mut self, receipt: &TransactionReceipt) -> Result<()>;
}

pub struct NoopJournal;

impl Journal for NoopJournal {
    fn persist(&mut self, _receipt: &TransactionReceipt) -> Result<()> {
        Ok(())
    }
}

impl<'a, S: MediaSession> Transaction<'a, S> {
    pub fn new(
        mut session: S,
        plan: &'a WritePlan,
        sources: &'a SourceRoot,
        evidence_root: &Path,
        transaction_id: String,
        bindings: EvidenceBindings,
    ) -> Result<Self> {
        let validation = (|| {
            validate_id(&transaction_id, "transaction id")?;
            validate_bindings(&bindings)?;
            let profile = session.profile();
            profile.validate()?;
            plan.validate(profile)?;
            let identity = session.identity();
            if identity.size != profile.whole_size
                || identity.sector_size != profile.sector_size
                || identity.hardware_target != profile.target
                || !identity.removable
                || identity.system_disk
            {
                return Err(Error::InvalidData(
                    "claimed media identity does not match profile".into(),
                ));
            }
            if plan.target_stable_id != identity.stable_id {
                return Err(Error::InvalidData(
                    "write plan stable device identity does not match claimed media".into(),
                ));
            }
            session.validate_external_path(sources.path())?;
            session.validate_external_path(evidence_root)?;
            Ok(())
        })();
        if let Err(error) = validation {
            let disposition = dispose_session(&mut session);
            if disposition.is_complete() {
                return Err(error);
            }
            return Err(Error::InvalidData(format!(
                "transaction construction failed: {error}; claimed-media disposition incomplete: {}",
                disposition.errors().join("; ")
            )));
        }
        let profile = session.profile();
        let identity = session.identity();
        let receipt = TransactionReceipt::new(
            transaction_id,
            plan.plan_id.clone(),
            profile.profile_id.clone(),
            bindings,
            identity.clone(),
            plan.verification,
        );
        Ok(Self {
            session,
            plan,
            sources,
            receipt,
            session_disposed: false,
        })
    }

    pub fn execute(self) -> (Result<TransactionReceipt>, TransactionReceipt) {
        self.execute_with_journal(&mut NoopJournal)
    }

    pub fn execute_with_journal<J: Journal>(
        mut self,
        journal: &mut J,
    ) -> (Result<TransactionReceipt>, TransactionReceipt) {
        let result = journal
            .persist(&self.receipt)
            .and_then(|()| self.execute_inner(journal));
        if let Err(error) = result {
            self.receipt.state = ReceiptState::Failed;
            self.receipt.safe_to_boot = false;
            self.receipt
                .details
                .insert("error".into(), error.to_string());
            let disposition = dispose_session(&mut self.session);
            self.session_disposed = true;
            let disposition_errors = disposition.errors().join("; ");
            self.receipt.failure_disposition = Some(disposition);
            if let Err(journal_error) = journal.persist(&self.receipt) {
                self.receipt
                    .details
                    .insert("journal_error".into(), journal_error.to_string());
                return (
                    Err(Error::InvalidData(format!(
                        "transaction failed: {error}; final journal persistence failed: {journal_error}"
                    ))),
                    self.receipt.clone(),
                );
            }
            if disposition_errors.is_empty() {
                return (Err(error), self.receipt.clone());
            }
            return (
                Err(Error::InvalidData(format!(
                    "transaction failed: {error}; failed-media disposition incomplete: {disposition_errors}"
                ))),
                self.receipt.clone(),
            );
        }
        self.session_disposed = true;
        (Ok(self.receipt.clone()), self.receipt.clone())
    }

    fn execute_inner<J: Journal>(&mut self, journal: &mut J) -> Result<()> {
        let mut pinned_sources = BTreeMap::<String, PinnedSource>::new();
        for operation in &self.plan.operations {
            let source = self.sources.open_verified(&operation.source)?;
            pinned_sources.insert(operation.id.clone(), source);
        }
        self.verify_prefix()?;
        let unchanged_before = self.hash_unchanged_ranges()?;
        let mut before_hashes = BTreeMap::new();
        for operation in &self.plan.operations {
            if let TargetPrecondition::ExactSha256 { sha256 } = &operation.target_before {
                let actual = self.hash_partition(operation)?;
                if &actual != sha256 {
                    return Err(Error::InvalidData(format!(
                        "target baseline mismatch for {}",
                        operation.id
                    )));
                }
                before_hashes.insert(operation.id.clone(), actual);
            }
        }

        self.receipt.state = ReceiptState::PreflightComplete;
        self.receipt.operations = self
            .plan
            .operations
            .iter()
            .map(|operation| {
                let partition = self.session.profile().partition(operation.partition)?;
                Ok(OperationReceipt {
                    id: operation.id.clone(),
                    partition: operation.partition,
                    offset: partition.offset,
                    length: partition.size,
                    state: OperationState::Pending,
                    bytes_written: 0,
                    source_sha256: operation.source.sha256.clone(),
                    target_sha256_before: before_hashes.get(&operation.id).cloned(),
                    target_sha256_after: None,
                    samples_after: Vec::new(),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        journal.persist(&self.receipt)?;

        let destructive_request = self.destructive_authorization_request()?;
        let destructive_authorization = if let Some(request) = destructive_request.as_ref() {
            let issuer = DestructiveAuthorizationIssuer::new(request);
            let authorization = self.session.authorize_destructive(request, issuer)?;
            if !authorization.authorizes(request) {
                return Err(Error::InvalidData(
                    "backend issued a destructive capability for the wrong transaction".into(),
                ));
            }
            Some(authorization)
        } else {
            None
        };

        self.receipt.state = ReceiptState::WriteInProgress;
        journal.persist(&self.receipt)?;
        for operation in &self.plan.operations {
            if matches!(
                operation.target_before,
                TargetPrecondition::Disposable { .. }
            ) {
                let authorized = destructive_request
                    .as_ref()
                    .zip(destructive_authorization.as_ref())
                    .is_some_and(|(request, authorization)| authorization.authorizes(request));
                if !authorized {
                    return Err(Error::InvalidData(format!(
                        "destructive operation {} has no backend-issued capability",
                        operation.id
                    )));
                }
            }
            let partition = self
                .session
                .profile()
                .partition(operation.partition)?
                .clone();
            let source = pinned_sources.get_mut(&operation.id).ok_or_else(|| {
                Error::InvalidData("verified source vanished from transaction".into())
            })?;
            let receipt_index = self.operation_receipt_index(&operation.id)?;
            self.receipt.operations[receipt_index].state = OperationState::Writing;
            journal.persist(&self.receipt)?;
            let mut last_persisted_bytes = 0_u64;
            let receipt = &mut self.receipt;
            let session = &mut self.session;
            let mut progress = |bytes_written: u64| -> Result<()> {
                if bytes_written == partition.size
                    || bytes_written.saturating_sub(last_persisted_bytes) >= JOURNAL_PROGRESS_BYTES
                {
                    receipt.operations[receipt_index].bytes_written = bytes_written;
                    journal.persist(receipt)?;
                    last_persisted_bytes = bytes_written;
                }
                Ok(())
            };
            let outcome = match session.write_partition(&partition, &mut source.file, &mut progress)
            {
                Ok(outcome) => outcome,
                Err(Error::PartialWrite {
                    target_offset,
                    target_length,
                    bytes_written,
                    message,
                }) => {
                    self.receipt.operations[receipt_index].state = OperationState::Failed;
                    self.receipt.operations[receipt_index].bytes_written = bytes_written;
                    journal.persist(&self.receipt)?;
                    return Err(Error::PartialWrite {
                        target_offset,
                        target_length,
                        bytes_written,
                        message,
                    });
                }
                Err(error) => {
                    self.receipt.operations[receipt_index].state = OperationState::Failed;
                    journal.persist(&self.receipt)?;
                    return Err(error);
                }
            };
            self.receipt.operations[receipt_index].bytes_written = outcome.bytes_written;
            if outcome.bytes_written != partition.size
                || outcome.source_stream_sha256 != operation.source.sha256
            {
                self.receipt.operations[receipt_index].state = OperationState::Failed;
                journal.persist(&self.receipt)?;
                return Err(Error::InvalidData(format!(
                    "actual source stream did not match operation {}",
                    operation.id
                )));
            }
            self.receipt.operations[receipt_index].state = OperationState::Written;
            journal.persist(&self.receipt)?;
            self.session.flush_and_prepare_readback()?;
            let (target_sha256_after, samples_after) = self.verify_written(operation, source)?;
            self.receipt.operations[receipt_index].state = OperationState::Verified;
            self.receipt.operations[receipt_index].target_sha256_after = target_sha256_after;
            self.receipt.operations[receipt_index].samples_after = samples_after;
            journal.persist(&self.receipt)?;
        }
        self.receipt.state = ReceiptState::WriteComplete;
        journal.persist(&self.receipt)?;

        self.verify_prefix()?;
        for (attestation, before) in self.plan.unchanged_ranges.iter().zip(unchanged_before) {
            let after = self.hash_media_range(attestation.offset, attestation.length)?;
            if before != after {
                return Err(Error::InvalidData(format!(
                    "unchanged range {} changed",
                    attestation.id
                )));
            }
            self.receipt.unchanged_ranges.push(RangeReceipt {
                id: attestation.id.clone(),
                offset: attestation.offset,
                length: attestation.length,
                sha256_before: before,
                sha256_after: after,
            });
        }
        self.session.flush_and_prepare_readback()?;
        self.receipt.state = ReceiptState::VerificationComplete;
        self.receipt.safe_to_boot = false;
        journal.persist(&self.receipt)?;
        self.session.eject()?;
        self.receipt.state = ReceiptState::Ejected;
        self.receipt.safe_to_boot = true;
        journal.persist(&self.receipt)?;
        Ok(())
    }

    fn destructive_authorization_request(&self) -> Result<Option<DestructiveAuthorizationRequest>> {
        let mut ranges = Vec::new();
        for operation in &self.plan.operations {
            if let TargetPrecondition::Disposable { rationale, .. } = &operation.target_before {
                let partition = self.session.profile().partition(operation.partition)?;
                ranges.push(DestructiveRangeRequest::new(
                    operation.id.clone(),
                    partition.offset,
                    partition.size,
                    rationale.clone(),
                ));
            }
        }
        if ranges.is_empty() {
            return Ok(None);
        }
        let identity = self.session.identity();
        Ok(Some(DestructiveAuthorizationRequest::new(
            identity.stable_id.clone(),
            identity.physical_store_id.clone(),
            self.receipt.bindings.profile_sha256.clone(),
            self.receipt.bindings.plan_sha256.clone(),
            self.receipt.transaction_id.clone(),
            ranges,
        )))
    }

    fn operation_receipt_index(&self, operation_id: &str) -> Result<usize> {
        self.receipt
            .operations
            .iter()
            .position(|receipt| receipt.id == operation_id)
            .ok_or_else(|| Error::InvalidData("operation receipt is missing".into()))
    }

    fn verify_prefix(&mut self) -> Result<()> {
        let prefix = self.session.profile().prefix.clone();
        let actual = self.hash_media_range(0, prefix.size)?;
        if actual != prefix.sha256 {
            return Err(Error::InvalidData("media prefix digest mismatch".into()));
        }
        Ok(())
    }

    fn hash_partition(&mut self, operation: &WriteOperation) -> Result<String> {
        let partition = self
            .session
            .profile()
            .partition(operation.partition)?
            .clone();
        self.hash_media_range(partition.offset, partition.size)
    }

    fn hash_unchanged_ranges(&mut self) -> Result<Vec<String>> {
        let attestations = self.plan.unchanged_ranges.clone();
        attestations
            .iter()
            .map(|attestation| {
                let actual = self.hash_media_range(attestation.offset, attestation.length)?;
                if actual != attestation.sha256_before {
                    return Err(Error::InvalidData(format!(
                        "unchanged range {} baseline mismatch",
                        attestation.id
                    )));
                }
                Ok(actual)
            })
            .collect()
    }

    fn verify_written(
        &mut self,
        operation: &WriteOperation,
        source: &mut PinnedSource,
    ) -> Result<(Option<String>, Vec<SampleReceipt>)> {
        let partition = self
            .session
            .profile()
            .partition(operation.partition)?
            .clone();
        match self.plan.verification {
            VerificationMode::Full => {
                let digest = self.hash_media_range(partition.offset, partition.size)?;
                if digest != operation.source.sha256 {
                    return Err(Error::InvalidData(format!(
                        "full readback mismatch for {}",
                        operation.id
                    )));
                }
                Ok((Some(digest), Vec::new()))
            }
            VerificationMode::Quick | VerificationMode::Balanced => {
                let ranges = sample_ranges(
                    self.plan.verification,
                    partition.size,
                    &self.receipt.bindings.plan_sha256,
                );
                let mut receipts = Vec::with_capacity(ranges.len());
                for (source_offset, length) in ranges {
                    let target_offset = partition.offset + source_offset;
                    let target_sha256 = self.hash_media_range(target_offset, length)?;
                    let source_sha256 = hash_range(&mut source.file, source_offset, length)?;
                    if target_sha256 != source_sha256 {
                        return Err(Error::InvalidData(format!(
                            "sample readback mismatch for {} at source offset {source_offset}",
                            operation.id
                        )));
                    }
                    receipts.push(SampleReceipt {
                        source_offset,
                        target_offset,
                        length,
                        source_sha256,
                        target_sha256,
                    });
                }
                Ok((None, receipts))
            }
        }
    }

    fn hash_media_range(&mut self, offset: u64, length: u64) -> Result<String> {
        let reader = self.session.reader()?;
        reader
            .seek(SeekFrom::Start(offset))
            .map_err(|source| Error::io("seek claimed media", source))?;
        hash_range(reader, offset, length)
    }
}

impl<S: MediaSession> Drop for Transaction<'_, S> {
    fn drop(&mut self) {
        if !self.session_disposed {
            let _ = dispose_session(&mut self.session);
            self.session_disposed = true;
        }
    }
}

fn dispose_session<S: MediaSession>(session: &mut S) -> FailureDisposition {
    let flush = match session.flush_and_prepare_readback() {
        Ok(()) => FailureDispositionStep::Succeeded,
        Err(error) => FailureDispositionStep::Failed {
            error: error.to_string(),
        },
    };
    // Ejection/release is deliberately attempted even when flushing fails.
    let eject = match session.eject() {
        Ok(()) => FailureDispositionStep::Succeeded,
        Err(error) => FailureDispositionStep::Failed {
            error: error.to_string(),
        },
    };
    FailureDisposition { flush, eject }
}

fn validate_bindings(bindings: &EvidenceBindings) -> Result<()> {
    if !is_sha256(&bindings.profile_sha256)
        || !is_sha256(&bindings.plan_sha256)
        || !is_sha256(&bindings.tool_sha256)
        || bindings.tool_version.trim().is_empty()
        || bindings.tool_version.len() > 128
    {
        return Err(Error::InvalidData("evidence bindings are invalid".into()));
    }
    Ok(())
}

fn sample_ranges(mode: VerificationMode, size: u64, plan_sha256: &str) -> Vec<(u64, u64)> {
    let sample_bytes = match mode {
        VerificationMode::Quick => QUICK_SAMPLE_BYTES,
        VerificationMode::Balanced => BALANCED_SAMPLE_BYTES,
        VerificationMode::Full => return vec![(0, size)],
    }
    .min(size);
    let max_offset = size - sample_bytes;
    let mut offsets = BTreeSet::from([0, max_offset]);
    if mode == VerificationMode::Balanced && max_offset != 0 {
        let seed = u64::from_str_radix(&plan_sha256[..16], 16).unwrap_or(0);
        for index in 1..=BALANCED_INTERIOR_SAMPLES {
            let evenly_spaced = max_offset.saturating_mul(index) / (BALANCED_INTERIOR_SAMPLES + 1);
            let jitter_window = (max_offset / (BALANCED_INTERIOR_SAMPLES + 1)).max(1);
            let rotated = seed.rotate_left(index as u32);
            let jitter = rotated % jitter_window;
            offsets.insert((evenly_spaced + jitter).min(max_offset));
        }
    }
    offsets
        .into_iter()
        .map(|offset| (offset, sample_bytes))
        .collect()
}

pub fn receipt_json(receipt: &TransactionReceipt) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(receipt)?;
    bytes.push(b'\n');
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn balanced_has_interior_samples_while_quick_does_not() {
        let size = 64 * 1024 * 1024;
        let digest = "1".repeat(64);
        let quick = sample_ranges(VerificationMode::Quick, size, &digest);
        let balanced = sample_ranges(VerificationMode::Balanced, size, &digest);
        assert_eq!(quick.len(), 2);
        assert!(balanced.len() > quick.len());
        assert!(
            balanced
                .iter()
                .any(|(offset, _)| *offset > 0 && *offset < size)
        );
    }
}
